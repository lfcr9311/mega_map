r"""Grafo sintetico pequeno para testes de roteamento e API.

    AAAA ---- W1 ---- W2 ---- W3 ---- BBBB        (UX1, alta, ao longo do equador)
                \                /
                 W4 ---------- W5                  (W12, baixa, desvio ao sul)

SID de AAAA: runway transition RW09 (R1 -> S1) + en-route S1 -> W1.
STAR de BBBB: en-route W3 -> T1 + runway transition RW27 (T1 -> R2).
"""
from pathlib import Path

import pytest

from fmsnav.navgraph import NavGraph

NODES = [
    ["AAAA", 0.0, 0.0, "A", "AAAA"],   # 0
    ["W1", 0.0, 1.0, "W", ""],         # 1
    ["W2", 0.0, 2.0, "W", ""],         # 2
    ["W3", 0.0, 3.0, "W", ""],         # 3
    ["BBBB", 0.0, 4.0, "A", "BBBB"],   # 4
    ["W4", -1.0, 1.5, "W", ""],        # 5
    ["W5", -1.0, 2.5, "W", ""],        # 6
    ["R1", 0.0, 0.05, "P", ""],        # 7
    ["S1", 0.1, 0.5, "P", ""],         # 8
    ["T1", 0.1, 3.5, "P", ""],         # 9
    ["R2", 0.0, 3.95, "P", ""],        # 10
]


def _km(a, b):
    from fmsnav.geo import haversine_km
    return haversine_km(NODES[a][1], NODES[a][2], NODES[b][1], NODES[b][2])


EDGES = [
    [1, 2, _km(1, 2), "UX1"], [2, 3, _km(2, 3), "UX1"],
    [1, 5, _km(1, 5), "W12"], [5, 6, _km(5, 6), "W12"], [6, 3, _km(6, 3), "W12"],
    [0, 1, _km(0, 1), ""], [4, 3, _km(4, 3), ""],
]

PROCS = {
    "AAAA": [
        ["S", "SID1A", "RW09", [[7, "IF", 0, ""], [8, "TF", 3000, "+"]]],
        ["S", "SID1A", "W1", [[8, "TF", 0, ""], [1, "TF", 9000, "-"]]],
    ],
    "BBBB": [
        ["T", "STR1A", "W3", [[3, "IF", 0, ""], [9, "TF", 5000, ""]]],
        ["T", "STR1A", "RW27", [[9, "TF", 0, ""], [10, "TF", 1500, "B"]]],
    ],
}

RUNWAYS = {"AAAA": [[90.0, 9000, 100]], "BBBB": [[270.0, 8000, 200]]}


@pytest.fixture
def graph() -> NavGraph:
    return NavGraph({"n": NODES, "e": EDGES, "p": PROCS, "r": RUNWAYS}, {"cycle": "TEST"})


REAL_GRAPH = Path(__file__).resolve().parents[2] / "data/build/navgraph.json.gz"


@pytest.fixture(scope="session")
def real_graph() -> NavGraph:
    if not REAL_GRAPH.exists():
        pytest.skip("navgraph real nao compilado (fmsnav build)")
    return NavGraph.load(REAL_GRAPH)
