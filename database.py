"""The Postgres connection and the logged-in user, shared by app.py and the game modules.

Locally this is a Postgres server on your Mac (database `geoquest`); online it's the address in
DATABASE_URL (Neon). Queries use %s for values: db.execute("SELECT ... WHERE id = %s", (user_id,)).
Rows can be read by position (row[0]) or by column name (row["name"]).
"""

import psycopg
from flask import current_app, g, session
from psycopg import sql
from psycopg.adapt import Loader
from psycopg.conninfo import conninfo_to_dict

LOCAL_URL = "postgresql:///geoquest"  # the Postgres server on this computer, logging in as you


class Row:
    """One result row: row[0], row["name"], `a, b = row`, dict(row) and {{ row.name }} in templates all work."""

    __slots__ = ("_values", "_index")

    def __init__(self, values, index):
        self._values = values
        self._index = index

    def __getitem__(self, key):
        return self._values[self._index[key] if isinstance(key, str) else key]

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def keys(self):
        return list(self._index)

    def __repr__(self):
        return f"Row({dict(zip(self._index, self._values))})"


def row_factory(cursor):
    index = {column.name: i for i, column in enumerate(cursor.description or [])}
    return lambda values: Row(values, index)


class TimeAsText(Loader):
    """Dates and times come back as text, '2026-10-03 15:17:25' (UTC), as the pages expect."""

    def load(self, data):
        return bytes(data).decode()[:19]


def connect(url):
    # prepare_threshold=None: no server-side prepared statements, so Neon's connection pooler works too.
    conn = psycopg.connect(url, row_factory=row_factory, prepare_threshold=None)
    for type_name in ("timestamptz", "timestamp", "date"):
        conn.adapters.register_loader(type_name, TimeAsText)
    return conn


def is_local(url):
    """True for a Postgres on this computer (no host, or localhost), false for Neon."""
    host = conninfo_to_dict(url).get("host") or ""
    return host in ("", "localhost", "127.0.0.1", "::1") or host.startswith("/")


def create_database_if_missing(url):
    """For running locally: make the database (e.g. `geoquest`) if this Postgres doesn't have it yet."""
    name = conninfo_to_dict(url).get("dbname")
    with psycopg.connect(url, dbname="postgres", autocommit=True) as server:
        if not server.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
            server.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE_URL"])
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()  # anything not committed is rolled back


def current_user_id():
    return session.get("user_id")
