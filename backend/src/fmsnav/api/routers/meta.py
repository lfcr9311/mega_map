from fastapi import APIRouter, Depends

from .. import schemas
from ..deps import AppState, get_state

router = APIRouter(tags=["meta"])


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}


@router.get("/meta", response_model=schemas.Meta)
def meta(st: AppState = Depends(get_state)) -> schemas.Meta:
    g = st.graph
    return schemas.Meta(
        cycle=g.meta.get("cycle"),
        area=g.meta.get("area"),
        built_at=g.meta.get("built_at"),
        nodes=len(g),
        edges=len(g.edges),
        airports=len(g.by_icao),
    )
