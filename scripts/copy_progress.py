"""Copy everyone's accounts and progress from one database to another, empty one.

    python scripts/copy_progress.py FROM TO

FROM is the old SQLite file (geo.db) or a Postgres address; TO is a Postgres address. For example:

    python scripts/copy_progress.py geo.db postgresql:///geoquest                 # old file -> this computer
    python scripts/copy_progress.py postgresql:///geoquest "postgresql://...neon..."  # this computer -> Neon

It's for moving over once, so TO must have no accounts yet. FROM isn't changed.
"""

import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from database import connect  # noqa: E402

# Parents before children, so every user_id already exists when it's referred to.
TABLES = {
    "users": ["id", "name", "password_hash", "created_at"],
    "attempts": ["id", "user_id", "game", "item_id", "guess", "correct", "typo", "guessed_id", "xp", "created_at"],
    "mastery": ["user_id", "game", "item_id", "seen", "correct", "box", "last_seen"],
    "runs": ["id", "user_id", "game", "variant", "state", "score", "total", "solved", "seconds", "bonus_xp",
             "started_at", "finished_at"],
    "achievements": ["user_id", "code", "xp", "unlocked_at"],
    "feedback": ["id", "user_id", "kind", "message", "page", "context", "done", "created_at"],
}


def open_source(source):
    if source.startswith("postgres"):
        return connect(source)  # times come back as UTC text, like SQLite's
    if not Path(source).exists():
        sys.exit(f"There's no {source} to copy from.")
    return sqlite3.connect(source)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    source, target = sys.argv[1], sys.argv[2]

    os.environ["DATABASE_URL"] = target
    import app  # noqa: F401  (creates the tables, and locally the database, if they aren't there yet)

    old = open_source(source)
    with connect(target) as db:  # one transaction: everything is copied, or nothing
        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
            sys.exit("That database already has accounts, so nothing was copied.")
        db.execute("SET timezone TO 'UTC'")  # the times being copied are UTC
        for table, columns in TABLES.items():
            rows = [tuple(row) for row in old.execute(f"SELECT {', '.join(columns)} FROM {table}").fetchall()]
            placeholders = ", ".join(["%s"] * len(columns))
            with db.cursor() as cur:
                cur.executemany(f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})", rows)
            if "id" in columns:  # new rows carry on numbering after the copied ones
                db.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                           f"(SELECT COALESCE(MAX(id), 0) + 1 FROM {table}), false)")
            print(f"{table}: {len(rows)} rows")
    old.close()
    print("Done.")


if __name__ == "__main__":
    main()
