"""Helpers shared by the map games: country shapes, and saving multi-step rounds ('runs')."""

import json
from dataclasses import dataclass, field
from functools import cache

from flask import abort

import geo
from games import COUNTRIES, COUNTRY_BY_ID, OUTLINES, flag_url

# The 193 UN members, Vatican City, Palestine, Kosovo and Taiwan: the usual '197 countries'.
SOVEREIGN = [c["id"] for c in COUNTRIES if c["type"] != "territory"]
COUNTRIES_197 = [cid for cid in SOVEREIGN if cid != "ESH"]


@dataclass
class Challenge:
    slug: str
    name: str
    icon: str
    blurb: str
    pool: list = field(default_factory=list)  # countries it asks about and tracks mastery for (empty: none)
    kind: str = "challenge"
    ready: bool = True


@cache
def shapes():
    """Every country's outline on the world map, for 'which country did you click?' and distances."""
    return {cid: geo.Shape(o["loc"]["path"]) if o["loc"]["path"] else geo.Dot(o["loc"]["cx"], o["loc"]["cy"])
            for cid, o in OUTLINES.items()}


def inside(shape, x, y, world_width=1000):
    """Point-in-country on the wrap-around map: a few shapes poke past the date line (Russia's far east)."""
    return any(shape.contains(x + dx, y) for dx in (0, world_width, -world_width))


def country_at(x, y):
    return next((cid for cid, shape in shapes().items() if inside(shape, x, y)), None)


def place(cid):
    """What the map needs to show a country: its outline path, bounding box and centre."""
    return {"id": cid, "name": COUNTRY_BY_ID[cid]["name"], **OUTLINES[cid]["loc"]}


def card(cid):
    """A country as the game pages show it: name and flag."""
    return {"id": cid, "name": COUNTRY_BY_ID[cid]["name"], "flag": flag_url(cid)}


def union_box(ids):
    boxes = [OUTLINES[cid]["loc"]["box"] for cid in ids if cid in OUTLINES]
    return [min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes)]


def view_box(ids, world_width=1000, drop_giant=True):
    """A box that frames these countries on the wrap-around map.

    Countries across the date line are moved next to the others (Samoa beside Australia, not on the
    far left), and one giant that would squash everyone else (Russia, for Europe) is left out
    unless drop_giant is False.
    """
    boxes = {cid: list(OUTLINES[cid]["loc"]["box"]) for cid in ids if cid in OUTLINES}
    width = lambda b: b[2] - b[0]
    centre = lambda b: (b[0] + b[2]) / 2
    anchor = centre(boxes[max(boxes, key=lambda c: width(boxes[c]))])
    for b in boxes.values():
        shift = round((anchor - centre(b)) / world_width) * world_width
        b[0] += shift
        b[2] += shift

    def union(keys):
        return [min(boxes[k][0] for k in keys), min(boxes[k][1] for k in keys),
                max(boxes[k][2] for k in keys), max(boxes[k][3] for k in keys)]

    biggest = max(boxes, key=lambda c: width(boxes[c]))
    rest = [k for k in boxes if k != biggest]
    if drop_giant and rest and width(boxes[biggest]) > 2 * width(union(rest)):
        return union(rest)
    return union(boxes)


def neighbours_of(cid):
    return [b for b in COUNTRY_BY_ID[cid]["borders"] if b in COUNTRY_BY_ID]


# ---------- Runs: one round of a multi-step game, saved as it goes ----------

def start_run(db, user_id, game, state, variant="", total=None):
    run_id = db.execute(
        "INSERT INTO runs (user_id, game, variant, state, total) VALUES (%s, %s, %s, %s, %s) RETURNING id",
        (user_id, game, variant, json.dumps(state), total),
    ).fetchone()[0]
    db.commit()
    return run_id


def open_run(db, user_id, game, run_id):
    """The player's unfinished run, or a 404/409 error."""
    if not isinstance(run_id, int):
        abort(404)
    row = db.execute("SELECT * FROM runs WHERE id = %s AND user_id = %s AND game = %s", (run_id, user_id, game)).fetchone()
    if row is None:
        abort(404)
    if row["finished_at"] is not None:
        abort(409)
    return row, json.loads(row["state"])


def latest_open_run(db, user_id, game):
    """An unfinished round to pick up again (e.g. after leaving the page), or None."""
    row = db.execute(
        "SELECT * FROM runs WHERE user_id = %s AND game = %s AND finished_at IS NULL ORDER BY id DESC LIMIT 1",
        (user_id, game),
    ).fetchone()
    return (row, json.loads(row["state"])) if row else (None, None)


def save_run(db, run_id, state, score=None):
    db.execute("UPDATE runs SET state = %s, score = COALESCE(%s, score) WHERE id = %s", (json.dumps(state), score, run_id))
    db.commit()


def finish_run(db, run_id, state, score, solved=False, bonus_xp=0, max_seconds=None):
    """Close the round. Its length is measured by the server, capped at the time limit if there is one."""
    seconds = db.execute(
        """UPDATE runs SET state = %s, score = %s, solved = %s, bonus_xp = %s, finished_at = now(),
                  seconds = LEAST(ROUND(EXTRACT(EPOCH FROM now() - started_at))::int, COALESCE(%s::int, 1000000000))
           WHERE id = %s
           RETURNING seconds""",
        (json.dumps(state), score, int(solved), bonus_xp, max_seconds, run_id),
    ).fetchone()[0]
    db.commit()
    return seconds
