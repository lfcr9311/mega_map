"""CLI: fmsnav build | serve | route"""
from __future__ import annotations

import argparse
import logging


def _build(a: argparse.Namespace) -> None:
    from .pipeline import build
    build(a.zip, out=a.out, cycle=a.cycle,
          area=a.area.split(",") if a.area else None, write_json=not a.no_json)


def _serve(a: argparse.Namespace) -> None:
    import os

    import uvicorn
    if a.graph:
        os.environ["FMSNAV_GRAPH"] = a.graph
    uvicorn.run("fmsnav.api.app:create_app", factory=True, host=a.host, port=a.port, reload=a.reload)


def _route(a: argparse.Namespace) -> None:
    from .navgraph import NavGraph
    from .routing import RoutePlanner, RouteRequest
    from .settings import Settings

    g = NavGraph.load(a.graph or Settings.from_env().graph_path)
    res = RoutePlanner(g).plan(RouteRequest(a.origin, a.destination, a.rwy_dep, a.rwy_arr, a.sid, a.star,
                                            level=a.level))
    for w in res.warnings:
        print("!", w)
    if res.sid:
        print("SID ", res.sid.label)
    if res.star:
        print("STAR", res.star.label)
    for x, y in zip(res.points, res.points[1:]):
        print(f"  {g.ident(x):>6} -> {g.ident(y):<6} {g.airway_between(x, y, a.level) or '·':<7} {g.distance_km(x, y):7.1f} km")
    print(f"total {res.km:,.0f} km (ortodromica {res.direct_km:,.0f} km)")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="fmsnav")
    sub = ap.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="decodifica o zip do ciclo e compila o grafo")
    b.add_argument("zip", help="zip (ou diretorio) do ciclo com os .S01")
    b.add_argument("--cycle", required=True, help="rotulo do ciclo AIRAC, ex.: 2607")
    b.add_argument("--out", default="data/build", help="diretorio de saida (default data/build)")
    b.add_argument("--area", help="prefixo(s) ICAO separados por virgula, ex.: SB")
    b.add_argument("--no-json", action="store_true", help="nao gravar db/*.json por parametro")
    b.set_defaults(fn=_build)

    s = sub.add_parser("serve", help="sobe a API (e o frontend, se compilado)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8001)
    s.add_argument("--graph", help="caminho do navgraph.json.gz (ou FMSNAV_GRAPH)")
    s.add_argument("--reload", action="store_true")
    s.set_defaults(fn=_serve)

    r = sub.add_parser("route", help="calcula uma rota no terminal (sem NOTAMs)")
    r.add_argument("origin")
    r.add_argument("destination")
    r.add_argument("--rwy-dep")
    r.add_argument("--rwy-arr")
    r.add_argument("--sid", help='chave ou "auto"')
    r.add_argument("--star", help='chave ou "auto"')
    r.add_argument("--level", choices=["H", "L"], help="so aerovias de alta (U...) ou baixa")
    r.add_argument("--graph")
    r.set_defaults(fn=_route)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
