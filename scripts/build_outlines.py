"""Build country outline shapes and a small world map from Natural Earth data.

Run from the project folder:  python scripts/build_outlines.py

Input:  data/raw/countries-50m.json  (world-atlas TopoJSON, Natural Earth 1:50m, public domain)
Output: data/outlines.json  -> {country id: {"path", "w", "h", "loc": {"path", "cx", "cy"}}}
        static/world.svg    -> grey world map that the locator highlight is drawn on
"""

import json
import math
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW = BASE_DIR / "data" / "raw" / "countries-50m.json"
COUNTRIES = BASE_DIR / "data" / "countries.json"
OUT = BASE_DIR / "data" / "outlines.json"
WORLD_SVG = BASE_DIR / "static" / "world.svg"

# Map pieces without an ISO number that belong to one of our countries.
MERGE_BY_NAME = {"Somaliland": "706", "N. Cyprus": "196", "Kosovo": "XK"}

MIN_POINTS = 20      # shapes with fewer corners are crude blobs at this map resolution
MIN_FILL = 0.02      # scattered specks of islands that fill almost none of their box aren't guessable
MAX_GAP_KM = 300     # land further than this from the main landmass is left off the outline
OUTLINE_SIZE = 1000  # outline drawn in a 1000 x (up to 1000) box
WORLD_W = 1000       # world map width
WORLD_LAT = (-58, 84)  # crop Antarctica and the far Arctic


# ---------- TopoJSON decoding ----------

def decode_arcs(topo):
    (sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x, y = x + dx, y + dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)
    return arcs


def ring_points(ring, arcs):
    points = []
    for index in ring:
        arc = arcs[index] if index >= 0 else arcs[~index][::-1]
        points.extend(arc[1:] if points else arc)
    return points


def polygons_of(geometry, arcs):
    """List of polygons; each polygon is a list of rings; each ring a list of (lon, lat)."""
    if geometry["type"] == "Polygon":
        return [[ring_points(r, arcs) for r in geometry["arcs"]]]
    if geometry["type"] == "MultiPolygon":
        return [[ring_points(r, arcs) for r in poly] for poly in geometry["arcs"]]
    return []


# ---------- Geometry helpers ----------

def wrap(lon):
    return (lon + 180) % 360 - 180


def ring_area(ring, lon0=0):
    """Rough area in 'degree²' corrected for latitude, good enough for comparing pieces."""
    total = 0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        x1, x2 = wrap(x1 - lon0) * math.cos(math.radians(y1)), wrap(x2 - lon0) * math.cos(math.radians(y2))
        total += x1 * y2 - x2 * y1
    return abs(total) / 2


def bbox(ring, lon0):
    xs = [wrap(x - lon0) for x, _ in ring]
    ys = [y for _, y in ring]
    return min(xs), min(ys), max(xs), max(ys)


def gap_km(a, b):
    """Approximate distance between two bounding boxes, in km."""
    dx = max(0, a[0] - b[2], b[0] - a[2])
    dy = max(0, a[1] - b[3], b[1] - a[3])
    mid_lat = math.radians((a[1] + a[3] + b[1] + b[3]) / 4)
    return math.hypot(dx * 111 * math.cos(mid_lat), dy * 111)


def main_cluster(polygons):
    """Keep the largest landmass plus anything chained to it by gaps under MAX_GAP_KM."""
    largest = max(polygons, key=lambda p: ring_area(p[0]))
    lon0 = sum(x for x, _ in largest[0]) / len(largest[0])
    boxes = [bbox(p[0], lon0) for p in polygons]
    keep = {polygons.index(largest)}
    changed = True
    while changed:
        changed = False
        for i, box in enumerate(boxes):
            if i not in keep and any(gap_km(box, boxes[k]) < MAX_GAP_KM for k in keep):
                keep.add(i)
                changed = True
    return [polygons[i] for i in sorted(keep)], lon0


def unwrap(ring):
    """Rings crossing the date line jump from +180 to -180; shift them onto one side."""
    lons = [x for x, _ in ring]
    if max(lons) - min(lons) > 180:
        return [(x + 360 if x < 0 else x, y) for x, y in ring]
    return ring


def mercator(lon, lat, lon0=0):
    lat = max(min(lat, 85), -85)
    return wrap(lon - lon0), math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))


def simplify(points, tolerance):
    """Douglas-Peucker: drop points that barely change the shape."""
    if len(points) < 4:
        return points
    if points[0] == points[-1]:
        # Closed ring: split at the point furthest from the start, simplify each half.
        x0, y0 = points[0]
        far = max(range(len(points)), key=lambda i: (points[i][0] - x0) ** 2 + (points[i][1] - y0) ** 2)
        if far == 0:
            return points[:1]
        return simplify(points[: far + 1], tolerance)[:-1] + simplify(points[far:], tolerance)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        (x1, y1), (x2, y2) = points[start], points[end]
        length = math.hypot(x2 - x1, y2 - y1) or 1e-9
        best, best_i = 0, None
        for i in range(start + 1, end):
            x0, y0 = points[i]
            d = abs((x2 - x1) * (y1 - y0) - (x1 - x0) * (y2 - y1)) / length
            if d > best:
                best, best_i = d, i
        if best_i is not None and best > tolerance:
            keep[best_i] = True
            stack += [(start, best_i), (best_i, end)]
    return [p for p, k in zip(points, keep) if k]


def to_path(rings, min_size=0.0, decimals=0):
    parts = []
    for ring in rings:
        xs, ys = [x for x, _ in ring], [y for _, y in ring]
        if len(ring) < 3 or max(max(xs) - min(xs), max(ys) - min(ys)) < min_size:
            continue
        pts = " ".join(f"{x:.{decimals}f} {y:.{decimals}f}" for x, y in ring)
        parts.append(f"M{pts}Z")
    return "".join(parts)


# ---------- Build ----------

def outline(polygons):
    """A country's shape, centred on itself (so countries across the date line work), fit to the box."""
    polygons, lon0 = main_cluster(polygons)
    rings = [[mercator(x, y, lon0) for x, y in ring] for poly in polygons for ring in poly]
    xs = [x for r in rings for x, _ in r]
    ys = [y for r in rings for _, y in r]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    scale = OUTLINE_SIZE / max(maxx - minx, maxy - miny)
    fitted = [[((x - minx) * scale, (maxy - y) * scale) for x, y in r] for r in rings]
    fitted = [simplify(r, 0.8) for r in fitted]
    path = to_path(fitted, min_size=2) or to_path(fitted)
    w, h = (maxx - minx) * scale, (maxy - miny) * scale
    points = sum(len(r) for r in fitted)
    fill = sum(ring_area_xy(r) for r in fitted) / max(w * h, 1)
    return {"path": path, "w": round(w), "h": round(h), "quiz": points >= MIN_POINTS and fill >= MIN_FILL}


def ring_area_xy(ring):
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))) / 2


def world_xy(lon, lat):
    """Plain Mercator for the world map. Longitudes past 180 (unwrapped date-line pieces) land off the right edge."""
    lat = max(min(lat, 85), -85)
    y = math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))
    top = math.degrees(math.log(math.tan(math.pi / 4 + math.radians(WORLD_LAT[1]) / 2)))
    k = WORLD_W / 360
    return (lon + 180) * k, (top - y) * k


def locator(polygons):
    rings = [simplify([world_xy(x, y) for x, y in unwrap(ring)], 0.15) for poly in polygons for ring in poly]
    largest = max(polygons, key=lambda p: ring_area(p[0]))[0]
    cx, cy = world_xy(sum(x for x, _ in largest) / len(largest), sum(y for _, y in largest) / len(largest))
    main, lon0 = main_cluster(polygons)
    # Measure every piece on the same side of the date line as the main landmass (Fiji's islands
    # straddle it), so the box stays compact instead of stretching across the whole map.
    near = [(lon0 + wrap(x - lon0), y) for poly in main for x, y in poly[0]]
    xs = [world_xy(x, y)[0] for x, y in near]
    ys = [world_xy(x, y)[1] for x, y in near]
    box = [round(min(xs), 1), round(min(ys), 1), round(max(xs), 1), round(max(ys), 1)]
    return {"path": to_path(rings, decimals=1), "cx": round(cx), "cy": round(cy), "box": box}


def dot(lat, lon):
    """Locator for places too small to be on the map: just a point."""
    x, y = world_xy(lon, lat)
    return {"path": "", "cx": round(x), "cy": round(y), "box": [round(x), round(y), round(x), round(y)]}


def main():
    topo = json.loads(RAW.read_text())
    arcs = decode_arcs(topo)
    by_code = {}
    world_rings = []
    for geometry in topo["objects"]["countries"]["geometries"]:
        polys = polygons_of(geometry, arcs)
        code = geometry.get("id") or MERGE_BY_NAME.get(geometry["properties"]["name"])
        if code:
            by_code.setdefault(code, []).extend(polys)
        for poly in polys:
            if ring_area(poly[0]) and min(y for _, y in poly[0]) > WORLD_LAT[0]:
                world_rings.append(simplify([world_xy(x, y) for x, y in unwrap(poly[0])], 0.15))

    result = {}
    for country in json.loads(COUNTRIES.read_text()):
        code = country["iso_num"] or country["iso2"].upper()
        if code in by_code:
            polys = by_code[code]
            result[country["id"]] = {**outline(polys), "loc": locator(polys)}
        else:
            result[country["id"]] = {"quiz": False, "loc": dot(*country["latlng"])}
    OUT.write_text(json.dumps(result, separators=(",", ":")))

    height = world_xy(0, WORLD_LAT[0])[1]
    WORLD_SVG.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WORLD_W} {height:.0f}">'
        f'<path fill="currentColor" d="{to_path(world_rings, min_size=0.3, decimals=1)}"/></svg>'
    )
    skipped = sorted(k for k, v in result.items() if not v["quiz"] and "path" in v)
    print(f"Too small or scattered to quiz ({len(skipped)}): {', '.join(skipped)}")
    print(f"Wrote {len(result)} outlines to {OUT.relative_to(BASE_DIR)} ({OUT.stat().st_size // 1024} KB)")
    print(f"Wrote world map to {WORLD_SVG.relative_to(BASE_DIR)} ({WORLD_SVG.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
