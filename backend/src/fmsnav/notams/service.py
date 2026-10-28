"""Areas restritas por NOTAM: busca no rpl_back, cache e indexacao no grafo."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from ..navgraph import NavGraph
from ..routing import Avoidance, AvoidZone
from .client import RplBackClient
from .parsing import polygon_from_notam

log = logging.getLogger(__name__)

# poligonos ficticios, so com FMSNAV_DEMO_NOTAMS=1 (para testar o desvio sem o rpl_back)
DEMO_NOTAMS = [
    {"number": "DEMO-001", "fir": "SBCW", "status": "demo", "textE": "Área de restrição fictícia",
     "geometry": {"coordinates": [[[-47.5, -15.8], [-47.3, -15.8], [-47.3, -16.0], [-47.5, -16.0], [-47.5, -15.8]]]}},
    {"number": "DEMO-002", "fir": "SBBS", "status": "demo", "textE": "Área proibida fictícia",
     "geometry": {"coordinates": [[[-48.2, -23.6], [-48.0, -23.6], [-48.0, -23.8], [-48.2, -23.8], [-48.2, -23.6]]]}},
]


@dataclass(frozen=True)
class NotamArea:
    number: str
    fir: str
    status: str
    text: str
    zone: AvoidZone


class NotamService:
    def __init__(self, client: RplBackClient | None, icaos: tuple[str, ...],
                 minutes: int, ttl_s: float, demo: bool = False):
        self.client = client
        self.icaos = icaos
        self.minutes = minutes
        self.ttl_s = ttl_s
        self.demo = demo
        self._areas: list[NotamArea] = []
        # None = nunca buscou (monotonic conta desde o boot: 0.0 pareceria recente)
        self._fetched_at: float | None = None
        self._lock = asyncio.Lock()
        self._avoidance: tuple[int, int, Avoidance] | None = None   # (id(areas), id(graph), ctx)

    async def areas(self) -> list[NotamArea]:
        async with self._lock:
            if self._fetched_at is None or time.monotonic() - self._fetched_at > self.ttl_s:
                self._areas = await self._fetch()
                self._fetched_at = time.monotonic()
            return self._areas

    async def avoidance(self, graph: NavGraph) -> Avoidance:
        areas = await self.areas()
        cached = self._avoidance
        if cached and cached[0] == id(areas) and cached[1] == id(graph):
            return cached[2]
        ctx = Avoidance(graph, [a.zone for a in areas])
        self._avoidance = (id(areas), id(graph), ctx)
        return ctx

    async def _fetch(self) -> list[NotamArea]:
        raw: list[dict] = []
        if self.client:
            results = await asyncio.gather(
                *(self.client.notams(icao, self.minutes) for icao in self.icaos),
                return_exceptions=True,
            )
            for icao, res in zip(self.icaos, results):
                if isinstance(res, Exception):
                    log.warning("NOTAMs de %s indisponiveis: %s", icao, res)
                else:
                    raw.extend(res)
        if not raw and self.demo:
            raw = DEMO_NOTAMS
        areas = []
        for n in raw:
            poly = polygon_from_notam(n)
            if len(poly) < 3:
                continue
            number = str(n.get("number") or n.get("numero") or f"NOTAM-{len(areas) + 1}")
            areas.append(NotamArea(
                number=number,
                fir=str(n.get("fir") or ""),
                status=str(n.get("status") or ""),
                text=str(n.get("textE") or n.get("descricao") or ""),
                zone=AvoidZone(number, tuple(poly)),
            ))
        log.info("%d areas de NOTAM carregadas", len(areas))
        return areas

    async def special_areas(self) -> list[dict]:
        if not self.client:
            return []
        try:
            return await self.client.special_areas()
        except Exception as e:  # rpl_back fora do ar nao derruba o planejador
            log.warning("areas especiais indisponiveis: %s", e)
            return []
