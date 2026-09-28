"""Build data/stats.json (numbers for Higher or Lower) from the Factbook extract.

Run from the project folder:  python scripts/build_stats.py

Input:  data/raw/factbook-stats.json (see scripts/extract_factbook.py), data/countries.json (for area)
Output: {country id: {"population", "area", "gdp", "life", "elevation", "peak", "coastline"}}
        A stat is left out for a country when the Factbook has no number for it.
"""

import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW = BASE_DIR / "data" / "raw" / "factbook-stats.json"
COUNTRIES = BASE_DIR / "data" / "countries.json"
OUT = BASE_DIR / "data" / "stats.json"

NUMBER = r"-?\d[\d,]*(?:\.\d+)?"


def first_number(text):
    m = re.search(NUMBER, text or "")
    return float(m.group().replace(",", "")) if m else None


def highest_point(text):
    """'Galdhopiggen 2,469 m' -> ('Galdhopiggen', 2469)."""
    m = re.match(rf"\s*(?P<name>.+?)\s+(?P<m>{NUMBER})\s*m\b", text or "")
    if not m:
        return None, None
    name = re.sub(r"\s*\(.*?\)", "", m["name"]).strip()
    return name, int(float(m["m"].replace(",", "")))


def main():
    raw = json.loads(RAW.read_text())
    areas = {c["id"]: c["area_km2"] for c in json.loads(COUNTRIES.read_text())}
    result = {}
    for cid, r in raw.items():
        peak, elevation = highest_point(r["elevation"])
        stats = {
            "population": first_number(r["population"]),
            "area": areas.get(cid),
            "gdp": first_number((r["gdp"] or "").replace("$", "")),
            "life": first_number(r["life"]),
            "elevation": elevation,
            "peak": peak,
            "coastline": first_number(r["coastline"]),
        }
        if stats["population"] is not None:
            stats["population"] = int(stats["population"])
        result[cid] = {k: v for k, v in stats.items() if v is not None}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    counts = {k: sum(1 for v in result.values() if k in v) for k in ("population", "area", "gdp", "life", "elevation", "coastline")}
    print(f"Wrote {OUT.relative_to(BASE_DIR)}: {counts}")


if __name__ == "__main__":
    main()
