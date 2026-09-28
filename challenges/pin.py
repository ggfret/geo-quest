"""📍 Pin it: you're given a country and click where it is on the world map."""

from flask import abort, jsonify, render_template, request

import achievements
import geo
import progress
from answers import Result
from challenges import bp
from challenges.common import Challenge, country_at, inside, place, shapes
from database import current_user_id, get_db
from games import COUNTRY_BY_ID, OUTLINES, country_info, explain_outline, flag_url

GAME = Challenge("pin", "Pin it", "📍", "Find the country on a blank map.", pool=sorted(OUTLINES))

NEAR_KM = 50            # a hit, for tiny countries or a click just off the coast
CLOSE_XP = [(300, 4), (1000, 2)]  # some XP for near misses: within 300 km -> 4 XP, within 1,000 km -> 2 XP


def score_click(target, x, y):
    """Where did the click land, relative to the target country?"""
    lon, lat = geo.lonlat(x, y)
    shape = shapes()[target]
    if inside(shape, x, y):
        return {"correct": True, "distance": 0, "nearest": (x, y), "clicked": target, "lat": lat, "lon": lon}
    distance, nearest = shape.nearest(lat, lon)
    clicked = country_at(x, y)
    tiny = not OUTLINES[target]["quiz"]  # too small to hit reliably (Vatican City, Malta, Tuvalu, ...)
    correct = distance <= NEAR_KM and (clicked is None or tiny)
    return {"correct": correct, "distance": distance, "nearest": nearest, "clicked": clicked, "lat": lat, "lon": lon}


@bp.route("/pin")
def pin_page():
    return render_template("pin.html", game=GAME)


@bp.get("/api/pin/next")
def pin_next():
    cid = progress.pick_next(get_db(), current_user_id(), "pin", GAME.pool)
    return jsonify({"item_id": cid, "name": COUNTRY_BY_ID[cid]["name"], "flag": flag_url(cid)})


@bp.post("/api/pin/answer")
def pin_answer():
    data = request.get_json(silent=True) or {}
    target = data.get("item_id")
    try:
        x, y = float(data["x"]), float(data["y"])
    except (KeyError, TypeError, ValueError):
        abort(400)
    if target not in GAME.pool:
        abort(400)

    s = score_click(target, x, y)
    clicked = s["clicked"] if s["clicked"] != target else None
    xp = None if s["correct"] else next((points for km, points in CLOSE_XP if s["distance"] <= km), 0)
    db, user_id = get_db(), current_user_id()
    xp = progress.record(db, user_id, "pin", target, f"{s['lat']:.2f}, {s['lon']:.2f}",
                         Result(s["correct"], guessed_id=clicked), xp=xp)

    return jsonify({
        "correct": s["correct"],
        "distance_km": round(s["distance"]),
        "answer": COUNTRY_BY_ID[target]["name"],
        "clicked": COUNTRY_BY_ID[clicked]["name"] if clicked else None,
        "click": [x, y],
        "nearest": list(s["nearest"]),
        "target": place(target),
        "clicked_place": place(clicked) if clicked else None,
        "xp": xp,
        "streak": progress.current_streak(db, user_id, "pin"),
        "fact": explain_outline(target, None, "")["fact"],
        "info": country_info(target),
        **achievements.after_play(db, user_id),
    })
