"""Caminho minimo sobre o grafo de aerovias.

A heuristica e a distancia great-circle ate o destino: limite inferior exato
do custo, logo admissivel. Nos bloqueados (dentro de area restrita) nao sao
proibidos, so ficam caros — assim sempre ha rota, e o desvio por coordenada
(routing.avoidance) cuida do que ainda cruzar a area.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import AbstractSet, Iterable

from ..geo import haversine_km
from ..navgraph import NavGraph, level_allows

BLOCKED_PENALTY = 10_000.0

_EMPTY: frozenset[int] = frozenset()


@dataclass(frozen=True, slots=True)
class PathResult:
    path: list[int]
    cost: float        # inclui penalidades de nos bloqueados


def _edge_cost(km: float, v: int, blocked: AbstractSet[int]) -> float:
    return km * BLOCKED_PENALTY if v in blocked else km


def shortest_path(graph: NavGraph, src: int, dst: int,
                  blocked: AbstractSet[int] = _EMPTY, level: str | None = None) -> PathResult | None:
    """`level` H/L restringe a aerovias de alta/baixa (conectores sempre valem)."""
    if src == dst:
        return PathResult([src], 0.0)
    lats, lons, adj = graph.lats, graph.lons, graph.adj
    dlat, dlon = lats[dst], lons[dst]

    g: dict[int, float] = {src: 0.0}
    prev: dict[int, int] = {}
    done: set[int] = set()
    heap = [(haversine_km(lats[src], lons[src], dlat, dlon), src)]
    while heap:
        _, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        if u == dst:
            break
        gu = g[u]
        for v, km, lvl in adj[u]:
            if not level_allows(level, lvl):
                continue
            nd = gu + _edge_cost(km, v, blocked)
            if nd < g.get(v, float("inf")) - 1e-9:
                g[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd + haversine_km(lats[v], lons[v], dlat, dlon), v))

    if dst not in prev:
        return None
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    path.reverse()
    return PathResult(path, g[dst])


def costs_from(graph: NavGraph, src: int, targets: Iterable[int],
               blocked: AbstractSet[int] = _EMPTY, level: str | None = None) -> dict[int, float]:
    """Dijkstra de uma origem ate todos os alvos (para assim que todos fecham).

    Usado para comparar muitas combinacoes SID x STAR sem rodar um A* por par.
    """
    pending = set(targets)
    out: dict[int, float] = {}
    if src in pending:
        out[src] = 0.0
        pending.discard(src)
    g: dict[int, float] = {src: 0.0}
    done: set[int] = set()
    heap = [(0.0, src)]
    adj = graph.adj
    while heap and pending:
        d, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        if u in pending:
            out[u] = d
            pending.discard(u)
        for v, km, lvl in adj[u]:
            if not level_allows(level, lvl):
                continue
            nd = d + _edge_cost(km, v, blocked)
            if nd < g.get(v, float("inf")) - 1e-9:
                g[v] = nd
                heapq.heappush(heap, (nd, v))
    return out
