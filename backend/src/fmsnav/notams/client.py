"""Cliente HTTP do rpl_back (servico externo de NOTAMs e areas especiais)."""
from __future__ import annotations

import httpx


class RplBackClient:
    def __init__(self, base_url: str, timeout_s: float = 5.0):
        self._http = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=timeout_s)

    async def notams(self, icao: str, minutes: int) -> list[dict]:
        r = await self._http.get("/api/notams", params={"icaocode": icao, "minutes": minutes})
        r.raise_for_status()
        return r.json() or []

    async def special_areas(self) -> list[dict]:
        r = await self._http.get("/api/special-areas")
        r.raise_for_status()
        return r.json() or []

    async def aclose(self) -> None:
        await self._http.aclose()
