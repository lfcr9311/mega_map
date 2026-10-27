"""Grafo de rotas em memoria, carregado do navgraph compilado.

Nos sao inteiros (indice no arquivo). Uma rota pode tambem conter pontos
virtuais (coordenadas livres, ex.: desvio de NOTAM) — `PathPoint` cobre os dois.
"""
from __future__ import annotations

import gzip
import json
from collections import defaultdict
from dataclasses import dataclass
from math import floor
from pathlib import Path
from typing import Iterator, Union

from ..geo import LatLon, haversine_km


@dataclass(frozen=True, slots=True)
class VirtualPoint:
    """Coordenada livre fora do banco (ex.: WPTA1 de desvio de NOTAM)."""
    ident: str
    lat: float
    lon: float


PathPoint = Union[int, VirtualPoint]

HIGH, LOW = "H", "L"


def airway_level(designator: str) -> str:
    """Nivel da aerovia pelo designador: alta comeca com U (ex.: UM465), o resto e baixa.

    "" = conector terminal (sem designador), usavel em qualquer nivel.
    Alternativa: AIRWAY.S01 traz um nivel H/L/B decodificado (docs §11), que
    discorda do prefixo em ~80 aerovias brasileiras marcadas "B" (ambas).
    """
    if not designator:
        return ""
    return HIGH if designator.startswith("U") else LOW


def level_allows(wanted: str | None, edge_level: str) -> bool:
    return not wanted or not edge_level or edge_level == wanted


@dataclass(frozen=True, slots=True)
class ProcPoint:
    node: int
    path_term: str
    altitude_ft: int
    alt_desc: str


@dataclass(frozen=True, slots=True)
class RawProcedure:
    """Uma linha de procedimento do banco: um (nome, transicao)."""
    kind: str                   # S=SID T=STAR A=APPR
    name: str
    transition: str             # "RW34" = runway transition; senao en-route
    points: tuple[ProcPoint, ...]

    @property
    def is_runway_transition(self) -> bool:
        return self.transition.startswith("RW")

    @property
    def nodes(self) -> list[int]:
        return [p.node for p in self.points]


@dataclass(frozen=True, slots=True)
class RunwayInfo:
    bearing: float
    length_ft: int
    elevation_ft: int

    @property
    def ident(self) -> str:
        return f"{(floor(self.bearing / 10 + 0.5) or 36):02d}"


class NavGraph:
    GRID_DEG = 1.0

    def __init__(self, graph: dict, meta: dict | None = None):
        self.meta = meta or {}
        n = graph["n"]
        self.idents: list[str] = [x[0] for x in n]
        self.lats: list[float] = [x[1] for x in n]
        self.lons: list[float] = [x[2] for x in n]
        self.kinds: list[str] = [x[3] for x in n]

        # adjacencia: (vizinho, km, nivel) — nivel H/L da aerovia, "" para conector
        self.adj: list[list[tuple[int, float, str]]] = [[] for _ in n]
        self._airways: dict[tuple[int, int], list[str]] = defaultdict(list)
        seen: set[tuple[int, int]] = set()
        self.edges: list[tuple[int, int]] = []        # sem duplicatas, para desenho
        for a, b, km, aw in graph["e"]:
            lvl = airway_level(aw)
            self.adj[a].append((b, km, lvl))
            self.adj[b].append((a, km, lvl))
            key = (a, b) if a < b else (b, a)
            if aw:
                self._airways[key].append(aw)
            if key not in seen:
                seen.add(key)
                self.edges.append(key)

        self.by_icao: dict[str, int] = {}
        self._by_name: dict[str, list[int]] = defaultdict(list)
        for i, ident in enumerate(self.idents):
            self._by_name[ident].append(i)
            if self.kinds[i] == "A":
                self.by_icao[ident] = i
        self.airport_ids: list[int] = sorted(self.by_icao.values(), key=lambda i: self.idents[i])

        self.procedures: dict[str, list[RawProcedure]] = {
            icao: [
                RawProcedure(p[0], p[1], str(p[2]), tuple(ProcPoint(*pt) for pt in p[3]))
                for p in plist
            ]
            for icao, plist in graph["p"].items()
        }
        self.runways: dict[str, list[RunwayInfo]] = {
            icao: [RunwayInfo(*r) for r in rs] for icao, rs in graph["r"].items()
        }

        self._grid: dict[tuple[int, int], list[int]] = defaultdict(list)
        for i in range(len(n)):
            self._grid[self._cell(self.lats[i], self.lons[i])].append(i)

    # ------------------------------------------------------------ load

    @classmethod
    def load(cls, path: str | Path) -> "NavGraph":
        doc = json.loads(gzip.decompress(Path(path).read_bytes()))
        return cls(doc["graph"], doc.get("meta"))

    # ------------------------------------------------------------ nos

    def __len__(self) -> int:
        return len(self.idents)

    def coord(self, p: PathPoint) -> LatLon:
        if isinstance(p, VirtualPoint):
            return (p.lat, p.lon)
        return (self.lats[p], self.lons[p])

    def ident(self, p: PathPoint) -> str:
        return p.ident if isinstance(p, VirtualPoint) else self.idents[p]

    def kind(self, p: PathPoint) -> str:
        return "V" if isinstance(p, VirtualPoint) else self.kinds[p]

    def distance_km(self, a: PathPoint, b: PathPoint) -> float:
        (la1, lo1), (la2, lo2) = self.coord(a), self.coord(b)
        return haversine_km(la1, lo1, la2, lo2)

    def path_km(self, path: list[PathPoint]) -> float:
        return sum(self.distance_km(path[k], path[k + 1]) for k in range(len(path) - 1))

    def airway_between(self, a: PathPoint, b: PathPoint, level: str | None = None) -> str:
        """Designador da perna; com `level`, prefere uma aerovia desse nivel."""
        if isinstance(a, VirtualPoint) or isinstance(b, VirtualPoint):
            return ""
        names = self._airways.get((a, b) if a < b else (b, a))
        if not names:
            return ""
        if level:
            match = [n for n in names if airway_level(n) == level]
            if match:
                return match[-1]
        return names[-1]

    # ------------------------------------------------------------ busca

    def resolve_ident(self, ident: str, near: LatLon | None = None) -> int | None:
        """No pelo ident; com idents repetidos, o mais proximo de `near`."""
        cands = self._by_name.get(ident.strip().upper())
        if not cands:
            return None
        if len(cands) == 1 or near is None:
            return cands[0]
        return min(cands, key=lambda c: haversine_km(near[0], near[1], self.lats[c], self.lons[c]))

    def search_airports(self, q: str, limit: int = 8) -> list[int]:
        """Exato, depois prefixo, depois substring."""
        q = q.strip().upper()
        if not q:
            return []
        exact, prefix, contains = [], [], []
        for i in self.airport_ids:
            ident = self.idents[i]
            if ident == q:
                exact.append(i)
            elif ident.startswith(q):
                prefix.append(i)
            elif q in ident:
                contains.append(i)
        return (exact + prefix + contains)[:limit]

    # ------------------------------------------------------- espacial

    def _cell(self, lat: float, lon: float) -> tuple[int, int]:
        return (floor(lat / self.GRID_DEG), floor(lon / self.GRID_DEG))

    def nodes_in_bbox(self, south: float, west: float, north: float, east: float) -> Iterator[int]:
        (r0, c0), (r1, c1) = self._cell(south, west), self._cell(north, east)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                for i in self._grid.get((r, c), ()):
                    if south <= self.lats[i] <= north and west <= self.lons[i] <= east:
                        yield i

    def edges_in_bbox(self, south: float, west: float, north: float, east: float,
                      level: str | None = None) -> Iterator[tuple[int, int]]:
        """Arestas com as duas pontas dentro da caixa (so as usaveis no nivel dado)."""
        inside = set(self.nodes_in_bbox(south, west, north, east))
        seen: set[tuple[int, int]] = set()
        for u in inside:
            for v, _, lvl in self.adj[u]:
                if not level_allows(level, lvl):
                    continue
                if u < v and v in inside and (u, v) not in seen:
                    seen.add((u, v))
                    yield (u, v)
