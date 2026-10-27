"""Contrato HTTP. Espelhado em frontend/src/api/types.ts."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AltDesc = Literal["+", "-", "", "B"]
# H = so aerovias de alta (designador comeca com U), L = so baixa, null = todas
AirwayLevel = Literal["H", "L"]


class Altitude(BaseModel):
    ft: int
    desc: AltDesc


class Point(BaseModel):
    id: int | None = Field(description="indice do no no grafo; null para ponto virtual")
    ident: str
    lat: float
    lon: float
    kind: str = Field(description="W aerovia, A aeroporto, P procedimento, V virtual")
    altitude: Altitude | None = None


class PointRef(BaseModel):
    """Referencia a um ponto: por id, por coordenada (virtual) ou por ident."""
    id: int | None = None
    ident: str | None = None
    lat: float | None = None
    lon: float | None = None


class RouteLeg(BaseModel):
    airway: str = Field(description='designador da aerovia; "" quando nao ha')
    km: float


class Procedure(BaseModel):
    key: str
    name: str
    transition: str
    label: str
    runway_transitions: list[str]


class ChosenProcedure(Procedure):
    chain: list[Point]


class EditedCore(BaseModel):
    path: list[PointRef]
    fallback: tuple[int, int]


class RouteIn(BaseModel):
    origin: str
    destination: str
    runway_dep: str | None = None
    runway_arr: str | None = None
    sid: str | None = Field(None, description='chave da SID, "auto" ou null')
    star: str | None = Field(None, description='chave da STAR, "auto" ou null')
    avoid_notams: bool = True
    level: AirwayLevel | None = None
    edited: EditedCore | None = None


class RouteOut(BaseModel):
    points: list[Point]
    legs: list[RouteLeg]
    km: float
    direct_km: float
    sid: ChosenProcedure | None = None
    star: ChosenProcedure | None = None
    avoidance_applied: bool = False
    warnings: list[str] = []


class AnnotateIn(BaseModel):
    points: list[PointRef]
    level: AirwayLevel | None = Field(None, description="nivel preferido ao rotular aerovias")


class AnnotateOut(BaseModel):
    points: list[Point]
    legs: list[RouteLeg]
    km: float


class Runway(BaseModel):
    ident: str
    bearing: float
    length_ft: int
    elevation_ft: int


class Airport(BaseModel):
    icao: str
    lat: float
    lon: float
    procedures: int


class AirportDetail(Airport):
    runways: list[Runway]


class Network(BaseModel):
    edges: list[tuple[float, float, float, float]]
    fixes: list[tuple[str, float, float]]
    truncated: bool


class NotamArea(BaseModel):
    number: str
    fir: str
    status: str
    text: str
    polygon: list[tuple[float, float]]


class Meta(BaseModel):
    cycle: str | None
    area: list[str] | None
    built_at: str | None
    nodes: int
    edges: int
    airports: int
