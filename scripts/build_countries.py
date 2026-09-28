"""Build data/countries.json from the raw world-countries dataset.

Run from the project folder:  python scripts/build_countries.py

The raw file (data/raw/world-countries.json) comes from
https://github.com/mledoze/countries (ODbL license).
"""

import json
import sys
import unicodedata
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from answers import normalize  # noqa: E402

RAW = BASE_DIR / "data" / "raw" / "world-countries.json"
OUT = BASE_DIR / "data" / "countries.json"

# Non-independent places we leave out: uninhabited, or run directly as part of
# another country (no government of their own, e.g. French overseas departments).
EXCLUDE = {
    "ATA", "ATF", "BVT", "HMD", "IOT", "SGS", "UMI",  # (almost) uninhabited
    "SJM", "BES", "GLP", "GUF", "MTQ", "MYT", "REU",  # integral parts of NO / NL / FR
    "CCK", "CXR", "NFK",                              # run directly by Australia
}

# Sovereign in practice but not (fully) recognised.
PARTLY_RECOGNISED = {"TWN", "XKX", "PSE", "ESH"}

# Extra accepted names on top of the dataset's own spellings.
EXTRA_NAMES = {
    "USA": ["America", "United States"],
    "GBR": ["Britain", "UK"],
    "CZE": ["Czech Republic"],
    "TUR": ["Turkey"],
    "COD": ["Congo Kinshasa", "Democratic Republic of the Congo"],
    "COG": ["Congo Brazzaville", "Congo Republic"],
    "CAF": ["CAR"],
    "VAT": ["Holy See"],
    "CPV": ["Cabo Verde", "Cape Verde"],
    "KOR": ["Korea South"],
    "PRK": ["Korea North"],
    "BIH": ["Bosnia"],
    "TTO": ["Trinidad"],
    "STP": ["Sao Tome"],
    "KNA": ["St Kitts"],
    "VCT": ["St Vincent"],
    "ATG": ["Antigua"],
    "FSM": ["Micronesia"],
    "XKX": ["Kosova"],
    "SHN": ["Saint Helena", "St Helena"],
    "VIR": ["US Virgin Islands"],
    "ALA": ["Aland"],
    "MAC": ["Macao"],
}

# Extra accepted capitals (seats of government, old or alternate spellings).
EXTRA_CAPITALS = {
    "BOL": ["La Paz"],
    "SWZ": ["Mbabane"],
    "USA": ["Washington", "Washington DC"],
    "MYS": ["Putrajaya"],
    "NLD": ["The Hague"],
    "CIV": ["Abidjan"],
    "BEN": ["Cotonou"],
    "LKA": ["Colombo", "Sri Jayawardenepura", "Kotte"],
    "KAZ": ["Nur-Sultan"],
    "IND": ["Delhi"],
    "UKR": ["Kiev"],
    "PSE": ["East Jerusalem", "Jerusalem"],
    "KIR": ["Tarawa"],
    "ESH": ["Laayoune"],
    "DJI": ["Djibouti City"],
    "KWT": ["Kuwait"],
    "GTM": ["Guatemala"],
    "PAN": ["Panama"],
    "VAT": ["Vatican"],
    "LUX": ["Luxembourg City"],
    "MCO": ["Monaco-Ville"],
    "CHE": ["Berne"],
    "MMR": ["Nay Pyi Taw", "Naypyitaw"],
    "XKX": ["Prishtina"],
    "MNG": ["Ulan Bator"],
    "CPV": ["Praia"],
    "BRN": ["Bandar Seri Begawan"],
}

# Capitals we replace entirely: wrong in the dataset, or places without a real capital.
CAPITAL_FIX = {
    "LKA": ["Sri Jayawardenepura Kotte"],
    "HKG": [],  # a city itself, no separate capital
    "TKL": [],  # the seat rotates between three atolls
}

# Shorter display names where the dataset's is unwieldy.
DISPLAY_NAME = {"SHN": "Saint Helena"}

# Codes the dataset gets "wrong" for our purposes.
ID_FIX = {"UNK": "XKX"}  # Kosovo: world-countries uses UNK, most tools use XKX

# Land borders the dataset lists that don't exist.
NOT_BORDERS = {("LKA", "IND")}  # Sri Lanka and India only share a sea


def is_latin(text):
    """True if every letter is a plain Latin letter once accents are removed."""
    stripped = unicodedata.normalize("NFKD", text)
    return all(ch.isascii() for ch in stripped if not unicodedata.combining(ch))


def continent(c):
    if c["region"] == "Americas":
        return "South America" if c["subregion"] == "South America" else "North America"
    return c["region"]


def kind(cid, c):
    if cid in PARTLY_RECOGNISED:
        return "partly recognised"
    return "sovereign" if c["independent"] else "territory"


def accepted(names):
    """Unique, readable names: no codes like 'NO', no 'Korea, Republic of', Latin only."""
    seen, result = set(), []
    for name in names:
        if "," in name or not is_latin(name):
            continue
        if len(name) <= 3 and name.isupper() and name not in ("US", "USA", "UK", "UAE", "DRC", "CAR", "RSA"):
            continue
        key = normalize(name)
        if key and key not in seen:
            seen.add(key)
            result.append(name)
    return result


def main():
    raw = json.loads(RAW.read_text())
    countries = []
    for c in raw:
        cid = ID_FIX.get(c["cca3"], c["cca3"])
        if cid in EXCLUDE:
            continue
        name = DISPLAY_NAME.get(cid, c["name"]["common"])
        countries.append({
            "id": cid,
            "iso2": c["cca2"].lower(),   # flag image file name
            "iso_num": c["ccn3"],         # matches the world map's country ids
            "name": name,
            "names": accepted([name, c["name"]["common"], c["name"]["official"], *c["altSpellings"], *EXTRA_NAMES.get(cid, [])]),
            "capitals": CAPITAL_FIX.get(cid, c["capital"]),
            "capital_names": accepted([*CAPITAL_FIX.get(cid, c["capital"]), *EXTRA_CAPITALS.get(cid, [])]),
            "continent": continent(c),
            "subregion": c["subregion"],
            "type": kind(cid, c),
            "borders": [ID_FIX.get(b, b) for b in c["borders"] if (cid, ID_FIX.get(b, b)) not in NOT_BORDERS],
            "landlocked": c["landlocked"],
            "area_km2": c["area"],
            "latlng": c["latlng"],
        })
    countries.sort(key=lambda x: x["name"])

    # Warn if one spelling would count for two different countries.
    for field in ("names", "capital_names"):
        owners = {}
        for country in countries:
            for n in country[field]:
                owners.setdefault(normalize(n), set()).add(country["id"])
        for key, ids in owners.items():
            if len(ids) > 1:
                print(f"  note: {field} '{key}' is accepted for {sorted(ids)}")

    OUT.write_text(json.dumps(countries, ensure_ascii=False, indent=1))
    by_type = {}
    for country in countries:
        by_type[country["type"]] = by_type.get(country["type"], 0) + 1
    print(f"Wrote {len(countries)} places to {OUT.relative_to(BASE_DIR)}: {by_type}")


if __name__ == "__main__":
    main()
