"""Achievements: badges for milestones, each worth some XP. Checked after every answer."""

from dataclasses import dataclass
from typing import Callable

import progress

MASTERED_BOX = 4


@dataclass
class Achievement:
    code: str
    icon: str
    name: str
    description: str
    xp: int
    check: Callable  # (db, user_id) -> bool


def _one(db, sql, *args):
    return db.execute(sql, args).fetchone()[0] or 0


def answers(db, u):
    return _one(db, "SELECT COUNT(*) FROM attempts WHERE user_id = %s", u)


def known(db, u, game=None):
    if game:
        return _one(db, "SELECT COUNT(*) FROM mastery WHERE user_id = %s AND game = %s AND box >= %s", u, game, MASTERED_BOX)
    return _one(db, "SELECT COUNT(*) FROM mastery WHERE user_id = %s AND box >= %s", u, MASTERED_BOX)


def knows_whole_region(db, u, game, region):
    """True if every item of this game in this region is known."""
    missing = _one(db, """SELECT COUNT(*) FROM items i
                          LEFT JOIN mastery m ON m.user_id = %s AND m.game = i.game AND m.item_id = i.item_id
                          WHERE i.game = %s AND i.region = %s AND COALESCE(m.box, 0) < %s""",
                   u, game, region, MASTERED_BOX)
    return missing == 0


def best_answer_streak(db, u):
    """Longest current run of correct answers in any game (Name them all doesn't count: it saves a whole list at once)."""
    games = [g for (g,) in db.execute("SELECT DISTINCT game FROM attempts WHERE user_id = %s AND game != 'nameall'", (u,))]
    return max((progress.current_streak(db, u, g) for g in games), default=0)


def best_day(db, u):
    return _one(db, "SELECT MAX(xp) FROM (SELECT SUM(xp) AS xp FROM xp_events WHERE user_id = %s GROUP BY at::date) AS days", u)


def run_exists(db, u, game, condition, *args):
    return _one(db, f"SELECT COUNT(*) FROM runs WHERE user_id = %s AND game = %s AND finished_at IS NOT NULL AND {condition}",
                u, game, *args) > 0


def games_played(db, u):
    return _one(db, "SELECT COUNT(DISTINCT game) FROM attempts WHERE user_id = %s", u)


def weeks_won(db, u):
    """Finished weeks (Monday to Sunday, UTC) where this player had the most XP, out of at least two players."""
    return _one(db, f"""
        WITH weekly AS (
            SELECT user_id, date_trunc('week', at) AS week, SUM(xp) AS xp
            FROM xp_events WHERE at < {progress.WEEK_START}
            GROUP BY user_id, week
        )
        SELECT COUNT(*) FROM weekly w
        WHERE w.user_id = %s
          AND w.xp = (SELECT MAX(xp) FROM weekly w2 WHERE w2.week = w.week)
          AND (SELECT COUNT(*) FROM weekly w3 WHERE w3.week = w.week) >= 2""", u)


ALL_GAMES = 11

ACHIEVEMENTS = [
    # Getting going
    Achievement("first_steps", "👣", "First steps", "Answer your first question.", 10,
                lambda db, u: answers(db, u) >= 1),
    Achievement("century", "💯", "Century", "Give 100 answers.", 50,
                lambda db, u: answers(db, u) >= 100),
    Achievement("thousand", "🏔️", "Thousand", "Give 1,000 answers.", 200,
                lambda db, u: answers(db, u) >= 1000),
    Achievement("all_rounder", "🎯", "All-rounder", "Play all eleven games.", 50,
                lambda db, u: games_played(db, u) >= ALL_GAMES),
    # Habits
    Achievement("goal_getter", "✅", "Goal getter", f"Reach the daily goal of {progress.DAILY_GOAL} XP.", 20,
                lambda db, u: best_day(db, u) >= progress.DAILY_GOAL),
    Achievement("daily_habit", "📅", "Daily habit", "Play 7 days in a row.", 70,
                lambda db, u: progress.day_streak(db, u)["streak"] >= 7),
    Achievement("month_of_maps", "🗓️", "Month of maps", "Play 30 days in a row.", 300,
                lambda db, u: progress.day_streak(db, u)["streak"] >= 30),
    Achievement("hot_streak", "🔥", "Hot streak", "Get 10 answers right in a row in one game.", 30,
                lambda db, u: best_answer_streak(db, u) >= 10),
    Achievement("unstoppable", "⚡", "Unstoppable", "Get 25 answers right in a row in one game.", 100,
                lambda db, u: best_answer_streak(db, u) >= 25),
    # Knowledge
    Achievement("flag_spotter", "🏳️", "Flag spotter", "Know 50 flags.", 50,
                lambda db, u: known(db, u, "flags") >= 50),
    Achievement("european_flags", "🇪🇺", "Flags of Europe", "Know every European flag.", 150,
                lambda db, u: knows_whole_region(db, u, "flags", "Europe")),
    Achievement("capital_collector", "🏛️", "Capital collector", "Know 50 capitals.", 50,
                lambda db, u: known(db, u, "capitals") >= 50),
    Achievement("shape_shifter", "🗺️", "Shape shifter", "Know 50 country outlines.", 50,
                lambda db, u: known(db, u, "outlines") >= 50),
    Achievement("polyglot", "🗣️", "Polyglot", "Know 30 languages.", 80,
                lambda db, u: known(db, u, "languages") >= 30),
    Achievement("walking_atlas", "🧭", "Walking atlas", "Know 500 things across all games.", 300,
                lambda db, u: known(db, u) >= 500),
    # Map games
    Achievement("bullseye", "📍", "Bullseye", "Pin 10 countries in a row.", 60,
                lambda db, u: progress.current_streak(db, u, "pin") >= 10),
    Achievement("lucky_guess", "🍀", "Lucky guess", "Solve Hot & Cold on the first guess.", 30,
                lambda db, u: run_exists(db, u, "hotcold", "solved = 1 AND score = 1")),
    Achievement("sharp_shooter", "🎯", "Sharp shooter", "Solve Hot & Cold in 3 guesses or fewer.", 40,
                lambda db, u: run_exists(db, u, "hotcold", "solved = 1 AND score <= 3")),
    Achievement("good_neighbour", "🤝", "Good neighbour", "Name every neighbour of a country with 8 or more.", 80,
                lambda db, u: run_exists(db, u, "neighbours", "solved = 1 AND total >= 8")),
    Achievement("road_tripper", "🚗", "Road tripper", "Finish 10 road trips.", 50,
                lambda db, u: _one(db, "SELECT COUNT(*) FROM runs WHERE user_id = %s AND game = 'roadtrip' AND solved = 1", u) >= 10),
    Achievement("shortcut", "🛣️", "Shortcut", "Find the shortest route on Hard without a wasted guess.", 100,
                lambda db, u: run_exists(db, u, "roadtrip", "variant = 'hard' AND solved = 1 AND score = total")),
    Achievement("full_house", "⏱️", "Full house", "Name every country of a continent.", 100,
                lambda db, u: run_exists(db, u, "nameall", "variant != 'world' AND score = total")),
    Achievement("world_traveller", "✈️", "World traveller", "Name 100 countries in one World round.", 100,
                lambda db, u: run_exists(db, u, "nameall", "variant = 'world' AND score >= 100")),
    Achievement("whole_world", "🌍", "The whole world", "Name all 197 countries.", 500,
                lambda db, u: run_exists(db, u, "nameall", "variant = 'world' AND score = total")),
    Achievement("number_cruncher", "🔢", "Number cruncher", "Reach a streak of 10 in Higher or Lower.", 50,
                lambda db, u: run_exists(db, u, "higherlower", "score >= 10")),
    Achievement("human_almanac", "📚", "Human almanac", "Reach a streak of 25 in Higher or Lower.", 150,
                lambda db, u: run_exists(db, u, "higherlower", "score >= 25")),
    # Friends
    Achievement("champion", "👑", "Weekly champion", "Finish a week at the top of the league.", 100,
                lambda db, u: weeks_won(db, u) >= 1),
]
BY_CODE = {a.code: a for a in ACHIEVEMENTS}


def check(db, user_id):
    """Unlock anything newly earned. Returns the new ones, for a 'badge unlocked' message."""
    have = {code for (code,) in db.execute("SELECT code FROM achievements WHERE user_id = %s", (user_id,))}
    new = [a for a in ACHIEVEMENTS if a.code not in have and a.check(db, user_id)]
    for a in new:
        db.execute("INSERT INTO achievements (user_id, code, xp) VALUES (%s, %s, %s)", (user_id, a.code, a.xp))
    if new:
        db.commit()
    return [{"code": a.code, "icon": a.icon, "name": a.name, "xp": a.xp} for a in new]


def after_play(db, user_id):
    """What every answer returns besides its own result: new badges and the updated header numbers."""
    unlocked = check(db, user_id)
    return {"unlocked": unlocked, "me": progress.summary(db, user_id)}


def listing(db, user_id):
    """Every achievement, with when (or whether) this player unlocked it."""
    have = {code: at for code, at in db.execute(
        "SELECT code, unlocked_at FROM achievements WHERE user_id = %s", (user_id,))}
    return [{"code": a.code, "icon": a.icon, "name": a.name, "description": a.description,
             "xp": a.xp, "unlocked_at": have.get(a.code)} for a in ACHIEVEMENTS]
