"""Objetos de dominio produzidos pelo decoder."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Fix:
    ident: str
    lat: float
    lon: float
    kind: str          # WPT_ENRT, WPT_TERM, VOR_DME, NDB, DME, VOR, AIRPORT, RUNWAY

    def __repr__(self) -> str:
        return f"{self.ident}({self.lat:.4f},{self.lon:.4f})"


@dataclass(frozen=True, slots=True)
class Airport:
    icao: str
    lat: float
    lon: float


@dataclass(frozen=True, slots=True)
class Runway:
    airport_idx: int
    lat: float
    lon: float
    bearing: float | None      # graus magneticos
    length_ft: int
    elevation_ft: int


@dataclass(frozen=True, slots=True)
class Leg:
    """Uma perna de procedimento (SID, STAR ou aproximacao)."""

    seq: int
    path_term: str             # TF, CF, DF, CA, VI, ...
    fix: Fix | None
    altitude_ft: int | None
    alt_desc: str              # '+' (ou acima), '-' (ou abaixo), '' (exata), 'B' (janela)
    distance_nm: float | None
    rnp: float | None

    @property
    def has_position(self) -> bool:
        return self.fix is not None


@dataclass(frozen=True, slots=True)
class Procedure:
    kind: str                  # SID, STAR, APPR
    airport: str
    name: str
    transition: str
    legs: tuple[Leg, ...]

    @property
    def fixes(self) -> tuple[Fix, ...]:
        return tuple(l.fix for l in self.legs if l.fix is not None)


@dataclass(frozen=True, slots=True)
class AirwayLeg:
    airway: str
    frm: Fix
    to: Fix
