"""Dependencias injetadas nas rotas (estado criado no lifespan do app)."""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException, Request

from ..navgraph import NavGraph, PathPoint, VirtualPoint
from ..notams import NotamService
from ..routing import RoutePlanner
from . import schemas


@dataclass
class AppState:
    graph: NavGraph
    planner: RoutePlanner
    notams: NotamService


def get_state(request: Request) -> AppState:
    return request.app.state.fmsnav


def to_point(g: NavGraph, p: PathPoint, altitudes: dict[int, tuple[int, str]] | None = None) -> schemas.Point:
    lat, lon = g.coord(p)
    alt = None
    if altitudes and not isinstance(p, VirtualPoint) and p in altitudes:
        ft, desc = altitudes[p]
        alt = schemas.Altitude(ft=ft, desc=desc)
    return schemas.Point(
        id=None if isinstance(p, VirtualPoint) else p,
        ident=g.ident(p), lat=lat, lon=lon, kind=g.kind(p), altitude=alt,
    )


def to_legs(g: NavGraph, path: list[PathPoint], level: str | None = None) -> list[schemas.RouteLeg]:
    return [
        schemas.RouteLeg(airway=g.airway_between(a, b, level), km=round(g.distance_km(a, b), 1))
        for a, b in zip(path, path[1:])
    ]


def resolve_refs(g: NavGraph, refs: list[schemas.PointRef]) -> list[PathPoint]:
    """PointRef -> PathPoint. Ident ambiguo resolve pelo mais proximo do ponto anterior.

    Aerodromo so vale nas pontas: no meio da rota, o ident resolve para um fixo
    homonimo ou e recusado.
    """
    out: list[PathPoint] = []
    last = len(refs) - 1
    for k, r in enumerate(refs):
        inner = 0 < k < last
        if r.id is not None:
            if not 0 <= r.id < len(g):
                raise HTTPException(422, {"index": k, "message": f"id {r.id} fora do grafo."})
            if inner and g.kinds[r.id] == "A":
                raise HTTPException(422, {"index": k, "message": f"{g.idents[r.id]} é aeródromo, não fixo de rota."})
            out.append(r.id)
        elif r.lat is not None and r.lon is not None:
            out.append(VirtualPoint(r.ident or f"PT{k}", r.lat, r.lon))
        elif r.ident:
            ident = r.ident.strip().upper()
            node = g.resolve_ident(ident, g.coord(out[-1]) if out else None, fixes_only=inner)
            if node is None:
                if inner and g.resolve_ident(ident) is not None:
                    raise HTTPException(422, {"index": k, "message": f"{ident} é aeródromo, não fixo de rota."})
                raise HTTPException(422, {"index": k, "message": f'"{ident}" não está no banco.'})
            out.append(node)
        else:
            raise HTTPException(422, {"index": k, "message": "ponto sem id, coordenada ou ident."})
    return out
