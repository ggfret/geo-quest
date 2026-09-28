"""The SQLite connection and the logged-in user, shared by app.py and the game modules."""

import sqlite3

from flask import current_app, g, session


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def current_user_id():
    return session.get("user_id")
