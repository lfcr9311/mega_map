from fastapi import APIRouter, Depends, Query

from .. import schemas
from ..schemas import AirwayLevel
from ..deps import AppState, get_state

router = APIRouter(tags=["network"])

MAX_EDGES = 40_000
MAX_FIXES = 4_000


@router.get("/network", response_model=schemas.Network)
def network(south: float, west: float, north: float, east: float,
            fixes: bool = Query(False, description="incluir fixos (para rotulos)"),
            level: AirwayLevel | None = Query(None, description="so aerovias de alta (H) ou baixa (L)"),
            st: AppState = Depends(get_state)):
    """Malha de aerovias (e opcionalmente os fixos) dentro da caixa."""
    g = st.graph
    edges, truncated = [], False
    for a, b in g.edges_in_bbox(south, west, north, east, level):
        if len(edges) >= MAX_EDGES:
            truncated = True
            break
        edges.append((g.lats[a], g.lons[a], g.lats[b], g.lons[b]))
    out_fixes = []
    if fixes:
        for i in g.nodes_in_bbox(south, west, north, east):
            if g.kinds[i] == "A":
                continue
            if len(out_fixes) >= MAX_FIXES:
                truncated = True
                break
            out_fixes.append((g.idents[i], g.lats[i], g.lons[i]))
    return schemas.Network(edges=edges, fixes=out_fixes, truncated=truncated)
