"""⏱️ Name them all: type every country of a continent (or the world) before the time runs out.

Correct names are accepted in the browser as soon as they're typed (the page gets each country's accepted
spellings); Enter asks the server, which also forgives small typos. At the end every country is saved as
remembered or forgotten, so the Knowledge page learns which ones slip your mind.
"""

import math

from flask import abort, jsonify, render_template, request

import achievements
import leaderboard
import progress
from answers import Result, identify, normalize
from challenges import bp
from challenges.common import COUNTRIES_197, Challenge, finish_run, open_run, place, start_run, view_box
from database import current_user_id, get_db
from games import COUNTRY_BY_ID, COUNTRY_NAMES

GAME = Challenge("nameall", "Name them all", "⏱️", "Name every country of a continent before time runs out.",
                 pool=COUNTRIES_197)

CONTINENTS = ["Africa", "Asia", "Europe", "North America", "South America", "Oceania"]
VARIANTS = {"world": "The whole world", **{c.lower().replace(" ", "-"): c for c in CONTINENTS}}
TARGETS = {
    "world": COUNTRIES_197,
    **{slug: [cid for cid in COUNTRIES_197 if COUNTRY_BY_ID[cid]["continent"] == name]
       for slug, name in VARIANTS.items() if slug != "world"},
}
# About 10 seconds per country, 3-10 minutes for a continent; 15 minutes for the world.
SECONDS = {slug: 15 * 60 if slug == "world" else 60 * min(10, max(3, math.ceil(len(ids) / 6)))
           for slug, ids in TARGETS.items()}
XP_PER_COUNTRY = 2   # plus a bonus of the same again for naming every single one


def variant_list(user_id=None, db=None):
    bests = leaderboard.personal_bests(db, user_id)["nameall"] if db else {}
    return [{"slug": slug, "name": name, "total": len(TARGETS[slug]), "minutes": SECONDS[slug] // 60,
             "best": bests.get(slug)} for slug, name in VARIANTS.items()]


@bp.route("/nameall")
def nameall_page():
    return render_template("nameall.html", game=GAME, variants=variant_list(current_user_id(), get_db()))


@bp.post("/api/nameall/start")
def nameall_start():
    data = request.get_json(silent=True) or {}
    variant = data.get("variant")
    if variant not in TARGETS:
        abort(400)
    ids = TARGETS[variant]
    db, user_id = get_db(), current_user_id()
    run_id = start_run(db, user_id, "nameall", {}, variant=variant, total=len(ids))
    return jsonify({
        "run_id": run_id,
        "title": VARIANTS[variant],
        "seconds": SECONDS[variant],
        "total": len(ids),
        # Every accepted spelling, already simplified the same way the page simplifies what you type.
        "targets": [{"id": cid, "name": COUNTRY_BY_ID[cid]["name"],
                     "names": sorted({normalize(n) for n in COUNTRY_NAMES[cid]})} for cid in ids],
        "view": view_box(ids) if variant != "world" else None,
    })


@bp.post("/api/nameall/check")
def nameall_check():
    """Enter pressed on something that isn't an exact name: allow a typo, or explain why it doesn't count."""
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    row, _ = open_run(db, user_id, "nameall", data.get("run_id"))
    cid, typo = identify(str(data.get("guess", ""))[:100], COUNTRY_NAMES)
    if cid is None:
        return jsonify({"ok": False, "message": "That's not a country I know."})
    c = COUNTRY_BY_ID[cid]
    if cid in TARGETS[row["variant"]]:
        return jsonify({"ok": True, "id": cid, "name": c["name"], "typo": typo})
    if cid not in COUNTRIES_197:
        return jsonify({"ok": False, "message": f"{c['name']} isn't counted as a country here ({c['type']})."})
    return jsonify({"ok": False, "message": f"{c['name']} is in {c['continent']}."})


@bp.post("/api/nameall/finish")
def nameall_finish():
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    row, _ = open_run(db, user_id, "nameall", data.get("run_id"))
    variant = row["variant"]
    ids = TARGETS[variant]
    found = [cid for cid in dict.fromkeys(data.get("found") or []) if cid in ids]
    best_before = leaderboard.personal_bests(db, user_id)["nameall"].get(variant)

    # Every country of the round counts as remembered or forgotten.
    xp = 0
    for cid in ids:
        remembered = cid in found
        xp += progress.record(db, user_id, "nameall", cid, COUNTRY_BY_ID[cid]["name"] if remembered else "",
                              Result(remembered), xp=XP_PER_COUNTRY if remembered else 0, commit=False)
    bonus = len(ids) if len(found) == len(ids) else 0
    seconds = finish_run(db, row["id"], {"found": found}, score=len(found), solved=bool(bonus),
                         bonus_xp=bonus, max_seconds=SECONDS[variant])
    new_best = best_before is None or (len(found), -seconds) > (best_before["score"], -best_before["seconds"])

    return jsonify({
        "score": len(found),
        "total": len(ids),
        "seconds": seconds,
        "xp": xp + bonus,
        "bonus": bonus,
        "new_best": new_best and len(found) > 0,
        "best_before": best_before,
        "missed": [place(cid) for cid in ids if cid not in found],
        **achievements.after_play(db, user_id),
    })
