from fastapi import APIRouter, Depends, HTTPException
from starlette.concurrency import run_in_threadpool

from ...routing import EditedCore, PlanningError, ProcedureOption, RouteRequest
from .. import schemas
from ..deps import AppState, get_state, resolve_refs, to_legs, to_point
from .airports import procedure_out

router = APIRouter(prefix="/route", tags=["route"])


@router.post("", response_model=schemas.RouteOut)
async def plan_route(body: schemas.RouteIn, st: AppState = Depends(get_state)):
    """Rota porta-a-porta. sid/star = chave, "auto" (melhor combinacao) ou null."""
    g = st.graph
    edited = None
    if body.edited:
        edited = EditedCore(resolve_refs(g, body.edited.path), body.edited.fallback)
    req = RouteRequest(
        origin=body.origin, destination=body.destination,
        runway_dep=body.runway_dep, runway_arr=body.runway_arr,
        sid=body.sid, star=body.star, edited=edited, level=body.level,
    )
    avoidance = await st.notams.avoidance(g) if body.avoid_notams else None
    try:
        # A* em Python e CPU-bound: roda fora do event loop
        res = await run_in_threadpool(st.planner.plan, req, avoidance)
    except PlanningError as e:
        raise HTTPException(422, str(e)) from e

    def chosen(opt: ProcedureOption | None, chain) -> schemas.ChosenProcedure | None:
        if opt is None:
            return None
        return schemas.ChosenProcedure(**procedure_out(opt).model_dump(),
                                       chain=[to_point(g, p) for p in chain])

    return schemas.RouteOut(
        points=[to_point(g, p, res.altitudes) for p in res.points],
        legs=to_legs(g, res.points, body.level),
        km=round(res.km, 1),
        direct_km=round(res.direct_km, 1),
        sid=chosen(res.sid, res.sid_chain),
        star=chosen(res.star, res.star_chain),
        avoidance_applied=res.avoidance_applied,
        warnings=res.warnings,
    )


@router.post("/annotate", response_model=schemas.AnnotateOut)
def annotate(body: schemas.AnnotateIn, st: AppState = Depends(get_state)):
    """Resolve uma rota editada a mao (sem re-rotear) e devolve pernas e distancias."""
    g = st.graph
    path = resolve_refs(g, body.points)
    return schemas.AnnotateOut(
        points=[to_point(g, p) for p in path],
        legs=to_legs(g, path, body.level),
        km=round(g.path_km(path), 1),
    )
