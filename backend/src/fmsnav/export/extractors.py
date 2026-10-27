"""Extractors: uma funcao por parametro do banco.

Cada extrator recebe o FmsDatabase e devolve uma estrutura serializavel em
JSON. Nenhuma escrita de arquivo aqui. Para adicionar um parametro novo,
escreva extract_<param>(db) e registre em EXTRACTORS.
"""
from __future__ import annotations

from ..decode import FmsDatabase
from ..geo import haversine_km


def rwy_ident(bearing: float | None) -> str:
    """Cabeceira 'nn' a partir da proa magnetica (ex.: 342 -> '34')."""
    if not bearing:
        return ""
    return str(round(bearing / 10) or 36).zfill(2)


def extract_airports(db: FmsDatabase) -> list[dict]:
    out = [{"icao": a.icao, "lat": round(a.lat, 5), "lon": round(a.lon, 5)} for a in db.airports]
    out.sort(key=lambda r: r["icao"])
    return out


def extract_runways(db: FmsDatabase) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for a in db.airports:
        rs = db.runways_of(a.icao)
        if not rs:
            continue
        out[a.icao] = [
            {
                "ident": rwy_ident(r.bearing),
                "bearing": round(r.bearing or 0, 1),
                "length_ft": r.length_ft,
                "elevation_ft": r.elevation_ft,
            }
            for r in rs
        ]
    return out


def extract_waypoints(db: FmsDatabase) -> list[dict]:
    """Waypoints referenciados por aerovias (W) e procedimentos (P),
    deduplicados por (ident, lat, lon)."""
    seen: dict[tuple, dict] = {}

    def add(fix, kind):
        if fix is None:
            return
        key = (fix.ident, round(fix.lat, 5), round(fix.lon, 5))
        if key not in seen:
            seen[key] = {"ident": fix.ident, "lat": key[1], "lon": key[2], "kind": kind}

    for leg in db.airways():
        add(leg.frm, "W")
        add(leg.to, "W")
    for it in (db.sids(), db.stars(), db.approaches()):
        for p in it:
            for leg in p.legs:
                add(leg.fix, "P")
    return list(seen.values())


def extract_airways(db: FmsDatabase) -> list[dict]:
    return [
        {
            "airway": leg.airway,
            "from": leg.frm.ident,
            "from_lat": round(leg.frm.lat, 5),
            "from_lon": round(leg.frm.lon, 5),
            "to": leg.to.ident,
            "to_lat": round(leg.to.lat, 5),
            "to_lon": round(leg.to.lon, 5),
            "km": round(haversine_km(leg.frm.lat, leg.frm.lon, leg.to.lat, leg.to.lon), 3),
        }
        for leg in db.airways()
    ]


def _procedures(iterator) -> dict[str, list[dict]]:
    """Comum a SID/STAR/APPR: agrupa por aeroporto, so pernas com posicao."""
    out: dict[str, list[dict]] = {}
    for p in iterator:
        pts = [
            {
                "ident": leg.fix.ident,
                "lat": round(leg.fix.lat, 5),
                "lon": round(leg.fix.lon, 5),
                "path_term": leg.path_term,
                "altitude_ft": leg.altitude_ft or 0,
                "alt_desc": leg.alt_desc,
            }
            for leg in p.legs if leg.fix is not None
        ]
        if len(pts) < 2:
            continue
        out.setdefault(p.airport, []).append(
            {"name": p.name, "transition": p.transition, "points": pts}
        )
    return out


def extract_sids(db: FmsDatabase) -> dict[str, list[dict]]:
    return _procedures(db.sids())


def extract_stars(db: FmsDatabase) -> dict[str, list[dict]]:
    return _procedures(db.stars())


def extract_approaches(db: FmsDatabase) -> dict[str, list[dict]]:
    return _procedures(db.approaches())


EXTRACTORS = {
    "airports": extract_airports,
    "runways": extract_runways,
    "waypoints": extract_waypoints,
    "airways": extract_airways,
    "sids": extract_sids,
    "stars": extract_stars,
    "approaches": extract_approaches,
}
