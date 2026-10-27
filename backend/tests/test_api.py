from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fmsnav.api import create_app
from fmsnav.notams import NotamService
from fmsnav.settings import Settings


@pytest.fixture
def client(graph):
    settings = Settings(
        graph_path=Path("/nonexistent"), rpl_back_url=None, notam_icaos=(), notam_minutes=0,
        notam_ttl_s=300, demo_notams=False, cors_origins=(), frontend_dist=Path("/nonexistent"),
    )
    app = create_app(settings, graph=graph, notam_service=NotamService(None, (), 0, 300))
    with TestClient(app) as c:
        yield c


def test_meta(client):
    assert client.get("/api/meta").json()["cycle"] == "TEST"


def test_airport_search_and_detail(client):
    assert [a["icao"] for a in client.get("/api/airports", params={"q": "AA"}).json()] == ["AAAA"]
    d = client.get("/api/airports/aaaa").json()
    assert d["runways"][0]["ident"] == "09" and d["procedures"] == 2
    assert client.get("/api/airports/ZZZZ").status_code == 404


def test_procedures_filtered_by_runway(client):
    url = "/api/airports/AAAA/procedures"
    assert [p["key"] for p in client.get(url, params={"kind": "SID", "runway": "09"}).json()] == ["SID1A.W1"]
    assert client.get(url, params={"kind": "SID", "runway": "27"}).json() == []


def test_route(client):
    r = client.post("/api/route", json={"origin": "AAAA", "destination": "BBBB",
                                        "runway_dep": "09", "runway_arr": "27", "sid": "auto", "star": "auto"})
    body = r.json()
    assert r.status_code == 200
    assert body["sid"]["key"] == "SID1A.W1"
    assert [p["ident"] for p in body["sid"]["chain"]] == ["AAAA", "R1", "S1", "W1"]
    assert body["legs"][3]["airway"] == "UX1"
    assert next(p for p in body["points"] if p["ident"] == "R2")["altitude"] == {"ft": 1500, "desc": "B"}


def test_route_error_is_422_with_message(client):
    r = client.post("/api/route", json={"origin": "AAAA", "destination": "AAAA"})
    assert r.status_code == 422 and "mesmo aeródromo" in r.json()["detail"]


def test_annotate_resolves_idents_and_virtual_points(client):
    r = client.post("/api/route/annotate", json={"points": [
        {"id": 0}, {"ident": "w1"}, {"ident": "WPTA1", "lat": -0.5, "lon": 2.0}, {"id": 4}]})
    body = r.json()
    assert [p["ident"] for p in body["points"]] == ["AAAA", "W1", "WPTA1", "BBBB"]
    assert body["points"][2]["kind"] == "V" and body["points"][2]["id"] is None
    bad = client.post("/api/route/annotate", json={"points": [{"id": 0}, {"ident": "NOPE"}]})
    assert bad.status_code == 422 and bad.json()["detail"]["index"] == 1


def test_network_bbox(client):
    body = client.get("/api/network", params={"south": -0.5, "west": 0.5, "north": 0.5, "east": 3.5,
                                              "fixes": True}).json()
    assert len(body["edges"]) == 2              # W1-W2, W2-W3
    assert {f[0] for f in body["fixes"]} >= {"W1", "W2", "W3"}


def test_route_level_low_and_network_filter(client):
    body = client.post("/api/route", json={"origin": "AAAA", "destination": "BBBB", "level": "L"}).json()
    assert [p["ident"] for p in body["points"]] == ["AAAA", "W1", "W4", "W5", "W3", "BBBB"]
    assert {l["airway"] for l in body["legs"]} == {"", "W12"}
    net = client.get("/api/network", params={"south": -2, "west": -1, "north": 1, "east": 5, "level": "H"}).json()
    assert len(net["edges"]) == 4          # UX1 x2 + 2 conectores
    assert client.post("/api/route", json={"origin": "AAAA", "destination": "BBBB", "level": "X"}).status_code == 422
