"""Monta o planejador HTML standalone.

Consome os dicts crus dos extractors e monta o payload compacto que o
JS do planejador espera:

    { "n": nodes,   # [ident, lat, lon, kind, name]
      "e": edges,   # [a, b, km, airway]  (a,b = indices em n)
      "p": procs,   # { icao: [[kind, name, transition, pts], ...] }
                    #   pts = [[node_id, path_term, altitude_ft, alt_desc], ...]
      "r": rwys }   # { icao: [[bearing, length_ft, elevation_ft], ...] }

O payload e comprimido (gzip) e embutido em base64 no template, junto do
rotulo de ciclo. Nada aqui reprocessa o banco: recebe os dicts prontos.
"""
from __future__ import annotations

import base64
import gzip
import json
from pathlib import Path

from .extractors import gc_km

TEMPLATE = Path(__file__).parent / "templates" / "planner.html"

_PROC_KIND = {"sids": "S", "stars": "T", "approaches": "A"}


def _build_payload(data: dict[str, object], areas: tuple[str, ...] | None) -> dict:
    """Constroi {n,e,p,r} a partir dos dicts de parametros."""
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

    # filtro opcional por area (prefixo ICAO, ex.: "SB" para Brasil)
    keep = tuple(a.strip().upper() for a in areas) if areas else None

    def area_box():
        pts = [(a["lat"], a["lon"]) for a in data["airports"]
               if a["icao"].startswith(keep)]
        if not pts:
            return (-90.0, 90.0, -180.0, 180.0)
        m = 3.0
        return (min(p[0] for p in pts) - m, max(p[0] for p in pts) + m,
                min(p[1] for p in pts) - m, max(p[1] for p in pts) + m)

    box = area_box() if keep else None

    def in_box(lat, lon):
        return box is None or (box[0] <= lat <= box[1] and box[2] <= lon <= box[3])

    # arestas de aerovia
    edges: list = []
    for a in data["airways"]:
        if keep and not (in_box(a["from_lat"], a["from_lon"])
                         or in_box(a["to_lat"], a["to_lon"])):
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

    # conectores terminais: liga cada aeroporto aos 2 fixos de aerovia mais
    # proximos (<=250 km) para o roteador entrar/sair da malha
    awy_nodes = [i for i in range(len(nodes)) if nodes[i][3] == "W"]
    for icao, ai in apt_ids.items():
        la, lo = nodes[ai][1], nodes[ai][2]
        best = []
        for j in awy_nodes:
            if abs(nodes[j][1] - la) > 2.0 or abs(nodes[j][2] - lo) > 2.5:
                continue
            best.append((gc_km(la, lo, nodes[j][1], nodes[j][2]), j))
        best.sort()
        for km, j in best[:2]:
            if km <= 250:
                edges.append([ai, j, round(km, 3), ""])

    # pistas
    rwys: dict[str, list] = {}
    for icao in apt_ids:
        rs = data["runways"].get(icao)
        if rs:
            rwys[icao] = [[r["bearing"], r["length_ft"], r["elevation_ft"]] for r in rs]

    # procedimentos (SID/STAR/APPR)
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
                if len(pts) < 2:
                    continue
                procs.setdefault(icao, []).append(
                    [kind, p["name"], p["transition"], pts]
                )

    return {"n": nodes, "e": edges, "p": procs, "r": rwys}


def build_html(data: dict[str, object], out_path: Path, cycle: str,
               areas: tuple[str, ...] | None = None) -> dict:
    """Monta o payload, injeta no template e grava o HTML. Retorna metricas."""
    payload = _build_payload(data, areas)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    packed = base64.b64encode(gzip.compress(raw.encode(), 9)).decode()

    template = TEMPLATE.read_text(encoding="utf-8")
    html = template.replace("__PACKED__", packed).replace("__CYCLE__", cycle)
    out_path.write_text(html, encoding="utf-8")

    return {
        "nodes": len(payload["n"]),
        "edges": len(payload["e"]),
        "procs": sum(len(v) for v in payload["p"].values()),
        "raw_mb": len(raw) / 1e6,
        "packed_mb": len(packed) / 1e6,
        "html_mb": out_path.stat().st_size / 1e6,
    }
