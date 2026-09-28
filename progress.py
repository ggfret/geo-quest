"""XP, levels, day streaks, the daily goal, and choosing what to ask next (spaced repetition).

Dates are in UTC, like SQLite's 'now'.
"""

import random
from datetime import date, datetime, timedelta, timezone

TITLES = ["Tourist", "Backpacker", "Map Reader", "Explorer", "Navigator",
          "Cartographer", "Geographer", "Globetrotter", "World Master"]

MAX_BOX = 5
# How likely each item is to be picked, by mastery box. Unseen items sit in the middle.
BOX_WEIGHT = [8, 6, 4, 2, 1, 0.5]
UNSEEN_WEIGHT = 5
# Knowledge fades: days after the last answer until an item is due for review again, by box.
REVIEW_DAYS = [0, 1, 3, 7, 14, 30]
NOT_DUE_FACTOR = 0.25  # items that aren't due yet are picked four times less often
RECENT_TO_SKIP = 5     # don't repeat any of the last few items

BASE_XP = 10
STREAK_XP = 2       # per correct answer in a row, capped
MAX_STREAK_BONUS = 10
WEAK_ITEM_XP = 5    # bonus for getting a country right that you usually miss
DAILY_GOAL = 50     # XP per day

# Monday 00:00 UTC of the current week, in SQLite.
WEEK_START = "date('now', 'weekday 0', '-6 days')"
# True when a mastery row (aliased m) is due for review; box 0 is always due.
DUE_SQL = ("julianday('now') - julianday(m.last_seen) >= CASE m.box "
           + " ".join(f"WHEN {box} THEN {days}" for box, days in enumerate(REVIEW_DAYS)) + " END")


def xp_to_next(level):
    """XP needed to go from `level` to `level + 1`: 100, 150, 200, ..."""
    return 100 + (level - 1) * 50


def level_info(xp):
    level, into = 1, xp
    while into >= xp_to_next(level):
        into -= xp_to_next(level)
        level += 1
    return {
        "xp": xp,
        "level": level,
        "into": into,
        "need": xp_to_next(level),
        "title": TITLES[min((level - 1) // 2, len(TITLES) - 1)],
    }


def today_utc():
    return datetime.now(timezone.utc).date()


def summary(db, user_id):
    """Everything the header shows: level, XP per game, today's XP, this week's XP and the day streak."""
    per_game = {game: xp for game, xp in db.execute(
        "SELECT game, SUM(xp) FROM xp_events WHERE user_id = ? GROUP BY game", (user_id,))}
    today_xp, week_xp = db.execute(
        f"""SELECT COALESCE(SUM(CASE WHEN at >= date('now') THEN xp END), 0),
                   COALESCE(SUM(CASE WHEN at >= {WEEK_START} THEN xp END), 0)
            FROM xp_events WHERE user_id = ?""",
        (user_id,),
    ).fetchone()
    return {
        **level_info(sum(per_game.values())),
        "per_game": per_game,
        "today_xp": today_xp,
        "daily_goal": DAILY_GOAL,
        "week_xp": week_xp,
        **day_streak(db, user_id),
    }


def day_streak(db, user_id):
    """Days in a row with at least one answer, counting back from today (or yesterday, if today's still to come)."""
    days = [date.fromisoformat(d) for (d,) in db.execute(
        "SELECT DISTINCT date(created_at) FROM attempts WHERE user_id = ? ORDER BY 1 DESC LIMIT 400", (user_id,))]
    today = today_utc()
    if not days or days[0] < today - timedelta(days=1):
        return {"streak": 0, "played_today": False}
    streak, expected = 0, days[0]
    for d in days:
        if d != expected:
            break
        streak += 1
        expected -= timedelta(days=1)
    return {"streak": streak, "played_today": days[0] == today}


def current_streak(db, user_id, game):
    """Correct answers in a row, most recent first."""
    rows = db.execute(
        "SELECT correct FROM attempts WHERE user_id = ? AND game = ? ORDER BY id DESC LIMIT 50",
        (user_id, game),
    ).fetchall()
    streak = 0
    for (correct,) in rows:
        if not correct:
            break
        streak += 1
    return streak


def pick_next(db, user_id, game, item_ids):
    """Pick the next item to ask: weak, new and due-for-review items often; recently learned ones rarely."""
    known = {
        item_id: (box, age)
        for item_id, box, age in db.execute(
            "SELECT item_id, box, julianday('now') - julianday(last_seen) FROM mastery WHERE user_id = ? AND game = ?",
            (user_id, game),
        )
    }
    recent = {
        item_id
        for (item_id,) in db.execute(
            "SELECT item_id FROM attempts WHERE user_id = ? AND game = ? ORDER BY id DESC LIMIT ?",
            (user_id, game, RECENT_TO_SKIP),
        )
    }
    candidates = [i for i in item_ids if i not in recent] or list(item_ids)

    def weight(item_id):
        if item_id not in known:
            return UNSEEN_WEIGHT
        box, age = known[item_id]
        due = age is None or age >= REVIEW_DAYS[box]
        return BOX_WEIGHT[box] * (1 if due else NOT_DUE_FACTOR)

    return random.choices(candidates, weights=[weight(i) for i in candidates])[0]


def record(db, user_id, game, item_id, guess, result, xp=None, mastery=True, commit=True):
    """Save one answer, update mastery, and return the XP earned.

    xp: a fixed amount instead of the usual formula (the map games score their own way).
    mastery: False for answers that aren't about knowing one item (Higher or Lower).
    """
    row = db.execute(
        "SELECT seen, box FROM mastery WHERE user_id = ? AND game = ? AND item_id = ?",
        (user_id, game, item_id),
    ).fetchone() if mastery else None
    seen, box = (row[0], row[1]) if row else (0, 0)

    if xp is None:
        xp = 0
        if result.correct:
            streak = current_streak(db, user_id, game)
            xp = BASE_XP + min(streak * STREAK_XP, MAX_STREAK_BONUS)
            if seen and box <= 1:
                xp += WEAK_ITEM_XP
    new_box = min(box + 1, MAX_BOX) if result.correct else max(box - 2, 0)

    db.execute(
        """INSERT INTO attempts (user_id, game, item_id, guess, correct, typo, guessed_id, xp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, game, item_id, guess, int(result.correct), int(result.typo), result.guessed_id, xp),
    )
    if mastery:
        db.execute(
            """INSERT INTO mastery (user_id, game, item_id, seen, correct, box, last_seen)
               VALUES (?, ?, ?, 1, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT (user_id, game, item_id) DO UPDATE SET
                   seen = seen + 1,
                   correct = correct + excluded.correct,
                   box = excluded.box,
                   last_seen = excluded.last_seen""",
            (user_id, game, item_id, int(result.correct), new_box),
        )
    if commit:
        db.commit()
    return xp


def due_counts(db, user_id):
    """{game: how many learned items are due for review} (box 0 'struggling' items aren't counted)."""
    return {game: n for game, n in db.execute(
        f"SELECT m.game, COUNT(*) FROM mastery m WHERE m.user_id = ? AND m.box >= 1 AND {DUE_SQL} GROUP BY m.game",
        (user_id,),
    )}
