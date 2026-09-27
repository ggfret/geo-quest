"""Build data/ethnicities.json from CIA World Factbook "Ethnic groups" texts.

Run from the project folder:  python scripts/build_ethnicities.py

Input: data/raw/factbook-ethnic-groups.json, extracted from github.com/factbook/factbook.json
       (public domain), e.g. "Norwegian 81.5% (includes about 60,000 Sami), other European 8.9%, ..."
Output: {country id: {"groups": [[name, percent, masked name], ...], "year": "2021"}}
        The masked name hides words named after the country itself
        ("Norwegian" in Norway -> "???") until you answer; null if nothing to hide.
"""

import html
import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from answers import normalize  # noqa: E402

RAW = BASE_DIR / "data" / "raw" / "factbook-ethnic-groups.json"
WORLD = BASE_DIR / "data" / "raw" / "world-countries.json"
COUNTRIES = BASE_DIR / "data" / "countries.json"
OUT = BASE_DIR / "data" / "ethnicities.json"

# "Arab 75-80%", "~15%", "approximately 35%", "more than 95%", "<1%", "33.3%"
GROUP = re.compile(
    r"^\s*(?P<name>.+?)\s+(?:~|approximately|about|roughly|around|nearly|almost|over|under|more than|less than|<)?\s*"
    r"(?P<a>\d+(?:\.\d+)?)(?:\s*[-–]\s*(?P<b>\d+(?:\.\d+)?))?\s*%"
)
LAST = ("other", "unspecified", "unknown", "not declared", "none", "no answer", "other minorities")
# Words in country names that don't give the country away when they appear in a group name.
GENERIC = {"arab", "african", "american", "island", "islands", "republic", "kingdom", "state", "states",
           "united", "democratic", "federal", "saint", "north", "south", "east", "west", "central",
           "people", "peoples", "equatorial", "guinea", "new", "virgin"}


def clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.split(r"\bnote\b", text, flags=re.I)[0]
    for _ in range(3):  # drop (parentheses), including nested ones
        text = re.sub(r"\([^()]*\)", "", text)
    return text


def parse(text):
    groups = []
    for part in re.split(r"[,;]", clean(text)):
        m = GROUP.match(part)
        if not m:
            continue
        name = re.sub(r"\s+", " ", m["name"]).strip(" .:-")
        name = re.sub(r"^and\s+", "", name)
        pct = (float(m["a"]) + float(m["b"])) / 2 if m["b"] else float(m["a"])
        if name and not re.search(r"\d", name):
            groups.append([name, round(pct, 1)])
    return groups


def year(text):
    years = re.findall(r"\b(19|20)(\d\d) est\b", text)
    return "".join(years[-1]) if years else None


def own_words(country, raw):
    """Words that give the country away: its name and demonym ('Norway', 'Norwegian')."""
    words = set()
    sources = [country["name"], *country["names"][:2]]
    demonym = raw.get("demonyms", {}).get("eng", {})
    sources += [demonym.get("m", ""), demonym.get("f", "")]
    for s in sources:
        words |= {w for w in normalize(s).split() if len(w) >= 4 and w not in GENERIC}
    return words


def gives_away(word, own):
    word = normalize(word)
    if word in GENERIC:
        return False
    for w in own:
        n = min(5, len(word), len(w))
        if n >= 4 and word[:n] == w[:n]:
            return True
    return False


def mask(name, own, full_names):
    """'Black/African/Caribbean/black British' in the UK -> '... black ???'. None if nothing is hidden."""
    masked = name
    for full in full_names:  # 'other Central African Republic groups'
        masked = re.sub(r"\b" + re.escape(full) + r"\b", "???", masked, flags=re.I)
    masked = re.sub(r"[^\W\d_]+", lambda m: "???" if gives_away(m.group(), own) else m.group(), masked)
    masked = re.sub(r"\?\?\?(?:[\s-]+\?\?\?)+", "???", masked)  # 'Cook Islands' -> one ???
    return masked if masked != name else None


def main():
    raw_texts = json.loads(RAW.read_text())
    raw_countries = {c["cca3"]: c for c in json.loads(WORLD.read_text())}
    raw_countries["XKX"] = raw_countries.get("UNK", {})
    countries = {c["id"]: c for c in json.loads(COUNTRIES.read_text())}

    result, rejected = {}, []
    for cid, entry in raw_texts.items():
        groups = parse(entry["text"])
        total = sum(p for _, p in groups)
        if len(groups) < 2 or not 85 <= total <= 125:  # >100 happens where people list several ancestries
            rejected.append(cid)
            continue
        own = own_words(countries[cid], raw_countries.get(cid, {}))
        full_names = sorted(countries[cid]["names"], key=len, reverse=True)
        groups.sort(key=lambda g: (g[0].lower() in LAST, -g[1]))
        groups = [[name, pct, mask(name, own, full_names)] for name, pct in groups]
        if not any(m is None and name.lower() not in LAST for name, _, m in groups):
            rejected.append(cid)  # e.g. Egypt: '??? 99.7%, other 0.3%' leaves nothing to go on
            continue
        result[cid] = {"groups": groups, "year": year(entry["text"])}

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1))
    no_numbers = sorted(set(countries) - set(raw_texts))
    print(f"Wrote {len(result)} countries to {OUT.relative_to(BASE_DIR)}")
    print(f"Unusable (no clear percentages): {', '.join(sorted(rejected))}")
    print(f"No Factbook entry: {', '.join(no_numbers)}")


if __name__ == "__main__":
    main()
