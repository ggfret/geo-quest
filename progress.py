"""XP, levels, and choosing what to ask next (spaced repetition)."""

import random

TITLES = ["Tourist", "Backpacker", "Map Reader", "Explorer", "Navigator",
          "Cartographer", "Geographer", "Globetrotter", "World Master"]

MAX_BOX = 5
# How likely each item is to be picked, by mastery box. Unseen items sit in the middle.
BOX_WEIGHT = [8, 6, 4, 2, 1, 0.5]
UNSEEN_WEIGHT = 5
RECENT_TO_SKIP = 5  # don't repeat any of the last few items

BASE_XP = 10
STREAK_XP = 2       # per correct answer in a row, capped
MAX_STREAK_BONUS = 10
WEAK_ITEM_XP = 5    # bonus for getting a country right that you usually miss


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


def summary(db, user_id):
    """Total XP/level plus XP per game."""
    rows = db.execute(
        "SELECT game, SUM(xp) AS xp FROM attempts WHERE user_id = ? GROUP BY game", (user_id,)
    ).fetchall()
    per_game = {row["game"]: row["xp"] for row in rows}
    return {**level_info(sum(per_game.values())), "per_game": per_game}


def current_streak(db, user_id, game):
    """Correct answers in a row, most recent first."""
    rows = db.execute(
        "SELECT correct FROM attempts WHERE user_id = ? AND game = ? ORDER BY id DESC LIMIT 50",
        (user_id, game),
    ).fetchall()
    streak = 0
    for row in rows:
        if not row["correct"]:
            break
        streak += 1
    return streak


def pick_next(db, user_id, game, item_ids):
    """Pick the next item to ask: weak and new items often, mastered ones rarely."""
    boxes = {
        row["item_id"]: row["box"]
        for row in db.execute(
            "SELECT item_id, box FROM mastery WHERE user_id = ? AND game = ?", (user_id, game)
        )
    }
    recent = {
        row["item_id"]
        for row in db.execute(
            "SELECT item_id FROM attempts WHERE user_id = ? AND game = ? ORDER BY id DESC LIMIT ?",
            (user_id, game, RECENT_TO_SKIP),
        )
    }
    candidates = [i for i in item_ids if i not in recent] or list(item_ids)
    weights = [BOX_WEIGHT[boxes[i]] if i in boxes else UNSEEN_WEIGHT for i in candidates]
    return random.choices(candidates, weights=weights)[0]


def record(db, user_id, game, item_id, guess, result):
    """Save one answer, update mastery, and return the XP earned."""
    row = db.execute(
        "SELECT seen, box FROM mastery WHERE user_id = ? AND game = ? AND item_id = ?",
        (user_id, game, item_id),
    ).fetchone()
    seen, box = (row["seen"], row["box"]) if row else (0, 0)

    xp = 0
    if result.correct:
        streak = current_streak(db, user_id, game)
        xp = BASE_XP + min(streak * STREAK_XP, MAX_STREAK_BONUS)
        if seen and box <= 1:
            xp += WEAK_ITEM_XP
        new_box = min(box + 1, MAX_BOX)
    else:
        new_box = max(box - 2, 0)

    db.execute(
        """INSERT INTO attempts (user_id, game, item_id, guess, correct, typo, guessed_id, xp)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, game, item_id, guess, int(result.correct), int(result.typo), result.guessed_id, xp),
    )
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
    db.commit()
    return xp
