"""🤝 Neighbours: name every country that borders a given country. Three wrong names end the round."""

from flask import jsonify, render_template, request

import achievements
import progress
from answers import Result, identify
from challenges import bp
from challenges.common import (Challenge, card, finish_run, latest_open_run, neighbours_of, open_run, place,
                               save_run, start_run, view_box)
from database import current_user_id, get_db
from games import COUNTRIES, COUNTRY_BY_ID, COUNTRY_NAMES, country_info

GAME = Challenge("neighbours", "Neighbours", "🤝", "Name every country that borders one country.",
                 pool=[c["id"] for c in COUNTRIES if neighbours_of(c["id"])])

STRIKES = 3
XP_PER_NEIGHBOUR = 3
ALL_FOUND_BONUS = 5


def guess_log(state):
    """Every guess in order, right (✓) or wrong (✗). Rounds saved before the log existed: found first, then wrong."""
    log = state.get("log") or (
        [{"id": cid, "ok": True} for cid in state["found"]] + [{"id": cid, "ok": False} for cid in state["wrong"]]
    )
    return [{"name": COUNTRY_BY_ID[g["id"]]["name"], "ok": g["ok"]} for g in log]


def board(run_id, state):
    """The round as the page shows it."""
    target = state["target"]
    return {
        "run_id": run_id,
        "country": card(target),
        "target": place(target),
        "total": len(neighbours_of(target)),
        "found": [place(cid) for cid in state["found"]],
        "wrong": [COUNTRY_BY_ID[cid]["name"] for cid in state["wrong"]],
        "wrong_places": [place(cid) for cid in state["wrong"]],
        "log": guess_log(state),
        "strikes_left": STRIKES - len(state["wrong"]),
        "view": view_box([target, *neighbours_of(target)]),  # frames the map without saying which ones they are
    }


def end(db, user_id, row, state):
    """Finish the round: save it, give XP, show what was missed."""
    target = state["target"]
    everyone = neighbours_of(target)
    won = len(state["found"]) == len(everyone)
    xp = XP_PER_NEIGHBOUR * len(state["found"]) + (ALL_FOUND_BONUS if won else 0)
    first_wrong = state["wrong"][0] if state["wrong"] else None
    xp = progress.record(db, user_id, "neighbours", target, f"{len(state['found'])}/{len(everyone)}",
                         Result(won, guessed_id=first_wrong), xp=xp)
    finish_run(db, row["id"], state, score=len(state["found"]), solved=won)
    return {
        "finished": True,
        "won": won,
        "missed": [place(cid) for cid in everyone if cid not in state["found"]],
        "xp": xp,
        "info": country_info(target),
        **achievements.after_play(db, user_id),
    }


@bp.route("/neighbours")
def neighbours_page():
    return render_template("neighbours.html", game=GAME)


@bp.post("/api/neighbours/start")
def neighbours_start():
    db, user_id = get_db(), current_user_id()
    row, state = latest_open_run(db, user_id, "neighbours")
    if row is None or (request.get_json(silent=True) or {}).get("new"):
        target = progress.pick_next(db, user_id, "neighbours", GAME.pool)
        state = {"target": target, "found": [], "wrong": [], "log": []}
        run_id = start_run(db, user_id, "neighbours", state, total=len(neighbours_of(target)))
        return jsonify(board(run_id, state))
    return jsonify(board(row["id"], state))


@bp.post("/api/neighbours/guess")
def neighbours_guess():
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    row, state = open_run(db, user_id, "neighbours", data.get("run_id"))
    target = state["target"]
    guess_id, typo = identify(str(data.get("guess", ""))[:100], COUNTRY_NAMES)

    if guess_id is None:
        return jsonify({"status": "unknown", **board(row["id"], state)})
    name = COUNTRY_BY_ID[guess_id]["name"]
    if guess_id == target:
        return jsonify({"status": "self", "name": name, **board(row["id"], state)})
    if guess_id in state["found"] or guess_id in state["wrong"]:
        return jsonify({"status": "repeat", "name": name, **board(row["id"], state)})

    if guess_id in neighbours_of(target):
        state["found"].append(guess_id)
        status = "found"
    else:
        state["wrong"].append(guess_id)
        status = "wrong"
    state.setdefault("log", []).append({"id": guess_id, "ok": status == "found"})
    save_run(db, row["id"], state, score=len(state["found"]))

    result = {"status": status, "name": name, "typo": typo, **board(row["id"], state)}
    if len(state["found"]) == len(neighbours_of(target)) or len(state["wrong"]) >= STRIKES:
        result.update(end(db, user_id, row, state))
    return jsonify(result)


@bp.post("/api/neighbours/give-up")
def neighbours_give_up():
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    row, state = open_run(db, user_id, "neighbours", data.get("run_id"))
    return jsonify({"status": "gave_up", **board(row["id"], state), **end(db, user_id, row, state)})
