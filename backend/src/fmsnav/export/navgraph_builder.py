"""Compila os parametros extraidos no grafo de rotas (navgraph).

Formato (JSON gzipado, lido por fmsnav.navgraph.NavGraph):

    { "format": 1,
      "meta":  { "cycle", "area", "built_at", "directions" },
      "graph": {
        "n": nodes,   # [ident, lat, lon, kind, name]   kind: W=aerovia A=aeroporto P=procedimento
        "e": edges,   # [a, b, km, airway, sentido]      (a,b = indices em n; airway "" = conector;
                      #   sentido "" = mao dupla, ">" so a->b, "<" so b->a — da eAIP, export.directions)
        "p": procs,   # { icao: [[kind, name, transition, pts], ...] }   kind: S=SID T=STAR A=APPR
                      #   pts = [[node, path_term, altitude_ft, alt_desc], ...]
        "r": rwys }}  # { icao: [[bearing, length_ft, elevation_ft], ...] }
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

from ..geo import haversine_km

FORMAT_VERSION = 1

_PROC_KIND = {"sids": "S", "stars": "T", "approaches": "A"}

# conectores terminais: cada aeroporto liga aos N fixos de aerovia mais proximos
CONNECTORS_PER_AIRPORT = 2
CONNECTOR_MAX_KM = 250
# margem (graus) em volta dos aeroportos da area filtrada
AREA_MARGIN_DEG = 3.0


def build_navgraph(data: dict[str, object], areas: tuple[str, ...] | None = None) -> dict:
    """Constroi {n,e,p,r} a partir dos dicts dos extractors."""
    idx: dict[tuple, int] = {}
    nodes: list = []

    def node_id(ident, lat, lon, kind, name=""):
        key = (round(lat, 5), round(lon, 5), ident)
        g = idx.get(key)
        if g is None:
            g = len(nodes)
            idx[key] = g
            nodes.append([ident, round(lat, 5), round(lon, 5), kind, name])
        return g

    keep = tuple(a.strip().upper() for a in areas) if areas else None
    box = _area_box(data["airports"], keep) if keep else None

    def in_box(lat, lon):
        return box is None or (box[0] <= lat <= box[1] and box[2] <= lon <= box[3])

    # arestas de aerovia
    edges: list = []
    for a in data["airways"]:
        if keep and not (in_box(a["from_lat"], a["from_lon"]) or in_box(a["to_lat"], a["to_lon"])):
            continue
        u = node_id(a["from"], a["from_lat"], a["from_lon"], "W")
        v = node_id(a["to"], a["to_lat"], a["to_lon"], "W")
        if u != v:
            edges.append([u, v, a["km"], a["airway"] or ""])

    # aeroportos
    apt_ids: dict[str, int] = {}
    for a in data["airports"]:
        if keep and not a["icao"].startswith(keep):
            continue
        apt_ids[a["icao"]] = node_id(a["icao"], a["lat"], a["lon"], "A", a["icao"])

    # conectores terminais para o roteador entrar/sair da malha
    awy_nodes = [i for i in range(len(nodes)) if nodes[i][3] == "W"]
    for ai in apt_ids.values():
        la, lo = nodes[ai][1], nodes[ai][2]
        best = []
        for j in awy_nodes:
            if abs(nodes[j][1] - la) > 2.0 or abs(nodes[j][2] - lo) > 2.5:
                continue
            best.append((haversine_km(la, lo, nodes[j][1], nodes[j][2]), j))
        best.sort()
        for km, j in best[:CONNECTORS_PER_AIRPORT]:
            if km <= CONNECTOR_MAX_KM:
                edges.append([ai, j, round(km, 3), ""])

    rwys: dict[str, list] = {}
    for icao in apt_ids:
        rs = data["runways"].get(icao)
        if rs:
            rwys[icao] = [[r["bearing"], r["length_ft"], r["elevation_ft"]] for r in rs]

    procs: dict[str, list] = {}
    for param, kind in _PROC_KIND.items():
        for icao, plist in data[param].items():
            if icao not in apt_ids:
                continue
            for p in plist:
                pts = [
                    [node_id(pt["ident"], pt["lat"], pt["lon"], "P"),
                     pt["path_term"], pt["altitude_ft"], pt["alt_desc"]]
                    for pt in p["points"]
                ]
                if len(pts) >= 2:
                    procs.setdefault(icao, []).append([kind, p["name"], p["transition"], pts])

    return {"n": nodes, "e": edges, "p": procs, "r": rwys}


def _area_box(airports, keep):
    pts = [(a["lat"], a["lon"]) for a in airports if a["icao"].startswith(keep)]
    if not pts:
        return (-90.0, 90.0, -180.0, 180.0)
    m = AREA_MARGIN_DEG
    return (min(p[0] for p in pts) - m, max(p[0] for p in pts) + m,
            min(p[1] for p in pts) - m, max(p[1] for p in pts) + m)


def write_navgraph(graph: dict, path: Path, cycle: str, areas: tuple[str, ...] | None,
                   directions: dict | None = None) -> dict:
    doc = {
        "format": FORMAT_VERSION,
        "meta": {
            "cycle": cycle,
            "area": list(areas) if areas else None,
            "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "directions": directions,
        },
        "graph": graph,
    }
    raw = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(raw, 6))
    return {
        "nodes": len(graph["n"]),
        "edges": len(graph["e"]),
        "procs": sum(len(v) for v in graph["p"].values()),
        "raw_mb": len(raw) / 1e6,
        "file_mb": path.stat().st_size / 1e6,
    }
