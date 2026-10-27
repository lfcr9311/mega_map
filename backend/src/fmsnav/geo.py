"""Geometria compartilhada: distancia great-circle e testes com poligonos.

Pontos sao (lat, lon) em graus. Os testes de poligono tratam lat/lon como um
plano (lon = x, lat = y) — suficiente para areas de NOTAM, que tem poucas
dezenas de km.
"""
from __future__ import annotations

from math import asin, cos, hypot, radians, sin, sqrt
from typing import Sequence

EARTH_RADIUS_KM = 6371.0088

LatLon = tuple[float, float]
Polygon = Sequence[LatLon]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = radians(lat1), radians(lat2)
    dp, dl = radians(lat2 - lat1), radians(lon2 - lon1)
    h = sin(dp / 2) ** 2 + cos(p1) * cos(p2) * sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def planar_distance(a: LatLon, b: LatLon) -> float:
    return hypot(a[0] - b[0], a[1] - b[1])


def point_in_polygon(p: LatLon, poly: Polygon) -> bool:
    """Ray casting."""
    lat, lon = p
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        lat1, lon1 = poly[i]
        lat2, lon2 = poly[j]
        if (lon1 > lon) != (lon2 > lon) and lat < (lat2 - lat1) * (lon - lon1) / (lon2 - lon1) + lat1:
            inside = not inside
        j = i
    return inside


def segments_cross(p1: LatLon, p2: LatLon, p3: LatLon, p4: LatLon) -> bool:
    """Cruzamento proprio de p1-p2 com p3-p4 (toque em ponta nao conta)."""
    def d(a: LatLon, b: LatLon, c: LatLon) -> float:
        return (b[1] - a[1]) * (c[0] - a[0]) - (b[0] - a[0]) * (c[1] - a[1])

    d1, d2 = d(p3, p4, p1), d(p3, p4, p2)
    d3, d4 = d(p1, p2, p3), d(p1, p2, p4)
    return ((d1 > 0 > d2) or (d1 < 0 < d2)) and ((d3 > 0 > d4) or (d3 < 0 < d4))


def segment_intersects_polygon(p1: LatLon, p2: LatLon, poly: Polygon) -> bool:
    """O segmento cruza o poligono ou tem uma ponta dentro dele."""
    if point_in_polygon(p1, poly) or point_in_polygon(p2, poly):
        return True
    j = len(poly) - 1
    for i in range(len(poly)):
        if segments_cross(p1, p2, poly[i], poly[j]):
            return True
        j = i
    return False


def centroid(poly: Polygon) -> LatLon:
    return (sum(p[0] for p in poly) / len(poly), sum(p[1] for p in poly) / len(poly))


def max_radius(poly: Polygon, center: LatLon) -> float:
    return max(planar_distance(p, center) for p in poly)


def bounds(poly: Polygon) -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max)"""
    lats = [p[0] for p in poly]
    lons = [p[1] for p in poly]
    return min(lats), max(lats), min(lons), max(lons)
