"""Geometry for the map games: projection, distances, directions, and which country a point is in.

The world map (static/world.svg and the shapes from /api/map) uses a Mercator projection,
1000 units wide, cropped to latitudes 84°N..58°S. These numbers must match scripts/build_outlines.py.
"""

import math
import re

WORLD_W = 1000
WORLD_LAT = (-58, 84)
EARTH_RADIUS_KM = 6371.0
HALF_EARTH_KM = math.pi * EARTH_RADIUS_KM  # ~20,015 km: the furthest apart two places can be
ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]


def _mercator_y(lat):
    lat = max(min(lat, 85), -85)
    return math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


_TOP = _mercator_y(WORLD_LAT[1])
_K = WORLD_W / 360


def world_xy(lon, lat):
    """Longitude/latitude -> position on the world map."""
    return (lon + 180) * _K, (_TOP - _mercator_y(lat)) * _K


def lonlat(x, y):
    """Position on the world map -> (longitude, latitude)."""
    merc = _TOP - y / _K
    return x / _K - 180, math.degrees(2 * math.atan(math.exp(math.radians(merc))) - math.pi / 2)


def distance_km(lat1, lon1, lat2, lon2):
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1, lon1, lat2, lon2):
    """Compass direction from point 1 towards point 2, in degrees (0 = north, 90 = east)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def arrow(degrees):
    return ARROWS[round(degrees / 45) % 8]


class Shape:
    """A country's outline on the world map, parsed from its locator path ('M x y x y ... Z M ...')."""

    def __init__(self, path):
        self.rings = []
        for ring in re.findall(r"M([^MZ]+)Z", path):
            numbers = [float(n) for n in ring.split()]
            self.rings.append(list(zip(numbers[0::2], numbers[1::2])))
        self.boxes = [(min(x for x, _ in r), min(y for _, y in r), max(x for x, _ in r), max(y for _, y in r))
                      for r in self.rings]
        # The same corners as (lat, lon), for measuring distances in km.
        self.latlon = [[lonlat(x, y)[::-1] for x, y in ring] for ring in self.rings]

    def contains(self, x, y):
        """Point-in-polygon with the even-odd rule, so holes (like Lesotho inside South Africa) work."""
        inside = False
        for ring, (x0, y0, x1, y1) in zip(self.rings, self.boxes):
            if not (x0 <= x <= x1 and y0 <= y <= y1):
                continue
            j = len(ring) - 1
            for i in range(len(ring)):
                xi, yi = ring[i]
                xj, yj = ring[j]
                if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
        return inside

    def corners(self):
        """Every corner as ((x, y), (lat, lon))."""
        return [(xy, ll) for ring, lls in zip(self.rings, self.latlon) for xy, ll in zip(ring, lls)]

    def nearest(self, lat, lon):
        """(distance in km, (x, y) of the nearest corner) from a point to this outline."""
        best, best_xy = float("inf"), None
        for ring, corners in zip(self.rings, self.latlon):
            for (x, y), (clat, clon) in zip(ring, corners):
                d = distance_km(lat, lon, clat, clon)
                if d < best:
                    best, best_xy = d, (x, y)
        return best, best_xy


class Dot:
    """A place too small to be drawn on the map (Gibraltar, Tuvalu, Tokelau): just a point."""

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.lon, self.lat = lonlat(x, y)

    def contains(self, x, y):
        return False

    def corners(self):
        return [((self.x, self.y), (self.lat, self.lon))]

    def nearest(self, lat, lon):
        return distance_km(lat, lon, self.lat, self.lon), (self.x, self.y)
