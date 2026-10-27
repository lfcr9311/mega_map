"""Extracao de poligonos do texto de NOTAM (campo E)."""
from __future__ import annotations

import re

from ..geo import LatLon

_COORD = re.compile(r"(\d{2})(\d{2})(\d{2})([NS])(\d{3})(\d{2})(\d{2})([EW])")
_COORD_TOKEN = re.compile(r"\d{6}[NS]\d{7}[EW]")


def parse_coord(token: str) -> LatLon | None:
    """'294948S0570127W' -> (-29.83, -57.02)."""
    m = _COORD.search(token)
    if not m:
        return None
    lad, lam, las, lah, lod, lom, los, loh = m.groups()
    lat = int(lad) + int(lam) / 60 + int(las) / 3600
    lon = int(lod) + int(lom) / 60 + int(los) / 3600
    return (-lat if lah == "S" else lat, -lon if loh == "W" else lon)


def coords_from_text(text: str | None) -> list[LatLon]:
    if not text:
        return []
    return [c for c in map(parse_coord, _COORD_TOKEN.findall(text)) if c]


def polygon_from_notam(notam: dict) -> list[LatLon]:
    """Poligono do NOTAM: coordenadas do texto E, ou geometry GeoJSON ([lon, lat])."""
    coords = coords_from_text(notam.get("textE"))
    if len(coords) >= 3:
        return coords
    ring = ((notam.get("geometry") or {}).get("coordinates") or [[]])[0]
    return [(c[1], c[0]) for c in ring]
