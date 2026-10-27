"""Planejamento porta-a-porta: aeroporto -> SID -> en-route -> STAR -> aeroporto.

Uma SID forca a saida pelo seu fixo final; uma STAR forca a chegada pelo seu
fixo inicial. O trecho en-route e (re)calculado entre essas duas pontas e as
cadeias dos procedimentos sao coladas em cada lado.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from ..navgraph import NavGraph, PathPoint
from .astar import costs_from, shortest_path
from .avoidance import Avoidance, VirtualNamer
from .procedures import (
    SID, STAR, ProcedureOption, filter_by_runway, find_option, procedure_options,
)

AUTO = "auto"
LEVEL_NAME = {"H": " de alta", "L": " de baixa"}


class PlanningError(ValueError):
    """Pedido invalido ou sem rota possivel — mensagem pronta para o usuario."""


@dataclass
class EditedCore:
    """Rota editada manualmente que deve ser preservada ao trocar SID/STAR.

    `path` e a rota completa atual; `fallback` e o intervalo [ini, fim) do
    miolo en-route, usado quando as novas pontas nao aparecem em `path`.
    """
    path: list[PathPoint]
    fallback: tuple[int, int]


@dataclass
class RouteRequest:
    origin: str
    destination: str
    runway_dep: str | None = None
    runway_arr: str | None = None
    sid: str | None = None             # chave da opcao, "auto" ou None
    star: str | None = None
    edited: EditedCore | None = None
    level: str | None = None            # H = so aerovias de alta (U...), L = so baixa


@dataclass
class PlannedRoute:
    points: list[PathPoint]
    sid: ProcedureOption | None
    star: ProcedureOption | None
    sid_chain: list[PathPoint]         # para desenho: [origem, ...SID]
    star_chain: list[PathPoint]        # para desenho: [...STAR, destino]
    altitudes: dict[int, tuple[int, str]]
    km: float
    direct_km: float
    avoidance_applied: bool = False
    warnings: list[str] = field(default_factory=list)


def _dedupe(path: list[PathPoint]) -> list[PathPoint]:
    return [p for k, p in enumerate(path) if k == 0 or p != path[k - 1]]


def _compose(src: int, sid: list[int] | None, mid: list[PathPoint],
             star: list[int] | None, dst: int) -> list[PathPoint]:
    path: list[PathPoint] = [src]
    if sid:
        path += sid[:-1]
    path += mid
    if star:
        path += star[1:]
    path.append(dst)
    return _dedupe(path)


class RoutePlanner:
    def __init__(self, graph: NavGraph):
        self.graph = graph

    # ------------------------------------------------------- consultas

    def airport(self, icao: str) -> int:
        node = self.graph.by_icao.get(icao.strip().upper())
        if node is None:
            raise PlanningError(f'"{icao.strip().upper()}" não está no banco. Use o código ICAO.')
        return node

    def options(self, icao: str, kind: str, runway: str | None = None) -> list[ProcedureOption]:
        return filter_by_runway(procedure_options(self.graph, icao.upper(), kind), runway)

    # ----------------------------------------------------- planejamento

    def plan(self, req: RouteRequest, avoidance: Avoidance | None = None) -> PlannedRoute:
        g = self.graph
        src, dst = self.airport(req.origin), self.airport(req.destination)
        if src == dst:
            raise PlanningError("Origem e destino são o mesmo aeródromo.")
        blocked = avoidance.blocked if avoidance else frozenset()
        warnings: list[str] = []

        level = req.level
        base = shortest_path(g, src, dst, blocked, level)
        if base is None:
            raise PlanningError(f"Sem rota por aerovias{LEVEL_NAME.get(level, '')} "
                                f"entre {g.idents[src]} e {g.idents[dst]}.")

        sid, star = self._choose_procedures(req, src, dst, blocked, warnings)
        sid_chain = sid.chain(req.runway_dep) if sid else None
        star_chain = star.chain(req.runway_arr) if star else None
        a = sid_chain[-1] if sid_chain else src
        b = star_chain[0] if star_chain else dst

        if req.edited:
            mid = self._extract_core(req.edited, a, b)
        else:
            leg = shortest_path(g, a, b, blocked, level)
            if leg is None:
                warnings.append("Sem rota en-route entre os procedimentos escolhidos; mantida a rota base.")
                return self._result(base.path, src, dst, sid, star, sid_chain, star_chain, req, warnings)
            mid = leg.path

        path = _compose(src, sid_chain, mid, star_chain, dst)

        applied = False
        if avoidance and avoidance.path_crosses(path):
            namer = VirtualNamer()
            new_path = None
            clear = avoidance.clear_route(avoidance.strip_interior(mid), namer)
            if clear:
                cand = _compose(src, sid_chain, clear, star_chain, dst)
                if not avoidance.path_crosses(cand):
                    new_path = cand
            if new_path is None:
                # SID/STAR ainda cruzam: rota direta src->dst com desvio, sem procedimentos
                direct = shortest_path(g, src, dst, blocked, level)
                if direct:
                    clear = avoidance.clear_route(avoidance.strip_interior(direct.path), namer)
                    if clear and not avoidance.path_crosses(clear):
                        new_path = clear
                        if sid or star:
                            warnings.append("SID/STAR cruzam área restrita: procedimentos removidos.")
                        sid = star = None
                        sid_chain = star_chain = None
            if new_path is not None:
                path, applied = new_path, True
            else:
                warnings.append("Não foi possível encontrar desvio livre das áreas restritas.")

        res = self._result(path, src, dst, sid, star, sid_chain, star_chain, req, warnings)
        res.avoidance_applied = applied
        return res

    def _result(self, path, src, dst, sid, star, sid_chain, star_chain, req, warnings) -> PlannedRoute:
        altitudes: dict[int, tuple[int, str]] = {}
        if sid:
            altitudes.update(sid.altitude_constraints(req.runway_dep))
        if star:
            altitudes.update(star.altitude_constraints(req.runway_arr))
        return PlannedRoute(
            points=path,
            sid=sid,
            star=star,
            sid_chain=[src, *sid_chain] if sid_chain else [],
            star_chain=[*star_chain, dst] if star_chain else [],
            altitudes=altitudes,
            km=self.graph.path_km(path),
            direct_km=self.graph.distance_km(src, dst),
            warnings=warnings,
        )

    def _choose_procedures(self, req, src, dst, blocked, warnings):
        """Resolve sid/star: chave explicita, "auto" (melhor combinacao) ou None."""
        g = self.graph
        origin, dest = g.idents[src], g.idents[dst]

        def candidates(value, icao, kind, runway, label):
            if not value:
                return [None]
            if value == AUTO:
                opts = self.options(icao, kind, runway)
                if not opts:
                    rw = f" para RW{runway}" if runway else ""
                    warnings.append(f"Nenhuma {label} de {icao}{rw}.")
                    return [None]
                return opts
            opt = find_option(self.options(icao, kind), value)
            if opt is None:
                raise PlanningError(f"{label} {value} não existe em {icao}.")
            return [opt]

        s_cands = candidates(req.sid, origin, SID, req.runway_dep, "SID")
        t_cands = candidates(req.star, dest, STAR, req.runway_arr, "STAR")
        if len(s_cands) == 1 and len(t_cands) == 1:
            return s_cands[0], t_cands[0]

        s_chains = [o.chain(req.runway_dep) if o else None for o in s_cands]
        t_chains = [o.chain(req.runway_arr) if o else None for o in t_cands]
        exits = {c[-1] if c else src for c in s_chains}
        entries = {c[0] if c else dst for c in t_chains}
        dist = {a: costs_from(g, a, entries, blocked, req.level) for a in exits}

        best, best_km = (None, None), float("inf")
        for (so, sc), (to, tc) in product(zip(s_cands, s_chains), zip(t_cands, t_chains)):
            a = sc[-1] if sc else src
            b = tc[0] if tc else dst
            enroute = dist[a].get(b)
            if enroute is None:
                continue
            km = enroute + (g.path_km(sc) if sc else 0) + (g.path_km(tc) if tc else 0)
            if km < best_km:
                best, best_km = (so, to), km
        if best_km == float("inf"):
            warnings.append("Nenhuma combinação SID/STAR conecta à malha de aerovias.")
        return best

    @staticmethod
    def _extract_core(edited: EditedCore, a: PathPoint, b: PathPoint) -> list[PathPoint]:
        """Miolo en-route editado entre as novas pontas a e b."""
        p = edited.path
        i = p.index(a) if a in p else -1
        j = len(p) - 1 - p[::-1].index(b) if b in p else -1
        if i < 0 or j < 0 or i > j:
            s, e = edited.fallback
            return p[max(1, s):max(1, e)]
        return p[i:j + 1]
