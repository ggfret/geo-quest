import os

from database import connect, is_local

# Tests run on their own database on this computer, emptied before every test.
# Never the site's real database: DATABASE_URL is replaced before the app is imported.
TEST_URL = os.environ.get("GEO_TEST_DATABASE_URL", "postgresql:///geoquest_test")
assert is_local(TEST_URL), "Tests empty their database, so they only run on a local Postgres."
os.environ["DATABASE_URL"] = TEST_URL

import pytest  # noqa: E402

import app as geo_app  # noqa: E402  (creates the test database and its tables)

TABLES = "users, attempts, mastery, login_failures, runs, achievements, feedback"


@pytest.fixture(scope="session", autouse=True)
def fresh_tables():
    """Rebuild the tables once per test run, so changes to schema.sql are picked up."""
    with connect(TEST_URL) as db:
        db.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    geo_app.init_db()


@pytest.fixture
def anon():
    """A browser with no account, on an empty database."""
    with connect(TEST_URL) as db:
        db.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")
    return geo_app.app.test_client()


@pytest.fixture
def client(anon):
    """A logged-in player (user id 1)."""
    anon.post("/signup", data={"username": "tester", "password": "correct horse"})
    return anon


@pytest.fixture
def db(anon):
    """A direct connection to the test database, for setting things up and checking results."""
    conn = connect(TEST_URL)
    conn.autocommit = True
    yield conn
    conn.close()
