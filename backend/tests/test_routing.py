import pytest

from fmsnav.navgraph import VirtualPoint
from fmsnav.routing import (
    AUTO, Avoidance, AvoidZone, EditedCore, PlanningError, RoutePlanner, RouteRequest,
    costs_from, procedure_options, shortest_path,
)
from fmsnav.routing.procedures import SID, STAR


def test_shortest_path_prefers_direct_airway(graph):
    res = shortest_path(graph, 0, 4)
    assert [graph.idents[i] for i in res.path] == ["AAAA", "W1", "W2", "W3", "BBBB"]


def test_blocked_node_forces_detour(graph):
    res = shortest_path(graph, 0, 4, blocked=frozenset({2}))
    assert 2 not in res.path and 5 in res.path


def test_costs_from_matches_astar(graph):
    costs = costs_from(graph, 1, [3, 4])
    assert costs[4] == pytest.approx(shortest_path(graph, 1, 4).cost)


def test_airway_designator(graph):
    assert graph.airway_between(1, 2) == "UX1"
    assert graph.airway_between(2, 1) == "UX1"
    assert graph.airway_between(0, 1) == ""


def test_procedure_chain_joins_common_fix(graph):
    sid = procedure_options(graph, "AAAA", SID)[0]
    star = procedure_options(graph, "BBBB", STAR)[0]
    assert sid.key == "SID1A.W1" and sid.serves_runway("09")
    assert sid.chain("09") == [7, 8, 1]
    assert star.chain("27") == [3, 9, 10]
    assert sid.altitude_constraints("09") == {8: (3000, "+"), 1: (9000, "-")}


def test_plan_with_auto_procedures(graph):
    res = RoutePlanner(graph).plan(RouteRequest("AAAA", "BBBB", "09", "27", AUTO, AUTO))
    assert [graph.idents[p] for p in res.points] == ["AAAA", "R1", "S1", "W1", "W2", "W3", "T1", "R2", "BBBB"]
    assert res.sid.key == "SID1A.W1" and res.star.key == "STR1A.W3"
    assert res.sid_chain == [0, 7, 8, 1] and res.star_chain == [3, 9, 10, 4]
    assert res.altitudes[10] == (1500, "B")


def test_plan_errors(graph):
    p = RoutePlanner(graph)
    with pytest.raises(PlanningError, match="não está no banco"):
        p.plan(RouteRequest("XXXX", "BBBB"))
    with pytest.raises(PlanningError, match="mesmo aeródromo"):
        p.plan(RouteRequest("AAAA", "AAAA"))
    with pytest.raises(PlanningError, match="não existe"):
        p.plan(RouteRequest("AAAA", "BBBB", sid="NOPE.X"))


def test_auto_without_matching_runway_warns(graph):
    res = RoutePlanner(graph).plan(RouteRequest("AAAA", "BBBB", "27", None, AUTO, None))
    assert res.sid is None and any("RW27" in w for w in res.warnings)


def test_edited_core_is_preserved(graph):
    edited = EditedCore(path=[0, 1, 5, 6, 3, 4], fallback=(1, 5))
    res = RoutePlanner(graph).plan(RouteRequest("AAAA", "BBBB", edited=edited))
    assert [graph.idents[p] for p in res.points] == ["AAAA", "W1", "W4", "W5", "W3", "BBBB"]


def test_avoidance_inserts_virtual_waypoint(graph):
    # area em volta de W2 e da perna W1-W2-W3, sem cobrir o desvio sul
    zone = AvoidZone("N1", ((0.3, 1.6), (0.3, 2.4), (-0.3, 2.4), (-0.3, 1.6)))
    av = Avoidance(graph, [zone])
    assert av.blocked == frozenset({2})
    res = RoutePlanner(graph).plan(RouteRequest("AAAA", "BBBB"), av)
    assert not av.path_crosses(res.points)
    assert 2 not in res.points


def test_avoidance_escape_coordinate_when_no_airway_detour(graph):
    # area so cruza a perna W1-W2 do meio; desvio sul (W12) tambem bloqueado
    zone = AvoidZone("N2", ((0.2, 1.4), (0.2, 1.6), (-1.2, 1.6), (-1.2, 1.4)))
    av = Avoidance(graph, [zone])
    res = RoutePlanner(graph).plan(RouteRequest("AAAA", "BBBB"), av)
    assert res.avoidance_applied
    assert any(isinstance(p, VirtualPoint) and p.ident == "WPTA1" for p in res.points)
    assert not av.path_crosses(res.points)


def test_real_graph_sbgr_sbbr(real_graph):
    res = RoutePlanner(real_graph).plan(RouteRequest("SBGR", "SBBR"))
    assert 850 < res.km < 1000
    assert real_graph.ident(res.points[0]) == "SBGR" and real_graph.ident(res.points[-1]) == "SBBR"


def test_airway_level_from_designator():
    from fmsnav.navgraph import airway_level
    assert airway_level("UM465") == "H"
    assert airway_level("UZ2") == "H"
    assert airway_level("W12") == "L"
    assert airway_level("") == ""


def test_level_restricts_airways(graph):
    low = shortest_path(graph, 0, 4, level="L")
    assert [graph.idents[i] for i in low.path] == ["AAAA", "W1", "W4", "W5", "W3", "BBBB"]
    high = shortest_path(graph, 0, 4, level="H")
    assert [graph.idents[i] for i in high.path] == ["AAAA", "W1", "W2", "W3", "BBBB"]


def test_level_without_route_raises():
    from conftest import EDGES, NODES, PROCS, RUNWAYS
    from fmsnav.navgraph import NavGraph
    only_high = NavGraph({"n": NODES, "e": [e for e in EDGES if e[3] != "W12"], "p": PROCS, "r": RUNWAYS})
    with pytest.raises(PlanningError, match="aerovias de baixa"):
        RoutePlanner(only_high).plan(RouteRequest("AAAA", "BBBB", level="L"))


def test_plan_level_low_with_procedures(graph):
    res = RoutePlanner(graph).plan(RouteRequest("AAAA", "BBBB", "09", "27", AUTO, AUTO, level="L"))
    assert [graph.idents[p] for p in res.points] == ["AAAA", "R1", "S1", "W1", "W4", "W5", "W3", "T1", "R2", "BBBB"]
