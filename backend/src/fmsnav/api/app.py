"""Aplicacao FastAPI: carrega o grafo uma vez e expoe /api/*.

Se frontend/dist existir (npm run build), tambem serve o frontend em /.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from ..navgraph import NavGraph
from ..notams import NotamService, RplBackClient
from ..routing import RoutePlanner
from ..settings import Settings
from .deps import AppState
from .routers import airports, meta, network, notams, routes

log = logging.getLogger("fmsnav")


def create_app(settings: Settings | None = None, graph: NavGraph | None = None,
               notam_service: NotamService | None = None) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        g = graph
        if g is None:
            if not settings.graph_path.exists():
                raise RuntimeError(
                    f"grafo nao encontrado em {settings.graph_path}. "
                    "Rode `fmsnav build <zip do ciclo>` ou defina FMSNAV_GRAPH."
                )
            log.info("carregando grafo %s", settings.graph_path)
            g = NavGraph.load(settings.graph_path)
        client = None
        svc = notam_service
        if svc is None:
            client = RplBackClient(settings.rpl_back_url) if settings.rpl_back_url else None
            svc = NotamService(client, settings.notam_icaos, settings.notam_minutes,
                               settings.notam_ttl_s, settings.demo_notams)
        app.state.fmsnav = AppState(graph=g, planner=RoutePlanner(g), notams=svc)
        log.info("pronto: %d nos, ciclo %s", len(g), g.meta.get("cycle"))
        yield
        if client:
            await client.aclose()

    app = FastAPI(title="fmsnav", version="0.2.0", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins),
                       allow_methods=["*"], allow_headers=["*"])
    for r in (meta, airports, network, routes, notams):
        app.include_router(r.router, prefix="/api")

    if settings.frontend_dist.is_dir():
        app.mount("/", StaticFiles(directory=settings.frontend_dist, html=True), name="frontend")
    return app
