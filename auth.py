"""User accounts: sign up, log in, and taking over progress from before accounts existed."""

import re

from werkzeug.security import check_password_hash, generate_password_hash

USERNAME = re.compile(r"^[A-Za-z0-9_]{3,20}$")
MIN_PASSWORD = 8
LEGACY_USER_ID = 1  # progress saved before accounts existed belongs to this user, who has no password


class AuthError(ValueError):
    """A problem to show on the form, e.g. 'That username is taken.'"""


def migrate(db):
    """Add the password column to databases created before accounts existed."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(users)")}
    if "password_hash" not in columns:
        db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")


def unclaimed_answers(db):
    """How many answers were saved before accounts existed and haven't been claimed yet."""
    row = db.execute(
        """SELECT COUNT(a.id) FROM users u JOIN attempts a ON a.user_id = u.id
           WHERE u.id = ? AND u.password_hash IS NULL""",
        (LEGACY_USER_ID,),
    ).fetchone()
    return row[0]


def sign_up(db, username, password, claim_legacy=False):
    """Create an account and return its id. With claim_legacy, take over the pre-account progress."""
    username = username.strip()
    if not USERNAME.match(username):
        raise AuthError("Usernames are 3–20 letters, numbers or underscores.")
    if len(password) < MIN_PASSWORD:
        raise AuthError(f"Passwords need at least {MIN_PASSWORD} characters.")
    taken = db.execute(
        "SELECT 1 FROM users WHERE lower(name) = lower(?) AND password_hash IS NOT NULL", (username,)
    ).fetchone()
    if taken:
        raise AuthError("That username is taken.")

    password_hash = generate_password_hash(password)
    if claim_legacy and unclaimed_answers(db):
        db.execute(
            "UPDATE users SET name = ?, password_hash = ? WHERE id = ?",
            (username, password_hash, LEGACY_USER_ID),
        )
        user_id = LEGACY_USER_ID
    else:
        user_id = db.execute(
            "INSERT INTO users (name, password_hash) VALUES (?, ?)", (username, password_hash)
        ).lastrowid
    db.commit()
    return user_id


def log_in(db, username, password):
    """Return the user's id if the password is right."""
    row = db.execute(
        "SELECT id, password_hash FROM users WHERE lower(name) = lower(?) AND password_hash IS NOT NULL",
        (username.strip(),),
    ).fetchone()
    if row is None or not check_password_hash(row["password_hash"], password):
        raise AuthError("Wrong username or password.")
    return row["id"]


def leaderboard(db, limit=50):
    rows = db.execute(
        """
        SELECT u.name,
               COALESCE(SUM(a.xp), 0) AS xp,
               COALESCE(SUM(CASE WHEN a.created_at >= datetime('now', '-7 days') THEN a.xp END), 0) AS week_xp,
               COUNT(a.id) AS answers,
               AVG(a.correct) AS accuracy
        FROM users u
        LEFT JOIN attempts a ON a.user_id = u.id
        WHERE u.password_hash IS NOT NULL
        GROUP BY u.id
        ORDER BY xp DESC, answers DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
