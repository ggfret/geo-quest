"""The games: what each one asks, which answers it accepts, and what it explains afterwards."""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from answers import check

DATA_DIR = Path(__file__).parent / "data"

COUNTRIES = json.loads((DATA_DIR / "countries.json").read_text())
COUNTRY_BY_ID = {c["id"]: c for c in COUNTRIES}
COUNTRY_NAMES = {c["id"]: c["names"] for c in COUNTRIES}

FLAGS = json.loads((DATA_DIR / "flags.json").read_text())
NO_OWN_FLAG = {"MAF"}  # Saint Martin officially flies the French flag

OUTLINES = json.loads((DATA_DIR / "outlines.json").read_text())

ETHNICITIES = json.loads((DATA_DIR / "ethnicities.json").read_text())

LANGUAGES = json.loads((DATA_DIR / "languages.json").read_text())
LANGS = LANGUAGES["languages"]

CAPITALS = json.loads((DATA_DIR / "capitals.json").read_text())
CAPITAL_NAMES = {c["id"]: c["capital_names"] for c in COUNTRIES if c["capital_names"]}


@dataclass
class Game:
    slug: str
    name: str
    icon: str
    blurb: str
    placeholder: str = "Type the country…"
    pool: list = field(default_factory=list)   # item ids that can be asked
    names: dict = field(default_factory=dict)  # id -> accepted answers (all possible answers, not just the pool)
    prompt: Callable = None                    # item id -> what to show the player
    explain: Callable = None                   # (item id, guessed id, guess text, context) -> fact card
    answer: Callable = lambda cid: COUNTRY_BY_ID[cid]["name"]   # item id -> the right answer, for display
    guessed: Callable = lambda cid: COUNTRY_BY_ID[cid]["name"]  # id the guess matched -> "You said ___."
    locate: Callable = lambda cid: [OUTLINES[cid]["loc"]] if cid in OUTLINES else []  # id -> places on the mini-map

    @property
    def ready(self):
        return self.prompt is not None


def country_info(cid):
    c = COUNTRY_BY_ID[cid]
    return f"{c['subregion'] or c['continent']} · Capital: {', '.join(c['capitals']) or '—'}"


def lookalike(groups, target, guessed=None):
    """The tip for a group containing both ids, else any group containing the target."""
    both = [g for g in groups if target in g["ids"] and guessed in g["ids"]]
    either = [g for g in groups if target in g["ids"]]
    return (both or either or [None])[0]


def flag_url(cid):
    return f"https://flagcdn.com/{COUNTRY_BY_ID[cid]['iso2']}.svg"


def explain_flag(cid, guessed_id, guess, context=None):
    group = lookalike(FLAGS["lookalikes"], cid, guessed_id)
    mixup = bool(group and guessed_id in group["ids"] and guessed_id != cid)
    return {
        "fact": FLAGS["facts"].get(cid),
        "info": country_info(cid),
        "tip": ("Common mix-up! " if mixup else "Lookalikes: ") + group["tip"] if group else None,
        "tip_is_mixup": mixup,
    }


def explain_outline(cid, guessed_id, guess, context=None):
    c = COUNTRY_BY_ID[cid]
    neighbours = [COUNTRY_BY_ID[b]["name"] for b in c["borders"] if b in COUNTRY_BY_ID]
    if neighbours:
        fact = f"{c['name']} borders {join_names(neighbours)}."
        if c["landlocked"]:
            fact += " It's landlocked, with no coastline."
    else:
        fact = f"{c['name']} has no land borders with other countries."
    area = f"{c['area_km2']:,.0f} km²"
    return {"fact": fact, "info": f"{c['subregion'] or c['continent']} · {area}", "tip": None, "tip_is_mixup": False}


def ethnicity_prompt(cid):
    e = ETHNICITIES[cid]
    return {"bars": [{"label": masked or name, "pct": pct, "hidden": bool(masked)} for name, pct, masked in e["groups"]]}


def explain_ethnicity(cid, guessed_id, guess, context=None):
    e = ETHNICITIES[cid]
    total = sum(pct for _, pct, _ in e["groups"])
    estimate = f", {e['year']} estimate" if e["year"] else ""
    fact = f"Source: CIA World Factbook{estimate}."
    if total > 102:
        fact += " People could list more than one ancestry, so the numbers add up to more than 100%."
    tip = None
    if guessed_id and guessed_id != cid and guessed_id in ETHNICITIES:
        top = ", ".join(f"{name} {pct:g}%" for name, pct, _ in ETHNICITIES[guessed_id]["groups"][:3])
        tip = f"Your guess, {COUNTRY_BY_ID[guessed_id]['name']}, looks like this: {top}."
    return {
        "bars": [{"label": name, "pct": pct, "hidden": bool(masked)} for name, pct, masked in e["groups"]],
        "fact": fact,
        "info": country_info(cid),
        "tip": tip,
        "tip_is_mixup": bool(tip),
    }


def join_names(names):
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def explain_capital(cid, guessed_id, guess, context=None):
    c = COUNTRY_BY_ID[cid]
    others = c["capital_names"][1:]
    trap = next((t for t in CAPITALS["traps"].get(cid, []) if check(guess, t, {t: [t]}).correct), None)
    return {
        "fact": CAPITALS["facts"].get(cid),
        "info": f"{c['name']} · {c['subregion'] or c['continent']}" + (f" · Also accepted: {', '.join(others)}" if others else ""),
        "tip": f"Common mix-up! {trap} is a big city in {c['name']}, but it's not the capital." if trap else None,
        "tip_is_mixup": bool(trap),
    }


def language_prompt(lang):
    index = random.randrange(len(LANGS[lang]["sentences"]))
    return {"sentence": LANGS[lang]["sentences"][index][0], "context": index, "choices": language_choices(lang)}


def language_choices(lang, n=4):
    """The right answer plus look-alikes: same writing system first, then the group's nearest neighbour."""
    group = LANGS[lang]["group"]
    same = [l for l, v in LANGS.items() if v["group"] == group and l != lang]
    fill_group = LANGUAGES["groups"][group].get("fill")
    near = [l for l, v in LANGS.items() if v["group"] == fill_group]
    random.shuffle(same)
    random.shuffle(near)
    choices = [lang] + (same + near)[: n - 1]
    random.shuffle(choices)
    return choices


def explain_language(lang, guessed_id, guess, context=None):
    info = LANGS[lang]
    tip = f"How to spot {lang}: {info['tell']}"
    if guessed_id and guessed_id != lang:
        tip += f"\nHow to spot {guessed_id}: {LANGS[guessed_id]['tell']}"
    sentences = info["sentences"]
    translation = sentences[context][1] if isinstance(context, int) and 0 <= context < len(sentences) else ""
    spoken = [COUNTRY_BY_ID[c]["name"] for c in info["countries"] if c in COUNTRY_BY_ID]
    more = f" and {len(spoken) - 6} more" if len(spoken) > 6 else ""
    return {
        "fact": f"It means: “{translation}”" if translation else None,
        "info": f"{LANGUAGES['groups'][info['group']]['name']} · Spoken in {', '.join(spoken[:6])}{more}",
        "tip": tip,
        "tip_is_mixup": bool(guessed_id and guessed_id != lang),
    }


GAMES = [
    Game(
        "flags", "Flags", "🏳️", "See a flag, type the country.",
        pool=[c["id"] for c in COUNTRIES if c["id"] not in NO_OWN_FLAG],
        names=COUNTRY_NAMES,
        prompt=lambda cid: {"image": flag_url(cid)},
        explain=explain_flag,
    ),
    Game(
        "capitals", "Capitals", "🏛️", "See a country, type its capital.",
        placeholder="Type the capital…",
        pool=list(CAPITAL_NAMES),
        names=CAPITAL_NAMES,
        prompt=lambda cid: {"text": COUNTRY_BY_ID[cid]["name"], "image": flag_url(cid), "small": True},
        explain=explain_capital,
        answer=lambda cid: " / ".join(COUNTRY_BY_ID[cid]["capitals"]),
        guessed=lambda cid: f"{COUNTRY_BY_ID[cid]['capitals'][0]} (capital of {COUNTRY_BY_ID[cid]['name']})",
    ),
    Game(
        "outlines", "Outlines", "🗺️", "See a border shape, type the country.",
        pool=[cid for cid, o in OUTLINES.items() if o["quiz"]],
        names=COUNTRY_NAMES,
        prompt=lambda cid: {"shape": {k: OUTLINES[cid][k] for k in ("path", "w", "h")}},
        explain=explain_outline,
    ),
    Game(
        "ethnicities", "Ethnicities", "👥", "See the ethnic makeup, type the country.",
        pool=[cid for cid in ETHNICITIES if cid in COUNTRY_BY_ID],
        names=COUNTRY_NAMES,
        prompt=ethnicity_prompt,
        explain=explain_ethnicity,
    ),
    Game(
        "languages", "Languages", "🗣️", "Read a sentence, pick the language.",
        pool=list(LANGS),
        names={lang: [lang] for lang in LANGS},
        prompt=language_prompt,
        explain=explain_language,
        answer=lambda lang: lang,
        guessed=lambda lang: lang,
        locate=lambda lang: [OUTLINES[c]["loc"] for c in LANGS[lang]["countries"] if c in OUTLINES],
    ),
]
GAME_BY_SLUG = {g.slug: g for g in GAMES}


def item_rows():
    """(game, item id, name, region) for every askable item, for the `items` table."""
    for game in GAMES:
        for item_id in game.pool:
            if game.slug == "languages":
                yield game.slug, item_id, item_id, LANGUAGES["groups"][LANGS[item_id]["group"]]["name"]
            else:
                c = COUNTRY_BY_ID[item_id]
                yield game.slug, item_id, c["name"], c["continent"]
