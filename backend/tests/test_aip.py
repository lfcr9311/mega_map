from datetime import date

import pytest

from fmsnav.aip import Segment, airac_date, parse_route_page, pick_amendment
from fmsnav.export import apply_directions
from fmsnav.navgraph import NavGraph
from fmsnav.routing import shortest_path


def _point(ident):
    return f'<tr id="{ident}" style="text-align: left" valign="middle"><td>{ident}</td></tr>'


def _cell(sym, colspan=1):
    span = ' colspan="2"' if colspan == 2 else ""
    return f'<td{span} style="text-align: center"><span><span style="font-size:40px;">{sym}</span></span></td>'


# formato da ENR 3.2: ponto, colunas Impar|Par do trecho, proximo ponto...
PAGE = "".join([
    _point("AAA"), _cell("↓"), _cell("↑"),      # mao dupla
    _point("BBB"), _cell("↓"), _cell("x"),      # so no sentido da tabela
    _point("CCC"), _cell("↑", colspan=2),       # uma celula para as duas paridades: so contrario
    _point("DDD"),
])


def test_airac_date():
    assert airac_date("2501") == date(2025, 1, 23)
    assert airac_date("2607") == date(2026, 7, 9)
    assert airac_date("2610") == date(2026, 10, 1)
    assert airac_date("2613") == date(2026, 12, 24)
    with pytest.raises(ValueError):
        airac_date("2614")


def test_pick_amendment_in_force_latest_publication():
    def a(d, eff, pub):
        return (f'{{"publication": {{"year": "{pub[:4]}", "month": "{pub[5:7]}", "day": "{pub[8:]}"}}, '
                f'"effective": {{"year": "{eff[:4]}", "month": "{eff[5:7]}", "day": "{eff[8:]}"}}, "dir": "{d}"}}')
    html = ("var amdts = [" + ", ".join([
        a("A 18", "2026-10-01", "2026-08-06"), a("20", "2026-10-01", "2026-09-10"),
        a("A 21", "2026-10-29", "2026-09-24"), a("A 16", "2026-09-03", "2026-07-09"),
    ]) + "]\n const months = {}")
    assert pick_amendment(html, date(2026, 10, 1)) == "20"
    assert pick_amendment(html, date(2026, 10, 15)) == "20"
    assert pick_amendment(html, date(2026, 10, 29)) == "A 21"


def test_parse_route_page():
    segs, problems = parse_route_page(PAGE, "UX1")
    assert problems == []
    assert segs == [
        Segment("UX1", "AAA", "BBB", True, True),
        Segment("UX1", "BBB", "CCC", True, False),
        Segment("UX1", "CCC", "DDD", False, True),
    ]
    assert [s.one_way for s in segs] == [False, True, True]


def test_parse_route_page_reports_odd_rows():
    _, problems = parse_route_page(_point("AAA") + _cell("↓") + _point("BBB") + _cell("?") + _cell("↓") + _point("CCC"), "UX1")
    assert len(problems) == 2


def test_apply_directions_and_routing(graph):
    # conftest: UX1 = W1-W2-W3 (aresta 1-2 gravada W1->W2, 2-3 gravada W2->W3)
    from conftest import EDGES, NODES, PROCS, RUNWAYS
    g = {"n": NODES, "e": [list(e) for e in EDGES], "p": PROCS, "r": RUNWAYS}
    # AIP lista W3 antes de W2 (contrario do binario) e manda voar so W3 -> W2 -> W1
    rep = apply_directions(g, [Segment("UX1", "W3", "W2", True, False), Segment("UX1", "W2", "W1", True, False),
                               Segment("UX1", "W9", "W1", True, True)])
    assert (rep["one_way"], rep["marked"], rep["missing"]) == (2, 2, ["UX1 W9-W1"])
    assert [e[4] for e in g["e"][:2]] == ["<", "<"]
    ng = NavGraph(g)
    assert [ng.idents[i] for i in shortest_path(ng, 0, 4).path] == ["AAAA", "W1", "W4", "W5", "W3", "BBBB"]
    assert [ng.idents[i] for i in shortest_path(ng, 4, 0).path] == ["BBBB", "W3", "W2", "W1", "AAAA"]


def test_old_graph_without_direction_field(graph):
    assert [graph.idents[i] for i in shortest_path(graph, 0, 4).path] == ["AAAA", "W1", "W2", "W3", "BBBB"]


def test_real_un866_only_ednes_to_ekera(real_graph):
    if not real_graph.meta.get("directions"):
        pytest.skip("navgraph real compilado sem eAIP")
    ekera, ednes = real_graph.resolve_ident("EKERA"), real_graph.resolve_ident("EDNES")
    assert ednes not in [v for v, *_ in real_graph.adj[ekera]]
    assert ekera in [v for v, *_ in real_graph.adj[ednes]]
