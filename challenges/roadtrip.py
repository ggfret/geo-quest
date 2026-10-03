"""🚗 Road trip: get from one country to another over land, crossing as few countries as possible.

You name the countries in between, in any order. Each one is coloured:
  green  - it's on a shortest route (there can be several, all equally short) that also goes through
           the green countries you've already named,
  yellow - you could pass through it, but it's a detour (or it's on another shortest route than the
           one your green countries are on: Niger and Algeria are alternatives, never both),
  red    - it can't be on the way at all: an island, another continent, or a dead end you'd have to leave
           the way you came in (like Portugal, which only borders Spain).
The round is won once the countries you've named link the two by land.
"""

import json
import math
import random
from collections import deque
from functools import cache, lru_cache

from flask import abort, jsonify, render_template, request

import achievements
import progress
from answers import Result, identify
from challenges import bp
from challenges.common import (COUNTRIES_197, Challenge, card, finish_run, latest_open_run, neighbours_of,
                               open_run, save_run, start_run, view_box)
from challenges.higherlower import STATS
from database import current_user_id, get_db
from games import COUNTRY_BY_ID, COUNTRY_NAMES

GAME = Challenge("roadtrip", "Road trip", "🚗", "Cross the fewest countries to get from one to another.")

GRAPH = {cid: neighbours_of(cid) for cid in COUNTRY_BY_ID}

LEVELS = {
    "easy": {"name": "Easy", "between": (2, 4), "extra": 4, "xp": 15,
             "about": "2–4 countries in between, all of them well known."},
    "medium": {"name": "Medium", "between": (5, 6), "extra": 5, "xp": 25,
               "about": "5–6 countries in between, still mostly well known."},
    "hard": {"name": "Hard", "between": (7, 10), "extra": 6, "xp": 40,
             "about": "7–10 countries in between, often through small or lesser-known ones."},
}
WASTED_GUESS_XP = 3   # less XP for every guess beyond the shortest route
MIN_WIN_XP = 5
GREEN_XP = 2          # for each green country when the round isn't finished
RECENT_PAIRS = 30     # don't repeat a pair from your last 30 rounds

# Easy and Medium only use countries most people have heard of: roughly the 110 biggest economies,
# plus a few that are famous anyway. Hard can go anywhere (Eswatini, Djibouti, Liechtenstein, ...).
FAMOUS_ANYWAY = {"PRK", "MNG", "YEM", "SOM", "ALB", "MOZ", "NAM", "BWA", "HTI", "RWA"}
WELL_KNOWN_ENDS = 80   # Easy starts and ends in one of the 80 biggest economies


@cache
def fame_rank():
    """The countries a trip can start or end in, from best to least known (by the size of their economy)."""
    def economy(cid):
        s = STATS.get(cid, {})
        return (s.get("population") or 0) * (s.get("gdp") or 0)

    ranked = sorted((cid for cid in COUNTRIES_197 if GRAPH[cid]), key=economy, reverse=True)
    return {cid: i for i, cid in enumerate(ranked)}


def familiar(cid, top=110):
    return fame_rank().get(cid, math.inf) < top or cid in FAMOUS_ANYWAY


# ---------- Routes ----------

@lru_cache(maxsize=4096)
def distances(start, allowed=None):
    """Borders crossed to reach each country from `start` (only through `allowed` countries, if given).

    The result is cached: don't change it.
    """
    seen = {start: 0}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        for nxt in GRAPH[here]:
            if nxt not in seen and (allowed is None or nxt in allowed):
                seen[nxt] = seen[here] + 1
                queue.append(nxt)
    return seen


def between(a, b):
    """How many countries lie between a and b on the shortest route (None if there's no land route)."""
    d = distances(a).get(b)
    return None if d is None else d - 1


def on_shortest_route(a, b):
    """Every country that is on at least one of the shortest routes."""
    da, db, total = distances(a), distances(b), distances(a)[b]
    return {c for c in da if c not in (a, b) and da[c] + db.get(c, math.inf) == total}


def one_shortest_route(a, b, allowed=None):
    """The countries between a and b along one shortest route (passing only through `allowed` ones, if given)."""
    to_b = distances(b, None if allowed is None else frozenset(allowed) | {a})
    if a not in to_b:
        return None
    route, here = [], a
    while to_b[here] > 1:
        here = min((n for n in GRAPH[here] if to_b.get(n) == to_b[here] - 1), key=lambda n: COUNTRY_BY_ID[n]["name"])
        route.append(here)
    return route


def count_shortest_routes(a, b):
    da, db = distances(a), distances(b)
    ways = {a: 1}
    for c in sorted(da, key=da.get):
        if c != a and da[c] + db.get(c, math.inf) == da[b]:
            ways[c] = sum(ways.get(p, 0) for p in GRAPH[c] if da.get(p) == da[c] - 1)
    return ways[b]


def route_through(a, b, x):
    """Countries between a and b on the shortest route that passes through x without visiting any
    country twice, or None if there's no such route.

    It's two paths leaving x, one to a and one to b, that share no country: a minimum-cost flow of 2
    from x, where every country can be used once (each one is split into an 'in' and 'out' node).
    """
    reachable = distances(a)
    if x not in reachable or b not in reachable:
        return None
    index = {c: i for i, c in enumerate(reachable)}
    sink = 2 * len(index)
    edges = [[] for _ in range(sink + 1)]  # [to, capacity, cost, index of the reverse edge]

    def add(u, v, cost):
        edges[u].append([v, 1, cost, len(edges[v])])
        edges[v].append([u, 0, -cost, len(edges[u]) - 1])

    for c, i in index.items():
        if c in (a, b):
            add(2 * i, sink, 0)          # a path ends here
            continue
        if c != x:
            add(2 * i, 2 * i + 1, 1)     # passing through costs one country
        for n in GRAPH[c]:
            if n != x:
                add(2 * i + 1, 2 * index[n], 0)

    source, cost = 2 * index[x] + 1, 0
    for _ in range(2):
        # Cheapest path in what's left (SPFA: Bellman-Ford with a queue, as undoing a step has a negative cost).
        dist, prev = {source: 0}, {}
        queue, queued = deque([source]), {source}
        while queue:
            u = queue.popleft()
            queued.discard(u)
            for k, (v, cap, c, _) in enumerate(edges[u]):
                if cap and dist[u] + c < dist.get(v, math.inf):
                    dist[v], prev[v] = dist[u] + c, (u, k)
                    if v not in queued:
                        queue.append(v)
                        queued.add(v)
        if sink not in dist:
            return None
        v = sink
        while v != source:
            u, k = prev[v]
            edges[u][k][1] -= 1
            edges[v][edges[u][k][3]][1] += 1
            v = u
        cost += dist[sink]
    return cost + 1  # the countries on both paths, plus x itself


def same_route(a, x, y):
    """Can x and y (both on shortest routes from a) be on the same shortest route?

    A shortest route takes one step further from a with every country, so they fit together if the
    one further away is exactly that many steps beyond the other. Two at the same distance never fit.
    """
    near, far = sorted((x, y), key=distances(a).get)
    return distances(near).get(far) == distances(a)[far] - distances(a)[near]


def judge(a, b, x, earlier=()):
    """Colour a guessed country: green, yellow or red, with a short reason.

    `earlier` are the guesses so far: a green one must fit on one shortest route with the earlier greens.
    """
    name = COUNTRY_BY_ID[x]["name"]
    if x in on_shortest_route(a, b):
        clash = [g["name"] for g in earlier if g["colour"] == "green" and not same_route(a, g["id"], x)]
        if not clash:
            return {"id": x, "name": name, "colour": "green", "why": "on a shortest route"}
        return {"id": x, "name": name, "colour": "yellow",
                "why": f"a detour from your route: it's on another shortest route, not the one through {' and '.join(clash)}"}
    if x not in distances(a):
        why = "an island: no land borders at all" if not GRAPH[x] else f"not connected to {COUNTRY_BY_ID[a]['name']} by land"
        return {"id": x, "name": name, "colour": "red", "why": why}
    length = route_through(a, b, x)
    if length is None:
        return {"id": x, "name": name, "colour": "red",
                "why": "a dead end: you'd have to leave the way you came in"}
    extra = length - between(a, b)
    return {"id": x, "name": name, "colour": "yellow", "extra": extra,
            "why": f"a detour: {extra} more countr{'y' if extra == 1 else 'ies'} than the shortest route"}


def linked_route(a, b, guesses):
    """The shortest way from a to b through the (non-red) countries you've named, or None if they don't link up yet."""
    return one_shortest_route(a, b, [g["id"] for g in guesses if g["colour"] != "red"])


# ---------- Picking a trip ----------

@cache
def pairs(level):
    """Every (start, end) pair for a level, each pair once."""
    low, high = LEVELS[level]["between"]
    ranks = fame_rank()
    if level == "hard":
        ends, via = list(ranks), None
    else:
        top = WELL_KNOWN_ENDS if level == "easy" else 110
        ends = [c for c in ranks if ranks[c] < top or c in FAMOUS_ANYWAY]
        via = frozenset(c for c in GRAPH if familiar(c))
    found = []
    for a in ends:
        for b in ends:
            n = between(a, b)
            if a < b and n is not None and low <= n <= high:
                # Easy and Medium need at least one shortest route through well-known countries only.
                route = one_shortest_route(a, b, via) if via else None
                if via is None or (route is not None and len(route) == n):
                    found.append((a, b))
    return found


def pick_pair(db, user_id, level):
    rows = db.execute("SELECT state FROM runs WHERE user_id = ? AND game = 'roadtrip' ORDER BY id DESC LIMIT ?",
                      (user_id, RECENT_PAIRS)).fetchall()
    recent = {frozenset((s["start"], s["end"])) for s in (json.loads(r[0]) for r in rows)}
    options = [p for p in pairs(level) if frozenset(p) not in recent] or pairs(level)
    a, b = random.choice(options)
    return (a, b) if random.random() < 0.5 else (b, a)


# ---------- The round ----------

def board(run_id, state):
    """The round as the page shows it."""
    a, b = state["start"], state["end"]
    return {
        "run_id": run_id,
        "level": state["level"],
        "level_name": LEVELS[state["level"]]["name"],
        "start": card(a),
        "end": card(b),
        "between": between(a, b),
        "max_guesses": state["max_guesses"],
        "guesses": state["guesses"],
        "view": view_box([a, b], drop_giant=False),
    }


def end(db, user_id, row, state, won):
    """Finish the round: XP, the route you found, and a shortest one to compare."""
    a, b, level = state["start"], state["end"], state["level"]
    shortest = between(a, b)
    used = len(state["guesses"])
    greens = sum(g["colour"] == "green" for g in state["guesses"])
    if won:
        xp = max(MIN_WIN_XP, LEVELS[level]["xp"] - WASTED_GUESS_XP * (used - shortest))
    else:
        xp = GREEN_XP * greens
    yours = linked_route(a, b, state["guesses"]) if won else None
    route_text = " → ".join(COUNTRY_BY_ID[c]["name"] for c in yours) if yours else f"{greens} green"
    xp = progress.record(db, user_id, "roadtrip", f"{a}-{b}", route_text, Result(won), xp=xp, mastery=False)
    finish_run(db, row["id"], state, score=used, solved=won)
    return {
        "finished": True,
        "won": won,
        "perfect": won and used == shortest,
        "used": used,
        "xp": xp,
        "your_route": [card(c) for c in yours] if yours else None,
        "shortest_route": [card(c) for c in one_shortest_route(a, b)],
        "other_routes": count_shortest_routes(a, b) - 1,
        "on_shortest": sorted(on_shortest_route(a, b)),  # every country on any shortest route, for the map
        "route_view": view_box([a, b, *on_shortest_route(a, b)]),  # frames them (without all of Russia)
        **achievements.after_play(db, user_id),
    }


@bp.route("/roadtrip")
def roadtrip_page():
    return render_template("roadtrip.html", game=GAME, levels=LEVELS)


@bp.post("/api/roadtrip/start")
def roadtrip_start():
    """Start a trip at a level, or (with no level) pick up an unfinished one."""
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    level = data.get("level")
    if level is None:
        row, state = latest_open_run(db, user_id, "roadtrip")
        return jsonify(board(row["id"], state) if row else {"run_id": None})
    if level not in LEVELS:
        abort(400)
    a, b = pick_pair(db, user_id, level)
    state = {"start": a, "end": b, "level": level, "guesses": [],
             "max_guesses": between(a, b) + LEVELS[level]["extra"]}
    run_id = start_run(db, user_id, "roadtrip", state, variant=level, total=between(a, b))
    return jsonify(board(run_id, state))


@bp.post("/api/roadtrip/guess")
def roadtrip_guess():
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    row, state = open_run(db, user_id, "roadtrip", data.get("run_id"))
    a, b = state["start"], state["end"]
    guess_id, typo = identify(str(data.get("guess", ""))[:100], COUNTRY_NAMES)

    if guess_id is None:
        return jsonify({"status": "unknown", **board(row["id"], state)})
    name = COUNTRY_BY_ID[guess_id]["name"]
    if guess_id in (a, b):
        return jsonify({"status": "endpoint", "name": name, **board(row["id"], state)})
    if any(g["id"] == guess_id for g in state["guesses"]):
        return jsonify({"status": "repeat", "name": name, **board(row["id"], state)})

    verdict = judge(a, b, guess_id, state["guesses"])
    state["guesses"].append(verdict)
    save_run(db, row["id"], state, score=len(state["guesses"]))

    result = {"status": "guess", "verdict": verdict, "typo": typo, **board(row["id"], state)}
    if linked_route(a, b, state["guesses"]) is not None:
        result.update(end(db, user_id, row, state, won=True))
    elif len(state["guesses"]) >= state["max_guesses"]:
        result.update(end(db, user_id, row, state, won=False))
    return jsonify(result)


@bp.post("/api/roadtrip/give-up")
def roadtrip_give_up():
    data = request.get_json(silent=True) or {}
    db, user_id = get_db(), current_user_id()
    row, state = open_run(db, user_id, "roadtrip", data.get("run_id"))
    return jsonify({"status": "gave_up", **board(row["id"], state), **end(db, user_id, row, state, won=False)})
