import sqlite3

import pytest

import app as geo_app


@pytest.fixture
def anon(tmp_path, monkeypatch):
    """A browser with no account, on a fresh database."""
    monkeypatch.setitem(geo_app.app.config, "DATABASE", tmp_path / "test.db")
    geo_app.init_db()
    return geo_app.app.test_client()


@pytest.fixture
def client(anon):
    """A logged-in player (user id 1)."""
    anon.post("/signup", data={"username": "tester", "password": "correct horse"})
    return anon


@pytest.fixture
def db(anon):
    """A direct connection to the test database, for setting things up and checking results."""
    conn = sqlite3.connect(geo_app.app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
