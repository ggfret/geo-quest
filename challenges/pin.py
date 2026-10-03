"""📍 Pin it: you're given a country and pick it on the world map (click it and it lights up)."""

from flask import abort, jsonify, render_template, request

import achievements
import geo
import progress
from answers import Result
from challenges import bp
from challenges.common import Challenge, neighbours_of, place, shapes
from database import current_user_id, get_db
from games import COUNTRY_BY_ID, OUTLINES, country_info, explain_outline, flag_url

GAME = Challenge("pin", "Pin it", "📍", "Find the country on a blank map.", pool=sorted(OUTLINES))

NEAR_KM = 50            # tiny countries (Vatican City, Malta, Tuvalu, ...): a click this close counts
CLOSE_XP = [(300, 4), (1000, 2)]  # some XP for near misses: within 300 km -> 4 XP, within 1,000 km -> 2 XP
CANDIDATES = 40         # corners compared when measuring the gap between two countries


def _closest_corners(corners, box, world_width=1000):
    """The corners nearest to a box on the map (on the wrap-around map), to keep gap() fast for Canada or Russia."""
    x0, y0, x1, y1 = box

    def away(corner):
        (x, y), _ = corner
        dx = min(abs(x + s - min(max(x + s, x0), x1)) for s in (0, world_width, -world_width))
        dy = y - min(max(y, y0), y1)
        return dx * dx + dy * dy

    return sorted(corners, key=away)[:CANDIDATES]


def gap(a, b):
    """How far apart two countries are: km between their outlines (0 if they share a border),
    and the two closest points on the map, for drawing a line between them."""
    if a == b or b in neighbours_of(a):
        return 0, None
    near_b = _closest_corners(shapes()[a].corners(), OUTLINES[b]["loc"]["box"])
    near_a = _closest_corners(shapes()[b].corners(), OUTLINES[a]["loc"]["box"])
    km, xy_a, xy_b = min((geo.distance_km(*ll_a, *ll_b), xy_a, xy_b) for xy_a, ll_a in near_b for xy_b, ll_b in near_a)
    return km, (xy_a, xy_b)


def is_correct(target, pick, x, y):
    """Right if you picked the country. Tiny ones are hard to hit, so a click within 50 km of them counts too."""
    if pick == target:
        return True
    if OUTLINES[target]["quiz"] or x is None:
        return False
    lon, lat = geo.lonlat(x, y)
    return shapes()[target].nearest(lat, lon)[0] <= NEAR_KM


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
    target, pick = data.get("item_id"), data.get("pick")
    if target not in GAME.pool or pick not in OUTLINES:
        abort(400)
    try:
        x, y = (float(data["x"]), float(data["y"])) if "x" in data else (None, None)
    except (KeyError, TypeError, ValueError):
        abort(400)

    correct = is_correct(target, pick, x, y)
    km, line = (0, None) if correct else gap(pick, target)
    xp = None if correct else next((points for limit, points in CLOSE_XP if km <= limit), 0)
    db, user_id = get_db(), current_user_id()
    xp = progress.record(db, user_id, "pin", target, COUNTRY_BY_ID[pick]["name"],
                         Result(correct, guessed_id=None if correct else pick), xp=xp)

    return jsonify({
        "correct": correct,
        "distance_km": round(km),
        "neighbour": not correct and target in neighbours_of(pick),
        "answer": COUNTRY_BY_ID[target]["name"],
        "picked": COUNTRY_BY_ID[pick]["name"],
        "target": place(target),
        "picked_place": place(pick),
        "line": [*line[0], *line[1]] if line else None,
        "xp": xp,
        "streak": progress.current_streak(db, user_id, "pin"),
        "fact": explain_outline(target, None, "")["fact"],
        "info": country_info(target),
        **achievements.after_play(db, user_id),
    })
