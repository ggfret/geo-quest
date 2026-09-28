import os
import re
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

import achievements
import auth
import challenges
import knowledge
import leaderboard
import progress
from answers import Result, check
from database import close_db, current_user_id, get_db
from games import COUNTRIES, GAME_BY_SLUG, GAMES, LANGS, LANGUAGES, OUTLINES, item_rows

BASE_DIR = Path(__file__).parent
WORLD_SIZE = [float(n) for n in re.search(
    r'viewBox="0 0 (\S+) (\S+)"', (BASE_DIR / "static" / "world.svg").read_text()).groups()]
ALL_GAMES = [*GAMES, *challenges.CHALLENGES]

app = Flask(__name__)
app.config.update(
    DATABASE=Path(os.environ.get("GEO_DATABASE", BASE_DIR / "geo.db")),  # GEO_DATABASE: use another database file
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("GEO_HTTPS") == "1",  # online: only send the login cookie over HTTPS
    INVITE_CODE=os.environ.get("GEO_INVITE_CODE"),             # online: only people with this code can sign up
)
app.register_blueprint(challenges.bp)
app.teardown_appcontext(close_db)


def load_secret_key():
    """Signs the login cookie. From GEO_SECRET_KEY if set (online), else a random key kept in instance/."""
    if os.environ.get("GEO_SECRET_KEY"):
        return os.environ["GEO_SECRET_KEY"]
    path = BASE_DIR / "instance" / "secret_key"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        path.write_text(secrets.token_hex(32))
    return path.read_text().strip()


app.secret_key = load_secret_key()


def init_db():
    with sqlite3.connect(app.config["DATABASE"]) as db:
        db.executescript((BASE_DIR / "schema.sql").read_text())
        auth.migrate(db)
        db.execute("DELETE FROM items")
        db.executemany("INSERT INTO items (game, item_id, name, region) VALUES (?, ?, ?, ?)",
                       [*item_rows(), *challenges.item_rows()])


PUBLIC_ENDPOINTS = {"login", "signup", "static"}


@app.before_request
def require_login():
    """Everything except the login and sign-up pages needs an account."""
    if request.endpoint in PUBLIC_ENDPOINTS or current_user_id():
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": "Please log in."}), 401
    return redirect(url_for("login", next=request.path))


def start_session(user_id):
    session.clear()
    session["user_id"] = user_id
    session.permanent = True


def ready_game(slug):
    game = GAME_BY_SLUG.get(slug)
    if game is None or not game.ready:
        abort(404)
    return game


@app.context_processor
def inject_progress():
    """Makes `me` (name, XP, level, streak, daily goal) available in every template, for the header."""
    user_id = current_user_id()
    if not user_id:
        return {"me": None}
    name = get_db().execute("SELECT name FROM users WHERE id = ?", (user_id,)).fetchone()
    return {"me": {**progress.summary(get_db(), user_id), "name": name["name"] if name else "?"}}


def safe_next(target):
    """Only redirect back to pages on this site after logging in."""
    return target if target and target.startswith("/") and not target.startswith("//") else url_for("index")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    db = get_db()
    legacy = auth.unclaimed_answers(db)
    error = None
    if request.method == "POST":
        try:
            user_id = auth.sign_up(
                db, request.form.get("username", ""), request.form.get("password", ""),
                claim_legacy=bool(request.form.get("claim")),
                invite=request.form.get("invite", ""),
                required_invite=app.config["INVITE_CODE"],
            )
            start_session(user_id)
            return redirect(safe_next(request.args.get("next")))
        except auth.AuthError as e:
            error = str(e)
    return render_template("auth.html", mode="signup", error=error, legacy=legacy)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        try:
            start_session(auth.log_in(get_db(), request.form.get("username", ""), request.form.get("password", "")))
            return redirect(safe_next(request.args.get("next")))
        except auth.AuthError as e:
            error = str(e)
    return render_template("auth.html", mode="login", error=error, legacy=0)


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/leaderboard")
def leaderboard_page():
    db = get_db()
    tab = request.args.get("tab", "week")
    if tab not in ("week", "all", "records"):
        tab = "week"
    return render_template(
        "leaderboard.html",
        tab=tab,
        rows=leaderboard.all_time(db) if tab == "all" else leaderboard.weekly(db),
        records=leaderboard.records(db) if tab == "records" else None,
        nameall_variants=challenges.nameall.VARIANTS,
        higherlower_variants=challenges.higherlower.VARIANTS,
        me_id=current_user_id(),
    )


@app.route("/")
def index():
    db, user_id = get_db(), current_user_id()
    due = progress.due_counts(db, user_id)
    week = leaderboard.weekly(db)
    rank = next((i + 1 for i, p in enumerate(week) if p["id"] == user_id), None)
    return render_template(
        "index.html",
        quizzes=GAMES,
        map_games=challenges.CHALLENGES,
        country_count=len(COUNTRIES),
        due=due,
        due_total=sum(due.values()),
        review_game=next((g for g in ALL_GAMES if due and g.slug == max(due, key=due.get)), None),
        rank=rank,
        players=len(week),
        known=knowledge.per_game(db, user_id),
    )


@app.route("/knowledge")
def knowledge_page():
    stats = knowledge.report(get_db(), current_user_id())
    lang_groups = {}
    for lang, info in LANGS.items():
        lang_groups.setdefault(LANGUAGES["groups"][info["group"]]["name"], []).append(lang)
    return render_template(
        "knowledge.html",
        games=ALL_GAMES,
        map_tabs=[g for g in ALL_GAMES if g.pool],
        stats=stats,
        pools={g.slug: g.pool for g in ALL_GAMES if g.pool},
        names={c["id"]: c["name"] for c in COUNTRIES},
        lang_groups=lang_groups,
        nameall_variants=challenges.nameall.VARIANTS,
        higherlower_variants=challenges.higherlower.VARIANTS,
    )


@app.route("/api/map")
def api_map():
    """Every country's shape on the world map (plus box and centre, for tiny ones). Cached by the browser."""
    response = jsonify({
        "width": WORLD_SIZE[0],
        "height": WORLD_SIZE[1],
        "paths": {cid: o["loc"]["path"] for cid, o in OUTLINES.items() if o["loc"]["path"]},
        "places": {cid: {"box": o["loc"]["box"], "cx": o["loc"]["cx"], "cy": o["loc"]["cy"]} for cid, o in OUTLINES.items()},
    })
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
        "locator": game.locate(item_id),
        "guessed_locator": game.locate(result.guessed_id) if result.guessed_id not in (None, item_id) else [],
        **game.explain(item_id, result.guessed_id, guess, data.get("context")),
        **achievements.after_play(db, user_id),
    })


init_db()

if __name__ == "__main__":
    app.run(debug=True, port=int(os.environ.get("PORT", 5070)))
