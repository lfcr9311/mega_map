from fastapi import APIRouter, Depends

from .. import schemas
from ..deps import AppState, get_state

router = APIRouter(tags=["notams"])


@router.get("/notams", response_model=list[schemas.NotamArea])
async def notams(st: AppState = Depends(get_state)):
    """Areas de NOTAM consideradas no desvio de rota."""
    return [
        schemas.NotamArea(number=a.number, fir=a.fir, status=a.status, text=a.text,
                          polygon=list(a.zone.polygon))
        for a in await st.notams.areas()
    ]


@router.get("/special-areas")
async def special_areas(st: AppState = Depends(get_state)) -> list[dict]:
    """Repasse das areas especiais do rpl_back (so exibicao)."""
    return await st.notams.special_areas()
