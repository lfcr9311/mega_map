from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ...routing import SID, STAR, ProcedureOption
from .. import schemas
from ..deps import AppState, get_state

router = APIRouter(prefix="/airports", tags=["airports"])

_KIND = {"SID": SID, "STAR": STAR}


def _airport(st: AppState, node: int) -> schemas.Airport:
    g = st.graph
    icao = g.idents[node]
    return schemas.Airport(icao=icao, lat=g.lats[node], lon=g.lons[node],
                           procedures=len(g.procedures.get(icao, ())))


def procedure_out(o: ProcedureOption) -> schemas.Procedure:
    return schemas.Procedure(
        key=o.key, name=o.name, transition=o.entry.transition, label=o.label,
        runway_transitions=[t.transition for t in o.runway_transitions],
    )


@router.get("", response_model=list[schemas.Airport])
def search(q: str = Query(..., min_length=1), limit: int = Query(8, le=50),
           st: AppState = Depends(get_state)):
    return [_airport(st, i) for i in st.graph.search_airports(q, limit)]


@router.get("/{icao}", response_model=schemas.AirportDetail)
def detail(icao: str, st: AppState = Depends(get_state)):
    node = st.graph.by_icao.get(icao.upper())
    if node is None:
        raise HTTPException(404, f"{icao.upper()} não está no banco.")
    rwys = [schemas.Runway(ident=r.ident, bearing=r.bearing, length_ft=r.length_ft,
                           elevation_ft=r.elevation_ft)
            for r in st.graph.runways.get(icao.upper(), ())]
    return schemas.AirportDetail(**_airport(st, node).model_dump(), runways=rwys)


@router.get("/{icao}/procedures", response_model=list[schemas.Procedure])
def procedures(icao: str, kind: Literal["SID", "STAR"], runway: str | None = None,
               st: AppState = Depends(get_state)):
    return [procedure_out(o) for o in st.planner.options(icao, _KIND[kind], runway)]
