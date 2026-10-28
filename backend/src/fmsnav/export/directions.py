"""Aplica o sentido das aerovias (eAIP, fmsnav.aip) nas arestas do navgraph.

Cada aresta ganha um 5o campo: "" = mao dupla, ">" = so de a para b,
"<" = so de b para a. Arestas sem trecho na AIP (fora do Brasil, conectores)
ficam "" — a AIP brasileira so cobre o espaco aereo brasileiro.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from ..aip import Segment

BOTH, FORWARD, BACKWARD = "", ">", "<"


def apply_directions(graph: dict, segments: Iterable[Segment]) -> dict:
    """Marca as arestas de sentido unico; retorna contagens e trechos sem perna."""
    idents = [n[0] for n in graph["n"]]
    edges = graph["e"]
    by_leg: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    for i, e in enumerate(edges):
        if e[3]:
            by_leg[(e[3], idents[e[0]], idents[e[1]])].append(i)
    for e in edges:
        if len(e) < 5:
            e.append(BOTH)

    report = {"segments": 0, "one_way": 0, "marked": 0, "missing": []}
    for s in segments:
        report["segments"] += 1
        found = [(i, True) for i in by_leg.get((s.route, s.start, s.end), ())]
        found += [(i, False) for i in by_leg.get((s.route, s.end, s.start), ())]
        if not found:
            report["missing"].append(f"{s.route} {s.start}-{s.end}")
            continue
        if not s.one_way:
            continue
        report["one_way"] += 1
        for i, same in found:
            # `forward` e o sentido da tabela da AIP (start -> end)
            edges[i][4] = FORWARD if s.forward == same else BACKWARD
            report["marked"] += 1
    return report
