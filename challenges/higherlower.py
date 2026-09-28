"""⬆️ Higher or Lower: does country B have more or less than country A? Keep going until you're wrong."""

import json
import random
from pathlib import Path

from flask import abort, jsonify, render_template, request

import achievements
import leaderboard
import progress
from answers import Result
from challenges import bp
from challenges.common import Challenge, card, finish_run, open_run, save_run, start_run
from database import current_user_id, get_db
from games import COUNTRY_BY_ID

GAME = Challenge("higherlower", "Higher or Lower", "⬆️", "Which has more people, more land, more money?")

STATS = json.loads((Path(__file__).parent.parent / "data" / "stats.json").read_text())
KINDS = {  # label for the card, phrase for the question ("Chile: higher or lower population than Kenya?")
    "population": {"label": "Population", "phrase": "population"},
    "area": {"label": "Area", "phrase": "area"},
    "gdp": {"label": "GDP per person", "phrase": "GDP per person"},
    "life": {"label": "Life expectancy", "phrase": "life expectancy"},
    "elevation": {"label": "Highest point", "phrase": "highest point"},
}
VARIANTS = {**{k: v["label"] for k, v in KINDS.items()}, "mixed": "Mixed"}
POOLS = {kind: [cid for cid, s in STATS.items() if cid in COUNTRY_BY_ID and s.get(kind)] for kind in KINDS}
XP_PER_RIGHT = 3
RECENT = 40  # countries not to show again too soon


def value(cid, kind):
    return STATS[cid][kind]


def fmt(kind, v):
    if kind == "population":
        if v >= 1e9:
            return f"{v / 1e9:.2f} billion"
        return f"{v / 1e6:.1f} million" if v >= 1e6 else f"{v:,.0f}"
    if kind == "area":
        return f"{v:,.0f} km²" if v >= 10 else f"{v:g} km²"
    if kind == "gdp":
        return f"${v:,.0f}"
    if kind == "life":
        return f"{v:.1f} years"
    return f"{v:,.0f} m"


def note(cid, kind):
    """A line to remember after the value is revealed."""
    if kind == "elevation" and STATS[cid].get("peak"):
        return f"{COUNTRY_BY_ID[cid]['name']}'s highest point is {STATS[cid]['peak']} ({fmt(kind, value(cid, kind))})."
    return None


def pick_kind(variant, a):
    if variant != "mixed":
        return variant
    return random.choice([k for k in KINDS if STATS[a].get(k)])


def pick_b(kind, a, used, streak):
    """Early rounds can be any country; later ones are closer to A, so the game gets harder."""
    av = value(a, kind)
    candidates = [c for c in POOLS[kind] if c != a and c not in used and value(c, kind) != av]
    band = 1.8 if streak >= 8 else 4 if streak >= 3 else None
    if band:
        close = [c for c in candidates if max(value(c, kind), av) / max(min(value(c, kind), av), 1e-9) <= band]
        candidates = close or candidates
    return random.choice(candidates or [c for c in POOLS[kind] if c != a])


def pair(state):
    kind, a, b = state["kind"], state["a"], state["b"]
    return {
        "kind": kind,
        "label": KINDS[kind]["label"],
        "phrase": KINDS[kind]["phrase"],
        "a": {**card(a), "value": fmt(kind, value(a, kind))},
        "b": card(b),
        "streak": state["streak"],
    }


@bp.route("/higherlower")
def higherlower_page():
    bests = leaderboard.personal_bests(get_db(), current_user_id())["higherlower"]
    variants = [{"slug": slug, "name": name, "best": bests.get(slug, {}).get("score")} for slug, name in VARIANTS.items()]
    return render_template("higherlower.html", game=GAME, variants=variants)


@bp.post("/api/higherlower/start")
def higherlower_start():
    variant = (request.get_json(silent=True) or {}).get("variant")
    if variant not in VARIANTS:
        abort(400)
    first_kind = variant if variant != "mixed" else random.choice(list(KINDS))
    a = random.choice(POOLS[first_kind])
    kind = pick_kind(variant, a) if variant == "mixed" else first_kind
    state = {"variant": variant, "kind": kind, "a": a, "streak": 0, "used": [a]}
    state["b"] = pick_b(kind, a, state["used"], 0)
    state["used"].append(state["b"])
    run_id = start_run(get_db(), current_user_id(), "higherlower", state, variant=variant)
    return jsonify({"run_id": run_id, **pair(state)})


@bp.post("/api/higherlower/guess")
def higherlower_guess():
    data = request.get_json(silent=True) or {}
    choice = data.get("choice")
    if choice not in ("higher", "lower"):
        abort(400)
    db, user_id = get_db(), current_user_id()
    row, state = open_run(db, user_id, "higherlower", data.get("run_id"))
    kind, a, b = state["kind"], state["a"], state["b"]
    av, bv = value(a, kind), value(b, kind)
    correct = (choice == "higher") == (bv > av)

    xp = progress.record(db, user_id, "higherlower", b, choice, Result(correct),
                         xp=XP_PER_RIGHT if correct else 0, mastery=False)
    reveal = {"id": b, "value": fmt(kind, bv), "note": note(b, kind) or note(a, kind)}

    if correct:
        state["streak"] += 1
        state["a"] = b
        state["kind"] = pick_kind(state["variant"], b)
        state["b"] = pick_b(state["kind"], b, state["used"][-RECENT:], state["streak"])
        state["used"].append(state["b"])
        save_run(db, row["id"], state, score=state["streak"])
        return jsonify({"correct": True, "xp": xp, "reveal": reveal, "next": pair(state),
                        **achievements.after_play(db, user_id)})

    best_before = leaderboard.personal_bests(db, user_id)["higherlower"].get(state["variant"])
    finish_run(db, row["id"], state, score=state["streak"])
    return jsonify({
        "correct": False, "xp": xp, "reveal": reveal, "streak": state["streak"],
        "new_best": state["streak"] > 0 and (best_before is None or state["streak"] > best_before["score"]),
        "best_before": best_before["score"] if best_before else None,
        **achievements.after_play(db, user_id),
    })
