import re
import sqlite3
from pathlib import Path

from flask import Flask, abort, g, jsonify, render_template, request

import knowledge
import progress
from answers import Result, check
from games import COUNTRIES, GAME_BY_SLUG, GAMES, LANGS, LANGUAGES, OUTLINES, item_rows

BASE_DIR = Path(__file__).parent
DATABASE = BASE_DIR / "geo.db"
WORLD_SIZE = [float(n) for n in re.search(
    r'viewBox="0 0 (\S+) (\S+)"', (BASE_DIR / "static" / "world.svg").read_text()).groups()]

app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DATABASE) as db:
        db.executescript((BASE_DIR / "schema.sql").read_text())
        db.execute("DELETE FROM items")
        db.executemany("INSERT INTO items (game, item_id, name, region) VALUES (?, ?, ?, ?)", item_rows())


def current_user_id():
    # Single player for now. When logins arrive, this is the one place to change.
    return 1


def ready_game(slug):
    game = GAME_BY_SLUG.get(slug)
    if game is None or not game.ready:
        abort(404)
    return game


@app.context_processor
def inject_progress():
    """Makes `me` (XP, level, title) available in every template, for the header."""
    return {"me": progress.summary(get_db(), current_user_id())}


@app.route("/")
def index():
    return render_template("index.html", games=GAMES, country_count=len(COUNTRIES))


@app.route("/knowledge")
def knowledge_page():
    stats = knowledge.report(get_db(), current_user_id())
    lang_groups = {}
    for lang, info in LANGS.items():
        lang_groups.setdefault(LANGUAGES["groups"][info["group"]]["name"], []).append(lang)
    return render_template(
        "knowledge.html",
        games=GAMES,
        stats=stats,
        pools={g.slug: g.pool for g in GAMES},
        names={c["id"]: c["name"] for c in COUNTRIES},
        lang_groups=lang_groups,
    )


@app.route("/api/map")
def api_map():
    """Every country's shape on the world map, for colouring by mastery. Cached by the browser."""
    paths = {cid: o["loc"]["path"] for cid, o in OUTLINES.items() if o["loc"]["path"]}
    response = jsonify({"width": WORLD_SIZE[0], "height": WORLD_SIZE[1], "paths": paths})
    response.cache_control.max_age = 86400
    return response


@app.route("/<slug>")
def play(slug):
    return render_template("play.html", game=ready_game(slug))


@app.route("/api/me")
def api_me():
    return jsonify(progress.summary(get_db(), current_user_id()))


@app.get("/api/<slug>/next")
def api_next(slug):
    game = ready_game(slug)
    item_id = progress.pick_next(get_db(), current_user_id(), slug, game.pool)
    return jsonify({"item_id": item_id, "prompt": game.prompt(item_id)})


@app.post("/api/<slug>/answer")
def api_answer(slug):
    game = ready_game(slug)
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id")
    guess = str(data.get("guess", ""))[:100].strip()
    if item_id not in game.pool:
        abort(400)

    result = Result(False) if data.get("skip") else check(guess, item_id, game.names)
    db, user_id = get_db(), current_user_id()
    xp = progress.record(db, user_id, slug, item_id, guess, result)

    return jsonify({
        "correct": result.correct,
        "typo": result.typo,
        "skipped": bool(data.get("skip")),
        "answer": game.answer(item_id),
        "guessed": game.guessed(result.guessed_id) if result.guessed_id else None,
        "xp": xp,
        "streak": progress.current_streak(db, user_id, slug),
        "me": progress.summary(db, user_id),
        "locator": game.locate(item_id),
        "guessed_locator": game.locate(result.guessed_id) if result.guessed_id not in (None, item_id) else [],
        **game.explain(item_id, result.guessed_id, guess, data.get("context")),
    })


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5070)
