"""Pull the few Factbook fields we use out of a downloaded copy of factbook.json.

    curl -L -o factbook.zip https://codeload.github.com/factbook/factbook.json/zip/refs/heads/master
    unzip factbook.zip -d factbook
    python scripts/extract_factbook.py factbook

Writes two small files that are kept in the repo (the full download is ~3 MB and isn't needed):
    data/raw/factbook-ethnic-groups.json   {country id: {"gec", "text"}}
    data/raw/factbook-stats.json           {country id: {"gec", "population", "life", "gdp", "elevation", "coastline"}}
The Factbook is public domain (CC0).
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from answers import normalize  # noqa: E402

COUNTRIES = BASE_DIR / "data" / "countries.json"
ETHNIC_OUT = BASE_DIR / "data" / "raw" / "factbook-ethnic-groups.json"
STATS_OUT = BASE_DIR / "data" / "raw" / "factbook-stats.json"
SKIP_FOLDERS = {"meta", "oceans", "antarctica"}


def text(entry, *keys):
    """Follow keys into the nested Factbook JSON and return the 'text' found there, or None."""
    for key in keys:
        if not isinstance(entry, dict):
            return None
        entry = entry.get(key)
    return entry.get("text") if isinstance(entry, dict) else None


def latest_gdp(economy):
    """'Real GDP per capita' has one entry per year; take the newest."""
    field = economy.get("Real GDP per capita") or {}
    years = sorted(k for k in field if k.startswith("Real GDP per capita"))
    return field[years[-1]].get("text") if years else None


def main(folder):
    lookup = {}
    for c in json.loads(COUNTRIES.read_text()):
        for name in c["names"]:
            lookup.setdefault(normalize(name), c["id"])

    ethnic, stats = {}, {}
    for path in sorted(Path(folder).glob("*/*/*.json")):
        if path.parent.name in SKIP_FOLDERS:
            continue
        d = json.loads(path.read_text())
        government = d.get("Government", {}).get("Country name", {})
        names = [text(government, k) for k in ("conventional short form", "conventional long form", "local short form")]
        cid = next((lookup[normalize(n)] for n in names if n and normalize(n) in lookup), None)
        if not cid:
            continue
        people, geography = d.get("People and Society", {}), d.get("Geography", {})
        gec = path.stem
        groups = text(people, "Ethnic groups")
        if groups:
            ethnic[cid] = {"gec": gec, "text": groups}
        stats[cid] = {
            "gec": gec,
            "population": text(people, "Population", "total") or text(people, "Population"),
            "life": text(people, "Life expectancy at birth", "total population"),
            "gdp": latest_gdp(d.get("Economy", {})),
            "elevation": text(geography, "Elevation", "highest point"),
            "coastline": text(geography, "Coastline"),
        }

    ETHNIC_OUT.write_text(json.dumps(dict(sorted(ethnic.items())), ensure_ascii=False, indent=1))
    STATS_OUT.write_text(json.dumps(dict(sorted(stats.items())), ensure_ascii=False, indent=1))
    print(f"Ethnic groups for {len(ethnic)} countries, stats for {len(stats)} countries.")


if __name__ == "__main__":
    main(sys.argv[1])
