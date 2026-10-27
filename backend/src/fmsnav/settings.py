"""Configuracao por variaveis de ambiente (prefixo FMSNAV_)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"FMSNAV_{name}", default)


def _csv(value: str) -> tuple[str, ...]:
    return tuple(x.strip() for x in value.split(",") if x.strip())


@dataclass(frozen=True)
class Settings:
    graph_path: Path
    rpl_back_url: str | None
    notam_icaos: tuple[str, ...]
    notam_minutes: int
    notam_ttl_s: float
    demo_notams: bool
    cors_origins: tuple[str, ...]
    frontend_dist: Path

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            graph_path=Path(_env("GRAPH", str(REPO_ROOT / "data/build/navgraph.json.gz"))),
            rpl_back_url=_env("RPL_BACK_URL", "http://localhost:8000") or None,
            notam_icaos=_csv(_env("NOTAM_ICAOS", "SBCW,SBBS,SBRE,SBAZ")),
            notam_minutes=int(_env("NOTAM_MINUTES", "120000")),
            notam_ttl_s=float(_env("NOTAM_TTL_S", "300")),
            demo_notams=_env("DEMO_NOTAMS", "0") == "1",
            cors_origins=_csv(_env("CORS_ORIGINS", "http://localhost:5173")),
            frontend_dist=Path(_env("FRONTEND_DIST", str(REPO_ROOT / "frontend/dist"))),
        )
