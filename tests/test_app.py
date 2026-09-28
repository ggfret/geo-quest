import re
import sqlite3

import pytest

import app as geo_app


@pytest.mark.parametrize("path", [
    "/", "/flags", "/capitals", "/outlines", "/languages", "/ethnicities",
    "/pin", "/hotcold", "/neighbours", "/nameall", "/higherlower",
    "/knowledge", "/leaderboard", "/leaderboard?tab=all", "/leaderboard?tab=records",
])
def test_pages_load(client, path):
    response = client.get(path)
    assert response.status_code == 200
    # Two elements with the same id break the page scripts (they find the first one only).
    ids = re.findall(r'\sid="([^"]+)"', response.get_data(as_text=True))
    assert len(ids) == len(set(ids)), f"duplicate ids on {path}: {[i for i in ids if ids.count(i) > 1]}"


def test_flag_round(client):
    question = client.get("/api/flags/next").get_json()
    assert question["prompt"]["image"].startswith("https://flagcdn.com/")

    r = client.post("/api/flags/answer", json={"item_id": "TCD", "guess": "Romania"}).get_json()
    assert not r["correct"] and r["guessed"] == "Romania"
    assert r["tip_is_mixup"] and "Chad" in r["tip"]

    r = client.post("/api/flags/answer", json={"item_id": "NOR", "guess": "norwya"}).get_json()
    assert r["correct"] and r["typo"] and r["xp"] == 10 and r["fact"]

    r = client.post("/api/flags/answer", json={"item_id": "NOR", "guess": "", "skip": True}).get_json()
    assert not r["correct"] and r["skipped"]
    assert r["me"]["xp"] == 10 + 10  # the answer, plus the "First steps" badge


def test_rejects_unknown_items(client):
    assert client.post("/api/flags/answer", json={"item_id": "MAF", "guess": "x"}).status_code == 400
    assert client.post("/api/flags/answer", json={}).status_code == 400


def test_capital_round(client):
    question = client.get("/api/capitals/next").get_json()
    assert question["prompt"]["text"]

    r = client.post("/api/capitals/answer", json={"item_id": "AUS", "guess": "sydney"}).get_json()
    assert not r["correct"] and r["answer"] == "Canberra"
    assert r["tip_is_mixup"] and "Sydney is a big city" in r["tip"]

    r = client.post("/api/capitals/answer", json={"item_id": "SWE", "guess": "Oslo"}).get_json()
    assert not r["correct"] and r["guessed"] == "Oslo (capital of Norway)"

    r = client.post("/api/capitals/answer", json={"item_id": "BOL", "guess": "la paz"}).get_json()
    assert r["correct"] and "Sucre" in r["answer"]

    r = client.post("/api/capitals/answer", json={"item_id": "NLD", "guess": "Amsterdma"}).get_json()
    assert r["correct"] and r["typo"]

    # places without a capital are never asked
    assert client.post("/api/capitals/answer", json={"item_id": "HKG", "guess": "x"}).status_code == 400


def test_outline_round(client):
    question = client.get("/api/outlines/next").get_json()
    shape = question["prompt"]["shape"]
    assert shape["path"].startswith("M") and shape["w"] and shape["h"]

    r = client.post("/api/outlines/answer", json={"item_id": "SVN", "guess": "Slovakia"}).get_json()
    assert not r["correct"] and r["guessed"] == "Slovakia"
    assert r["locator"][0]["path"] and r["guessed_locator"][0]["path"]
    assert "Italy" in r["fact"]  # neighbours

    # too small to be recognisable -> never asked as an outline
    assert client.post("/api/outlines/answer", json={"item_id": "VAT", "guess": "x"}).status_code == 400


def test_every_answer_has_a_locator(client):
    for slug, item in [("flags", "GIB"), ("capitals", "TUV"), ("flags", "NOR")]:
        r = client.post(f"/api/{slug}/answer", json={"item_id": item, "guess": "x"}).get_json()
        assert r["locator"][0]["box"]


def test_language_round(client):
    question = client.get("/api/languages/next").get_json()
    prompt = question["prompt"]
    assert prompt["sentence"] and len(prompt["choices"]) == 4 and question["item_id"] in prompt["choices"]

    r = client.post("/api/languages/answer",
                    json={"item_id": "Ukrainian", "guess": "Russian", "context": 0}).get_json()
    assert not r["correct"] and r["guessed"] == "Russian" and r["answer"] == "Ukrainian"
    assert "ї" in r["tip"] and "How to spot Russian" in r["tip"]
    assert r["fact"] == "It means: “I would like to order a cup of tea.”"
    assert r["locator"] and r["guessed_locator"]  # Ukraine in green, Russia & co in red

    r = client.post("/api/languages/answer", json={"item_id": "Icelandic", "guess": "Icelandic"}).get_json()
    assert r["correct"] and r["xp"] >= 10


def test_language_choices_are_lookalikes():
    from games import LANGS, language_choices
    for lang in LANGS:
        choices = language_choices(lang)
        assert len(set(choices)) == 4 and lang in choices
    assert set(language_choices("Russian")) <= {l for l, v in LANGS.items() if v["group"] == "cyrillic"}


def test_ethnicity_round(client):
    question = client.get("/api/ethnicities/next").get_json()
    assert len(question["prompt"]["bars"]) >= 2

    from games import ethnicity_prompt
    norway = ethnicity_prompt("NOR")["bars"]
    assert norway[0]["label"] == "???" and norway[0]["hidden"]  # 'Norwegian' would give it away

    r = client.post("/api/ethnicities/answer", json={"item_id": "NOR", "guess": "Sweden"}).get_json()
    assert not r["correct"] and r["bars"][0]["label"] == "Norwegian"
    assert r["tip"].startswith("Your guess, Sweden")

    r = client.post("/api/ethnicities/answer", json={"item_id": "JPN", "guess": "japan"}).get_json()
    assert r["correct"]


def test_no_country_name_leaks_into_ethnicity_puzzles():
    from answers import normalize
    from games import COUNTRY_BY_ID, ETHNICITIES, ethnicity_prompt
    for cid in ETHNICITIES:
        shown = normalize(" ".join(b["label"] for b in ethnicity_prompt(cid)["bars"]))
        assert f" {normalize(COUNTRY_BY_ID[cid]['name'])} " not in f" {shown} ", cid


def test_knowledge_page_empty(client):
    page = client.get("/knowledge").get_data(as_text=True)
    assert "Nothing here yet" in page


def test_knowledge_report(client):
    answer = lambda game, item, guess: client.post(f"/api/{game}/answer", json={"item_id": item, "guess": guess})
    for _ in range(3):
        answer("flags", "TCD", "Romania")     # the same mix-up three times
    for item, guess in [("NOR", "Norway"), ("SWE", "Sweden"), ("DNK", "Denmark"), ("FIN", "Finland"), ("ISL", "Iceland")]:
        answer("flags", item, guess)
    answer("languages", "Ukrainian", "Russian")

    geo_app_db = sqlite3.connect(geo_app.app.config["DATABASE"])
    geo_app_db.row_factory = sqlite3.Row
    import knowledge
    report = knowledge.report(geo_app_db, 1)

    assert report["total_answers"] == 9
    flags = report["games"]["flags"]
    assert flags["answered"] == 8 and flags["seen"] == 6 and flags["pool"] == 232
    assert report["mixups"][0] == {"game": "flags", "answer": "Chad", "guessed": "Romania", "times": 3}
    assert report["hardest"][0]["name"] == "Chad"
    europe = next(a for a in report["areas"] if a["game"] == "flags" and a["region"] == "Europe")
    assert europe["answered"] == 5 and europe["accuracy"] == 1.0
    assert report["best_areas"][0]["region"] == "Europe"
    assert report["mastery"]["languages"]["Ukrainian"][0] == 0

    page = client.get("/knowledge").get_data(as_text=True)
    assert "Most common mix-ups" in page and "Romania" in page
    m = client.get("/api/map").get_json()
    assert m["width"] == 1000 and "NOR" in m["paths"]


# ---------- Accounts ----------

def test_pages_need_login(anon):
    assert anon.get("/flags").status_code == 302
    assert anon.get("/flags").headers["Location"].startswith("/login")
    assert anon.get("/api/flags/next").status_code == 401
    assert anon.get("/login").status_code == 200 and anon.get("/signup").status_code == 200


def test_signup_login_logout(anon):
    r = anon.post("/signup?next=/capitals", data={"username": "ana", "password": "12345678"})
    assert r.status_code == 302 and r.headers["Location"] == "/capitals"
    assert "ana" in anon.get("/").get_data(as_text=True)

    anon.post("/logout")
    assert anon.get("/").status_code == 302

    bad = anon.post("/login", data={"username": "ana", "password": "wrong-password"})
    assert "Wrong username or password" in bad.get_data(as_text=True)
    ok = anon.post("/login", data={"username": "ANA", "password": "12345678"})  # usernames ignore case
    assert ok.status_code == 302 and anon.get("/").status_code == 200


def test_signup_rules(anon):
    too_short = anon.post("/signup", data={"username": "ab", "password": "12345678"})
    assert "3–20" in too_short.get_data(as_text=True)
    weak = anon.post("/signup", data={"username": "abc", "password": "short"})
    assert "at least 8" in weak.get_data(as_text=True)
    anon.post("/signup", data={"username": "abc", "password": "12345678"})
    anon.post("/logout")
    taken = anon.post("/signup", data={"username": "ABC", "password": "12345678"})
    assert "taken" in taken.get_data(as_text=True)


def test_players_have_separate_progress(anon):
    anon.post("/signup", data={"username": "ana", "password": "12345678"})
    anon.post("/api/flags/answer", json={"item_id": "NOR", "guess": "Norway"})
    anon.post("/logout")
    anon.post("/signup", data={"username": "ben", "password": "12345678"})
    assert anon.get("/api/me").get_json()["xp"] == 0

    board = anon.get("/leaderboard").get_data(as_text=True).split("<tbody>")[1]
    assert board.index("ana") < board.index("ben")  # ana has more XP, so she's first


def test_claiming_progress_from_before_accounts(tmp_path, monkeypatch):
    """A database from before accounts: user 1 'me' with answers and no password."""
    db_path = tmp_path / "old.db"
    old = sqlite3.connect(db_path)
    old.executescript("""
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        INSERT INTO users (id, name) VALUES (1, 'me');
    """)
    old.close()
    monkeypatch.setitem(geo_app.app.config, "DATABASE", db_path)
    geo_app.init_db()  # adds the password column
    with sqlite3.connect(db_path) as db:
        db.execute("INSERT INTO attempts (user_id, game, item_id, guess, correct, xp) VALUES (1, 'flags', 'NOR', 'Norway', 1, 10)")

    browser = geo_app.app.test_client()
    assert "Keep the progress already on this computer (1 answers)" in browser.get("/signup").get_data(as_text=True)
    browser.post("/signup", data={"username": "gabriel", "password": "12345678", "claim": "1"})
    assert browser.get("/api/me").get_json()["xp"] == 10  # badges are only checked after the next answer
    assert "Keep the progress" not in geo_app.app.test_client().get("/signup").get_data(as_text=True)


def test_invite_code(anon):
    geo_app.app.config["INVITE_CODE"] = "atlas"
    try:
        assert "Invite code" in anon.get("/signup").get_data(as_text=True)
        wrong = anon.post("/signup", data={"username": "eve", "password": "12345678", "invite": "nope"})
        assert "invite code" in wrong.get_data(as_text=True)
        ok = anon.post("/signup", data={"username": "ana", "password": "12345678", "invite": "atlas"})
        assert ok.status_code == 302
    finally:
        geo_app.app.config["INVITE_CODE"] = None


def test_too_many_wrong_passwords(anon):
    anon.post("/signup", data={"username": "ana", "password": "12345678"})
    anon.post("/logout")
    for _ in range(5):
        anon.post("/login", data={"username": "ana", "password": "guess-guess"})
    locked = anon.post("/login", data={"username": "ana", "password": "12345678"})
    assert "Too many wrong passwords" in locked.get_data(as_text=True)
