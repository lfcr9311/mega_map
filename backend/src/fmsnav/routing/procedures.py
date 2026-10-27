"""Procedimentos SID/STAR segundo a estrutura ARINC 424.

Uma SID/STAR e uma rota comum ligada as pistas por RUNWAY transitions
("RW34") e a aerovia por EN-ROUTE transitions, unidas no fixo-nome do
procedimento. Cada opcao oferecida ao usuario e um par (procedimento,
transicao en-route), carregando as runway transitions do mesmo procedimento
para montar a cadeia completa conforme a pista escolhida.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..navgraph import NavGraph, RawProcedure

SID, STAR = "S", "T"


def runway_digits(s: str | None) -> str:
    """'RW34' -> '34', '34' -> '34', 'RW09L' -> '09'."""
    return re.sub(r"[^0-9]", "", s or "")


def runway_matches(transition: str, runway: str | None) -> bool:
    if not runway:
        return False
    a = runway_digits(transition)
    return bool(a) and a == runway_digits(runway)


@dataclass(frozen=True, slots=True)
class ProcedureOption:
    kind: str                                   # S ou T
    name: str
    entry: RawProcedure                         # en-route transition (ou runway, se nao ha en-route)
    runway_transitions: tuple[RawProcedure, ...]

    @property
    def key(self) -> str:
        return f"{self.name}.{self.entry.transition}"

    @property
    def label(self) -> str:
        return f"{self.name} · {self.entry.transition}"

    def serves_runway(self, runway: str) -> bool:
        token = f"RW{runway}"
        if self.runway_transitions:
            return any(token in t.transition.upper() for t in self.runway_transitions)
        return token in self.label

    def runway_transition(self, runway: str | None) -> RawProcedure | None:
        if not self.runway_transitions:
            return None
        return next((t for t in self.runway_transitions if runway_matches(t.transition, runway)),
                    self.runway_transitions[0])

    def chain(self, runway: str | None) -> list[int]:
        """Cadeia completa de nos do procedimento para a pista dada.

        SID:  runway transition (pista -> COMMON) + en-route (COMMON -> aerovia)
        STAR: en-route (aerovia -> COMMON) + runway transition (COMMON -> pista)
        O fixo COMMON aparece nas duas partes e entra uma vez so.
        """
        ent = self.entry.nodes
        rwy = self.runway_transition(runway)
        if rwy is None:
            return ent
        if self.kind == SID:
            return rwy.nodes[:-1] + ent
        return ent + rwy.nodes[1:]

    def altitude_constraints(self, runway: str | None) -> dict[int, tuple[int, str]]:
        """node -> (altitude_ft, descritor) das partes usadas na cadeia."""
        parts = [self.entry]
        rwy = self.runway_transition(runway)
        if rwy is not None:
            parts.append(rwy)
        out: dict[int, tuple[int, str]] = {}
        for part in parts:
            for p in part.points:
                if p.altitude_ft:
                    out[p.node] = (p.altitude_ft, p.alt_desc or "")
        return out


def procedure_options(graph: NavGraph, icao: str, kind: str) -> list[ProcedureOption]:
    by_name: dict[str, tuple[list[RawProcedure], list[RawProcedure]]] = {}
    for p in graph.procedures.get(icao, ()):
        if p.kind != kind:
            continue
        ent, rwy = by_name.setdefault(p.name, ([], []))
        (rwy if p.is_runway_transition else ent).append(p)

    opts: list[ProcedureOption] = []
    for name, (ent, rwy) in by_name.items():
        if ent:
            opts.extend(ProcedureOption(kind, name, e, tuple(rwy)) for e in ent)
        else:
            # sem transicao en-route (ex.: RNAV fechado): cada runway transition vira opcao
            opts.extend(ProcedureOption(kind, name, r, ()) for r in rwy)
    return opts


def filter_by_runway(opts: list[ProcedureOption], runway: str | None) -> list[ProcedureOption]:
    if not runway:
        return opts
    return [o for o in opts if o.serves_runway(runway)]


def find_option(opts: list[ProcedureOption], key: str) -> ProcedureOption | None:
    return next((o for o in opts if o.key == key), None)
