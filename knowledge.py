"""The 'My Knowledge' page: what you know well, what you don't, and what you mix up.

Everything is computed with SQL from the `attempts`, `mastery` and `items` tables.
"""

MASTERED_BOX = 4       # box 4-5 counts as "known"
MIN_AREA_ANSWERS = 5   # a game + region needs this many answers before we judge it
MIN_ITEM_ANSWERS = 2   # an item needs this many answers before it can be "hardest"


def report(db, user_id):
    area_list = areas(db, user_id)
    judged = sorted((a for a in area_list if a["answered"] >= MIN_AREA_ANSWERS), key=lambda a: a["accuracy"])
    best = [a for a in reversed(judged) if a["accuracy"] >= 0.5][:3]
    worst = [a for a in judged if a["accuracy"] < 0.8 and a not in best][:3]
    return {
        "games": per_game(db, user_id),
        "areas": area_list,
        "best_areas": best,
        "worst_areas": worst,
        "hardest": items(db, user_id, hardest=True),
        "easiest": items(db, user_id, hardest=False),
        "mixups": mixups(db, user_id),
        "mastery": mastery_by_game(db, user_id),
        "total_answers": db.execute("SELECT COUNT(*) FROM attempts WHERE user_id = ?", (user_id,)).fetchone()[0],
    }


def per_game(db, user_id):
    """Per game: pool size, how many you've seen/know, answers, accuracy and XP."""
    rows = db.execute(
        """
        WITH pool AS (
            SELECT i.game,
                   COUNT(*) AS pool,
                   COUNT(m.item_id) AS seen,
                   SUM(m.box >= ?) AS known
            FROM items i
            LEFT JOIN mastery m ON m.user_id = ? AND m.game = i.game AND m.item_id = i.item_id
            GROUP BY i.game
        ),
        answers AS (
            SELECT game, COUNT(*) AS answered, AVG(correct) AS accuracy, SUM(xp) AS xp
            FROM attempts WHERE user_id = ?
            GROUP BY game
        )
        SELECT pool.game, pool.pool, pool.seen, COALESCE(pool.known, 0) AS known,
               COALESCE(answers.answered, 0) AS answered, answers.accuracy, COALESCE(answers.xp, 0) AS xp
        FROM pool LEFT JOIN answers USING (game)
        """,
        (MASTERED_BOX, user_id, user_id),
    ).fetchall()
    return {row["game"]: dict(row) for row in rows}


def areas(db, user_id):
    """Accuracy per game and region (continent, or writing system for languages)."""
    rows = db.execute(
        """
        SELECT a.game, i.region, COUNT(*) AS answered, AVG(a.correct) AS accuracy
        FROM attempts a
        JOIN items i ON i.game = a.game AND i.item_id = a.item_id
        WHERE a.user_id = ?
        GROUP BY a.game, i.region
        ORDER BY a.game, i.region
        """,
        (user_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def items(db, user_id, hardest, limit=8):
    """Your weakest (or strongest) countries/languages across all games."""
    order, only = ("ASC", "m.correct < m.seen") if hardest else ("DESC", "m.correct > 0")
    rows = db.execute(
        f"""
        SELECT m.game, i.name, m.seen, m.correct, m.box, 1.0 * m.correct / m.seen AS accuracy
        FROM mastery m
        JOIN items i ON i.game = m.game AND i.item_id = m.item_id
        WHERE m.user_id = ? AND m.seen >= ? AND {only}
        ORDER BY accuracy {order}, m.seen DESC
        LIMIT ?
        """,
        (user_id, MIN_ITEM_ANSWERS, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def mixups(db, user_id, limit=10):
    """Wrong answers where you named another real country or language, most frequent first."""
    rows = db.execute(
        """
        SELECT a.game,
               COALESCE(t.name, a.item_id) AS answer,
               COALESCE(g.name, a.guessed_id) AS guessed,
               COUNT(*) AS times
        FROM attempts a
        LEFT JOIN items t ON t.game = a.game AND t.item_id = a.item_id
        LEFT JOIN items g ON g.game = a.game AND g.item_id = a.guessed_id
        WHERE a.user_id = ? AND a.correct = 0 AND a.guessed_id IS NOT NULL AND a.guessed_id != a.item_id
        GROUP BY a.game, a.item_id, a.guessed_id
        ORDER BY times DESC, MAX(a.id) DESC
        LIMIT ?
        """,
        (user_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def mastery_by_game(db, user_id):
    """{game: {item id: [box, seen, correct]}} for colouring the maps."""
    result = {}
    for row in db.execute("SELECT game, item_id, box, seen, correct FROM mastery WHERE user_id = ?", (user_id,)):
        result.setdefault(row["game"], {})[row["item_id"]] = [row["box"], row["seen"], row["correct"]]
    return result

