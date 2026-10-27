from fmsnav.decode.primitives import CHARS, decode_ident, decode_lat, decode_lon, decode_name6

_CODE = {v: k for k, v in CHARS.items() if v}


def _encode(ident: str) -> int:
    v = 0
    for ch, shift in zip(ident.ljust(5, "\0"), (26, 20, 14, 8, 2)):
        v |= _CODE.get(ch, 0) << shift
    return v


def test_ident_roundtrip():
    for ident in ("SBGR", "UZ2", "A-1", "ALON1"):
        assert decode_ident(_encode(ident)) == ident


def test_name6_sixth_char():
    head = _encode("ALON1")
    sixth = _CODE["B"]
    v64 = (head << 32) | (sixth << (64 - 38))
    assert decode_name6(v64.to_bytes(8, "big")) == "ALON1B"


def test_coordinates_south_west_by_complement():
    lat = round(-23.4356 * 80000) % 2 ** 24
    lon = round(-46.4731 * 40000) % 2 ** 24
    rec = lat.to_bytes(3, "big") + lon.to_bytes(3, "big")
    assert abs(decode_lat(rec, 0) - -23.4356) < 1e-4
    assert abs(decode_lon(rec, 3) - -46.4731) < 1e-4
