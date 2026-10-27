"""Extractors: uma funcao por parametro do banco.

Cada extrator recebe o FmsDatabase e devolve uma estrutura Python
serializavel em JSON. Nenhuma escrita de arquivo aqui — isso e do
json_export. Assim cada parametro pode ser testado e regenerado sozinho.

Os JSONs sao "crus" (uma lista/dic por parametro). A montagem do grafo
compacto usado pelo HTML fica no html_builder, que consome estes dicts.
"""
from __future__ import annotations

from math import asin, cos, radians, sin, sqrt

from .reader import FmsDatabase


def gc_km(lat1, lon1, lat2, lon2):
    """Distancia great-circle em km."""
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * 6371.0088 * asin(sqrt(h))


def rwy_ident(bearing: float | None) -> str:
    """Cabeceira 'RWnn' a partir da proa magnetica (ex.: 342 -> '34')."""
    if not bearing:
        return ""
    return str(round(bearing / 10) or 36).zfill(2)


# --------------------------------------------------------------------------
# um extrator por parametro
# --------------------------------------------------------------------------
def extract_airports(db: FmsDatabase) -> list[dict]:
    """Aeroportos: ICAO + posicao."""
    out = []
    for a in db.airports:
        out.append({"icao": a.icao, "lat": round(a.lat, 5), "lon": round(a.lon, 5)})
    out.sort(key=lambda r: r["icao"])
    return out


def extract_runways(db: FmsDatabase) -> dict[str, list[dict]]:
    """Pistas por aeroporto: cabeceira, proa, comprimento, elevacao."""
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
    """Waypoints (en-route + terminais) referenciados por aerovias e
    procedimentos. Deduplicados por (ident, lat, lon)."""
    seen: dict[tuple, dict] = {}

    def add(fix, kind):
        if fix is None:
            return
        key = (fix.ident, round(fix.lat, 5), round(fix.lon, 5))
        if key not in seen:
            seen[key] = {
                "ident": fix.ident,
                "lat": round(fix.lat, 5),
                "lon": round(fix.lon, 5),
                "kind": kind,
            }

    for leg in db.airways():
        add(leg.frm, "W")
        add(leg.to, "W")
    for it in (db.sids(), db.stars(), db.approaches()):
        for p in it:
            for leg in p.legs:
                add(leg.fix, "P")
    return list(seen.values())


def extract_airways(db: FmsDatabase) -> list[dict]:
    """Pernas de aerovia: designador + par de fixos + distancia."""
    out = []
    for leg in db.airways():
        out.append(
            {
                "airway": leg.airway,
                "from": leg.frm.ident,
                "from_lat": round(leg.frm.lat, 5),
                "from_lon": round(leg.frm.lon, 5),
                "to": leg.to.ident,
                "to_lat": round(leg.to.lat, 5),
                "to_lon": round(leg.to.lon, 5),
                "km": round(gc_km(leg.frm.lat, leg.frm.lon, leg.to.lat, leg.to.lon), 3),
            }
        )
    return out


def _procedures(db: FmsDatabase, kind: str, iterator) -> dict[str, list[dict]]:
    """Comum a SID/STAR/APPR. Agrupa por aeroporto; cada procedimento traz
    seus pontos com restricao de altitude ja decodificada."""
    out: dict[str, list[dict]] = {}
    for p in iterator:
        pts = []
        for leg in p.legs:
            if leg.fix is None:
                continue
            pts.append(
                {
                    "ident": leg.fix.ident,
                    "lat": round(leg.fix.lat, 5),
                    "lon": round(leg.fix.lon, 5),
                    "path_term": leg.path_term,
                    "altitude_ft": leg.altitude_ft or 0,
                    "alt_desc": leg.alt_desc,   # '+', '-', '', 'B'
                }
            )
        if len(pts) < 2:
            continue
        out.setdefault(p.airport, []).append(
            {"name": p.name, "transition": p.transition, "points": pts}
        )
    return out


def extract_sids(db: FmsDatabase) -> dict[str, list[dict]]:
    return _procedures(db, "SID", db.sids())


def extract_stars(db: FmsDatabase) -> dict[str, list[dict]]:
    return _procedures(db, "STAR", db.stars())


def extract_approaches(db: FmsDatabase) -> dict[str, list[dict]]:
    return _procedures(db, "APPR", db.approaches())


# registro central: nome do parametro -> extrator. O build itera isto,
# entao adicionar um parametro novo e so registrar aqui.
EXTRACTORS = {
    "airports": extract_airports,
    "runways": extract_runways,
    "waypoints": extract_waypoints,
    "airways": extract_airways,
    "sids": extract_sids,
    "stars": extract_stars,
    "approaches": extract_approaches,
}
