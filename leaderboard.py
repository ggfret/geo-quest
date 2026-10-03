"""Leaderboards: the weekly league, all-time totals, and records in the map games."""

import progress

MASTERED_BOX = 4
TOP = 5


def players(db):
    """Every player with their XP (all time and this week), level, knowledge, badges and day streak."""
    rows = db.execute(
        f"""
        SELECT u.id, u.name,
               COALESCE(SUM(e.xp), 0) AS xp,
               COALESCE(SUM(CASE WHEN e.at >= {progress.WEEK_START} THEN e.xp END), 0) AS week_xp,
               (SELECT COUNT(*) FROM mastery m WHERE m.user_id = u.id AND m.box >= ?) AS known,
               (SELECT COUNT(*) FROM achievements a WHERE a.user_id = u.id) AS badges
        FROM users u
        LEFT JOIN xp_events e ON e.user_id = u.id
        WHERE u.password_hash IS NOT NULL
        GROUP BY u.id
        """,
        (MASTERED_BOX,),
    ).fetchall()
    champion = last_week_champion(db)
    result = []
    for row in rows:
        player = dict(row)
        player["level"] = progress.level_info(player["xp"])["level"]
        player["streak"] = progress.day_streak(db, player["id"])["streak"]
        player["champion"] = player["id"] == champion
        result.append(player)
    return result


def weekly(db):
    return sorted(players(db), key=lambda p: (-p["week_xp"], -p["xp"]))


def all_time(db):
    return sorted(players(db), key=lambda p: (-p["xp"], -p["known"]))


def last_week_champion(db):
    """Who had the most XP last week (Monday to Sunday, UTC), if at least two people played."""
    rows = db.execute(
        f"""SELECT user_id, SUM(xp) AS xp FROM xp_events
            WHERE at >= date({progress.WEEK_START}, '-7 days') AND at < {progress.WEEK_START}
            GROUP BY user_id ORDER BY xp DESC""",
    ).fetchall()
    return rows[0][0] if len(rows) >= 2 and rows[0][1] > rows[1][1] else None


def best_runs(db, game, user_id=None):
    """Each player's best finished run per variant: highest score, then fastest."""
    rows = db.execute(
        """
        SELECT variant, name, user_id, score, total, seconds FROM (
            SELECT r.variant, u.name, r.user_id, r.score, r.total, r.seconds,
                   ROW_NUMBER() OVER (PARTITION BY r.variant, r.user_id
                                      ORDER BY r.score DESC, r.seconds ASC, r.id ASC) AS rank
            FROM runs r JOIN users u ON u.id = r.user_id
            WHERE r.game = ? AND r.finished_at IS NOT NULL AND u.password_hash IS NOT NULL
        )
        WHERE rank = 1 AND (? IS NULL OR user_id = ?)
        ORDER BY variant, score DESC, seconds ASC
        """,
        (game, user_id, user_id),
    ).fetchall()
    result = {}
    for row in rows:
        result.setdefault(row["variant"], []).append(dict(row))
    return result


def hotcold_averages(db, user_id=None, last=10, minimum=3):
    """Average guesses over each player's last 10 solved Hot & Cold rounds (fewer is better)."""
    rows = db.execute(
        """
        SELECT name, user_id, AVG(score) AS average, COUNT(*) AS rounds FROM (
            SELECT u.name, r.user_id, r.score,
                   ROW_NUMBER() OVER (PARTITION BY r.user_id ORDER BY r.id DESC) AS n
            FROM runs r JOIN users u ON u.id = r.user_id
            WHERE r.game = 'hotcold' AND r.solved = 1 AND u.password_hash IS NOT NULL
        )
        WHERE n <= ? AND (? IS NULL OR user_id = ?)
        GROUP BY user_id HAVING COUNT(*) >= ?
        ORDER BY average ASC
        """,
        (last, user_id, user_id, minimum),
    ).fetchall()
    return [dict(r) for r in rows]


def pin_accuracy(db, user_id=None, last=20, minimum=10):
    """Share of each player's last 20 pins that hit the country."""
    rows = db.execute(
        """
        SELECT name, user_id, AVG(correct) AS accuracy, COUNT(*) AS pins FROM (
            SELECT u.name, a.user_id, a.correct,
                   ROW_NUMBER() OVER (PARTITION BY a.user_id ORDER BY a.id DESC) AS n
            FROM attempts a JOIN users u ON u.id = a.user_id
            WHERE a.game = 'pin' AND u.password_hash IS NOT NULL
        )
        WHERE n <= ? AND (? IS NULL OR user_id = ?)
        GROUP BY user_id HAVING COUNT(*) >= ?
        ORDER BY accuracy DESC, pins DESC
        """,
        (last, user_id, user_id, minimum),
    ).fetchall()
    return [dict(r) for r in rows]


def neighbour_rounds(db, user_id=None):
    """Rounds where every neighbour was named, per player."""
    rows = db.execute(
        """
        SELECT u.name, r.user_id, SUM(r.solved) AS perfect, COUNT(*) AS rounds
        FROM runs r JOIN users u ON u.id = r.user_id
        WHERE r.game = 'neighbours' AND r.finished_at IS NOT NULL AND u.password_hash IS NOT NULL
          AND (? IS NULL OR r.user_id = ?)
        GROUP BY r.user_id
        HAVING SUM(r.solved) > 0
        ORDER BY perfect DESC, rounds ASC
        """,
        (user_id, user_id),
    ).fetchall()
    return [dict(r) for r in rows]


def perfect_trips(db, user_id=None):
    """Road trips finished on a shortest route without a wasted guess, per player (and how many on Hard)."""
    rows = db.execute(
        """
        SELECT u.name, r.user_id,
               SUM(r.solved = 1 AND r.score = r.total) AS perfect,
               SUM(r.solved = 1 AND r.score = r.total AND r.variant = 'hard') AS hard
        FROM runs r JOIN users u ON u.id = r.user_id
        WHERE r.game = 'roadtrip' AND r.finished_at IS NOT NULL AND u.password_hash IS NOT NULL
          AND (? IS NULL OR r.user_id = ?)
        GROUP BY r.user_id
        HAVING perfect > 0
        ORDER BY hard DESC, perfect DESC
        """,
        (user_id, user_id),
    ).fetchall()
    return [dict(r) for r in rows]


def records(db):
    """The Records tab: the top players in each map game."""
    return {
        "nameall": {variant: rows[:TOP] for variant, rows in best_runs(db, "nameall").items()},
        "higherlower": {variant: rows[:TOP] for variant, rows in best_runs(db, "higherlower").items()},
        "hotcold": hotcold_averages(db)[:TOP],
        "pin": pin_accuracy(db)[:TOP],
        "neighbours": neighbour_rounds(db)[:TOP],
        "roadtrip": perfect_trips(db)[:TOP],
    }


def personal_bests(db, user_id):
    """One player's records, for the game pages and the Knowledge page."""
    hotcold = hotcold_averages(db, user_id, minimum=1)
    pin = pin_accuracy(db, user_id, minimum=1)
    neighbours = neighbour_rounds(db, user_id)
    trips = perfect_trips(db, user_id)
    return {
        "nameall": {v: rows[0] for v, rows in best_runs(db, "nameall", user_id).items()},
        "higherlower": {v: rows[0] for v, rows in best_runs(db, "higherlower", user_id).items()},
        "hotcold": hotcold[0] if hotcold else None,
        "pin": pin[0] if pin else None,
        "neighbours": neighbours[0] if neighbours else None,
        "roadtrip": trips[0] if trips else None,
    }
