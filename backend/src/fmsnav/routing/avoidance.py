"""Desvio de areas restritas (NOTAM).

Estrategia, igual a do planejador original:
  1. nos dentro de alguma area ficam caros no A* (ver astar.BLOCKED_PENALTY);
  2. se a rota ainda cruza uma area, os nos internos sao removidos e cada
     segmento que cruza ganha uma coordenada de escape (ponto virtual),
     preservando as aerovias antes e depois.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot

from ..geo import (
    LatLon, bounds, centroid, max_radius, planar_distance, point_in_polygon,
    segment_intersects_polygon,
)
from ..navgraph import NavGraph, PathPoint, VirtualPoint

MAX_ESCAPE_ITERATIONS = 30


@dataclass(frozen=True)
class AvoidZone:
    id: str
    polygon: tuple[LatLon, ...]
    bbox: tuple[float, float, float, float] = field(init=False)

    def __post_init__(self):
        object.__setattr__(self, "bbox", bounds(self.polygon))

    def contains(self, p: LatLon) -> bool:
        la0, la1, lo0, lo1 = self.bbox
        return la0 <= p[0] <= la1 and lo0 <= p[1] <= lo1 and point_in_polygon(p, self.polygon)


class VirtualNamer:
    """WPTA1, WPTB2, ... (um contador por planejamento)."""

    def __init__(self):
        self.n = 0

    def __call__(self) -> str:
        label = f"WPT{chr(65 + self.n % 26)}{self.n + 1}"
        self.n += 1
        return label


class Avoidance:
    """Areas a evitar, ja indexadas contra um grafo."""

    def __init__(self, graph: NavGraph, zones: list[AvoidZone]):
        self.graph = graph
        self.zones = zones
        self.blocked: frozenset[int] = frozenset(
            i for z in zones
            for i in graph.nodes_in_bbox(z.bbox[0], z.bbox[2], z.bbox[1], z.bbox[3])
            if z.contains((graph.lats[i], graph.lons[i]))
        )

    def __bool__(self) -> bool:
        return bool(self.zones)

    def segment_hit(self, a: LatLon, b: LatLon) -> AvoidZone | None:
        for z in self.zones:
            if segment_intersects_polygon(a, b, z.polygon):
                return z
        return None

    def path_crosses(self, path: list[PathPoint]) -> bool:
        c = self.graph.coord
        return any(self.segment_hit(c(path[k]), c(path[k + 1])) for k in range(len(path) - 1))

    def strip_interior(self, path: list[PathPoint]) -> list[PathPoint]:
        """Remove nos dentro de alguma area (mantem as duas pontas)."""
        c = self.graph.coord
        last = len(path) - 1
        return [p for k, p in enumerate(path)
                if k in (0, last) or not any(z.contains(c(p)) for z in self.zones)]

    def best_escape(self, a: LatLon, b: LatLon, zone: AvoidZone) -> LatLon | None:
        """Coordenada C mais curta tal que A->C e C->B nao cruzem nenhuma area.

        Candidatos: vertices empurrados para fora do centroide e offsets
        perpendiculares ao segmento A-B.
        """
        cent = centroid(zone.polygon)
        raio = max_radius(zone.polygon, cent)
        cands: list[LatLon] = []
        for vlat, vlon in zone.polygon:
            dx, dy = vlat - cent[0], vlon - cent[1]
            ln = hypot(dx, dy) or 1e-9
            for extra in (0.15, 0.35, 0.6):
                cands.append((cent[0] + dx / ln * (ln + raio * extra),
                              cent[1] + dy / ln * (ln + raio * extra)))

        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        dlat, dlon = b[0] - a[0], b[1] - a[1]
        plen = hypot(dlat, dlon) or 1e-9
        perp = (-dlon / plen, dlat / plen)
        for sign in (1, -1):
            for mult in (1, 1.5, 2, 3, 4):
                off = raio * mult * sign
                cands.append((mid[0] + perp[0] * off, mid[1] + perp[1] * off))

        best, best_cost = None, float("inf")
        for c in cands:
            if point_in_polygon(c, zone.polygon):
                continue
            if self.segment_hit(a, c) or self.segment_hit(c, b):
                continue
            cost = planar_distance(a, c) + planar_distance(c, b)
            if cost < best_cost:
                best, best_cost = c, cost
        return best

    def clear_route(self, path: list[PathPoint], namer: VirtualNamer) -> list[PathPoint] | None:
        """Insere coordenadas de escape so nos segmentos que cruzam alguma area."""
        pts = list(path)
        c = self.graph.coord
        for _ in range(MAX_ESCAPE_ITERATIONS):
            hit_k, hit_zone = -1, None
            for k in range(len(pts) - 1):
                z = self.segment_hit(c(pts[k]), c(pts[k + 1]))
                if z is not None:
                    hit_k, hit_zone = k, z
                    break
            if hit_zone is None:
                return pts
            esc = self.best_escape(c(pts[hit_k]), c(pts[hit_k + 1]), hit_zone)
            if esc is None:
                return None
            pts.insert(hit_k + 1, VirtualPoint(namer(), esc[0], esc[1]))
        return None if self.path_crosses(pts) else pts
