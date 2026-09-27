import sqlite3

import pytest

import app as geo_app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(geo_app, "DATABASE", tmp_path / "test.db")
    geo_app.init_db()
    return geo_app.app.test_client()


def test_pages_load(client):
    assert client.get("/").status_code == 200
    assert client.get("/flags").status_code == 200
    assert client.get("/capitals").status_code == 200
    assert client.get("/outlines").status_code == 200
    assert client.get("/languages").status_code == 200
    assert client.get("/ethnicities").status_code == 200


def test_flag_round(client):
    question = client.get("/api/flags/next").get_json()
    assert question["prompt"]["image"].startswith("https://flagcdn.com/")

    r = client.post("/api/flags/answer", json={"item_id": "TCD", "guess": "Romania"}).get_json()
    assert not r["correct"] and r["guessed"] == "Romania"
    assert r["tip_is_mixup"] and "Chad" in r["tip"]

    r = client.post("/api/flags/answer", json={"item_id": "NOR", "guess": "norwya"}).get_json()
    assert r["correct"] and r["typo"] and r["xp"] == 10 and r["fact"]

    r = client.post("/api/flags/answer", json={"item_id": "NOR", "guess": "", "skip": True}).get_json()
    assert not r["correct"] and r["skipped"] and r["me"]["xp"] == 10


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

    geo_app_db = sqlite3.connect(geo_app.DATABASE)
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
