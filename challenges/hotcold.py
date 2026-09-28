"""🔥 Hot & Cold: guess a mystery country. Each guess tells you how far away it is and in which direction."""

from flask import abort, jsonify, render_template, request

import achievements
import geo
import progress
from answers import Result, identify
from challenges import bp
from challenges.common import SOVEREIGN, Challenge, finish_run, latest_open_run, open_run, place, save_run, start_run
from database import current_user_id, get_db
from games import COUNTRY_BY_ID, COUNTRY_NAMES, country_info, explain_outline

GAME = Challenge("hotcold", "Hot & Cold", "🔥", "Guess the mystery country. Distance and direction guide you.",
                 pool=SOVEREIGN)


def xp_for(guesses):
    """30 XP for a first-guess hit, 5 less per extra guess, never below 5."""
    return max(5, 35 - 5 * guesses)


def describe(guess_id, target):
    """How close a guess is: km between the countries' centres, which way to go, and whether they touch."""
    (lat1, lon1), (lat2, lon2) = COUNTRY_BY_ID[guess_id]["latlng"], COUNTRY_BY_ID[target]["latlng"]
    km = geo.distance_km(lat1, lon1, lat2, lon2)
    return {
        "id": guess_id,
        "name": COUNTRY_BY_ID[guess_id]["name"],
        "km": round(km),
        "arrow": geo.arrow(geo.bearing(lat1, lon1, lat2, lon2)),
        "proximity": max(0, round(100 * (1 - km / geo.HALF_EARTH_KM))),
        "neighbour": target in COUNTRY_BY_ID[guess_id]["borders"],
    }


def reveal(db, user_id, target, state, won):
    """End the round: save it, give XP, and show the answer."""
    n = len(state["guesses"]) + (1 if won else 0)
    xp = progress.record(db, user_id, "hotcold", target, f"{n} guesses", Result(won), xp=xp_for(n) if won else 0)
    return {
        "answer": COUNTRY_BY_ID[target]["name"],
        "target": place(target),
        "guesses_used": n,
        "xp": xp,
        "info": country_info(target),
        "fact": explain_outline(target, None, "")["fact"],
        **achievements.after_play(db, user_id),
    }


@bp.route("/hotcold")
def hotcold_page():
    return render_template("hotcold.html", game=GAME)


@bp.post("/api/hotcold/start")
def hotcold_start():
    db, user_id = get_db(), current_user_id()
    row, state = latest_open_run(db, user_id, "hotcold")
    if row is None or (request.get_json(silent=True) or {}).get("new"):
        state = {"target": progress.pick_next(db, user_id, "hotcold", GAME.pool), "guesses": []}
        return jsonify({"run_id": start_run(db, user_id, "hotcold", state), "guesses": []})
    return jsonify({"run_id": row["id"], "guesses": state["guesses"]})


@bp.post("/api/hotcold/guess")
def hotcold_guess():
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    row, state = open_run(db, user_id, "hotcold", data.get("run_id"))
    target = state["target"]
    guess_id, typo = identify(str(data.get("guess", ""))[:100], COUNTRY_NAMES)

    if guess_id is None:
        return jsonify({"status": "unknown", "guesses": state["guesses"]})
    if any(g["id"] == guess_id for g in state["guesses"]):
        return jsonify({"status": "repeat", "name": COUNTRY_BY_ID[guess_id]["name"], "guesses": state["guesses"]})
    if guess_id == target:
        state["solved"] = True
        result = reveal(db, user_id, target, state, won=True)
        finish_run(db, row["id"], state, score=result["guesses_used"], solved=True)
        return jsonify({"status": "solved", "guesses": state["guesses"], **result})

    state["guesses"].append({**describe(guess_id, target), "typo": typo})
    save_run(db, row["id"], state, score=len(state["guesses"]))
    return jsonify({"status": "guess", "guesses": state["guesses"]})


@bp.post("/api/hotcold/give-up")
def hotcold_give_up():
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    row, state = open_run(db, user_id, "hotcold", data.get("run_id"))
    result = reveal(db, user_id, state["target"], state, won=False)
    finish_run(db, row["id"], state, score=len(state["guesses"]), solved=False)
    return jsonify({"status": "gave_up", "guesses": state["guesses"], **result})
