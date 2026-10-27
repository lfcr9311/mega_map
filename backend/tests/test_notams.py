import asyncio

import pytest

from fmsnav.notams import NotamService
from fmsnav.notams.parsing import coords_from_text, parse_coord, polygon_from_notam


def test_parse_coord():
    lat, lon = parse_coord("294948S0570127W")
    assert lat == pytest.approx(-(29 + 49 / 60 + 48 / 3600))
    assert lon == pytest.approx(-(57 + 1 / 60 + 27 / 3600))


def test_polygon_from_text_and_geojson():
    text = "AREA 294948S0570127W - 291818S0563225W - 290000S0570000W"
    assert len(coords_from_text(text)) == 3
    geo = {"geometry": {"coordinates": [[[-47.5, -15.8], [-47.3, -15.8], [-47.3, -16.0]]]}}
    assert polygon_from_notam(geo)[0] == (-15.8, -47.5)


class _FakeClient:
    def __init__(self, by_icao):
        self.by_icao = by_icao

    async def notams(self, icao, minutes):
        v = self.by_icao[icao]
        if isinstance(v, Exception):
            raise v
        return v


def test_service_tolerates_failing_icao(graph):
    client = _FakeClient({
        "SBAA": [{"number": "A1/26", "textE": "001000N0011000E 001000N0012000E 000000N0012000E"}],
        "SBBB": RuntimeError("timeout"),
    })
    svc = NotamService(client, ("SBAA", "SBBB"), 60, ttl_s=300)
    areas = asyncio.run(svc.areas())
    assert [a.number for a in areas] == ["A1/26"]


def test_demo_only_when_enabled():
    assert asyncio.run(NotamService(None, (), 60, 300).areas()) == []
    assert len(asyncio.run(NotamService(None, (), 60, 300, demo=True).areas())) == 2
