"""The map games: Pin it, Hot & Cold, Neighbours, Road trip, Name them all, Higher or Lower."""

import json

import geo
from games import COUNTRY_BY_ID

COUNTRY_IDS = list(COUNTRY_BY_ID)


def force_state(db, run_id, **changes):
    """Set up a round with a known mystery country / pair, so the test doesn't depend on chance."""
    state = json.loads(db.execute("SELECT state FROM runs WHERE id = %s", (run_id,)).fetchone()[0])
    state.update(changes)
    db.execute("UPDATE runs SET state = %s WHERE id = %s", (json.dumps(state), run_id))
    db.commit()


# ---------- Pin it ----------

def pin(client, target, lon, lat, pick=None):
    """Click a point; like the browser, select the country there (or `pick`, e.g. a tiny island next to the click)."""
    from challenges.common import country_at
    x, y = geo.world_xy(lon, lat)
    return client.post("/api/pin/answer", json={"item_id": target, "pick": pick or country_at(x, y), "x": x, "y": y}).get_json()


def test_pin_the_right_country(client):
    assert client.get("/api/pin/next").get_json()["name"]
    r = pin(client, "NOR", 10.75, 59.9)  # Oslo
    assert r["correct"] and r["distance_km"] == 0 and r["xp"] == 10 and r["line"] is None
    assert r["target"]["path"] and "Sweden" in r["fact"]


def test_pin_the_wrong_country(client):
    r = pin(client, "NOR", 11.97, 57.71)  # Gothenburg
    assert not r["correct"] and r["picked"] == "Sweden" and r["picked_place"]["id"] == "SWE"
    assert r["neighbour"] and r["distance_km"] == 0 and r["xp"] == 4 and r["line"] is None

    r = pin(client, "NOR", 9.5, 56.2)  # Denmark: across the sea, about 100 km from Norway
    assert not r["correct"] and not r["neighbour"] and 30 < r["distance_km"] < 300 and r["xp"] == 4
    assert len(r["line"]) == 4

    far = pin(client, "NOR", -58.4, -34.6)  # Buenos Aires
    assert not far["correct"] and far["distance_km"] > 10000 and far["xp"] == 0


def test_pin_tiny_countries_have_some_leeway(client):
    assert pin(client, "VAT", 12.50, 41.90)["correct"]               # Rome (Italy), right next to Vatican City
    assert not pin(client, "LUX", 6.2, 50.6)["correct"]               # Belgium, near Luxembourg: big enough to click
    assert pin(client, "MLT", 14.6, 35.6, pick="MLT")["correct"]      # in the sea next to Malta, which lights up
    assert not pin(client, "MLT", 14.0, 37.5)["correct"]              # Sicily, too far from Malta


def test_pin_gap_between_big_countries_is_quick():
    import time
    from challenges.pin import gap
    started = time.perf_counter()
    km, line = gap("USA", "RUS")  # Alaska to Chukotka, across the Bering Strait
    assert km < 300 and line and time.perf_counter() - started < 0.5


def test_pin_rejects_bad_input(client):
    assert client.post("/api/pin/answer", json={"item_id": "NOR"}).status_code == 400
    assert client.post("/api/pin/answer", json={"item_id": "NOR", "pick": "XXX"}).status_code == 400
    assert client.post("/api/pin/answer", json={"item_id": "XXX", "pick": "NOR"}).status_code == 400
    assert client.post("/api/pin/answer", json={"item_id": "NOR", "pick": "NOR", "x": "a", "y": 1}).status_code == 400


# ---------- Hot & Cold ----------

def test_hotcold_round(client, db):
    run = client.post("/api/hotcold/start", json={}).get_json()["run_id"]
    force_state(db, run, target="FRA")
    guess = lambda text: client.post("/api/hotcold/guess", json={"run_id": run, "guess": text}).get_json()

    r = guess("Germany")
    assert r["status"] == "guess"
    g = r["guesses"][0]
    assert g["name"] == "Germany" and g["neighbour"] and 400 < g["km"] < 1000 and g["arrow"] in "←↙↖"

    assert guess("germany")["status"] == "repeat"
    assert guess("Wakanda")["status"] == "unknown"
    assert guess("Japan")["guesses"][1]["km"] > 9000

    solved = guess("France")
    assert solved["status"] == "solved" and solved["answer"] == "France" and solved["guesses_used"] == 3
    assert solved["xp"] == 20  # 35 - 5 x 3 guesses
    assert tuple(db.execute("SELECT solved, score FROM runs WHERE id = %s", (run,)).fetchone()) == (1, 3)
    assert client.post("/api/hotcold/guess", json={"run_id": run, "guess": "Spain"}).status_code == 409


def test_hotcold_picks_up_where_you_left_off_and_give_up(client, db):
    run = client.post("/api/hotcold/start", json={}).get_json()["run_id"]
    force_state(db, run, target="PER")
    client.post("/api/hotcold/guess", json={"run_id": run, "guess": "Chile"})
    again = client.post("/api/hotcold/start", json={}).get_json()
    assert again["run_id"] == run and again["guesses"][0]["name"] == "Chile"

    r = client.post("/api/hotcold/give-up", json={"run_id": run}).get_json()
    assert r["status"] == "gave_up" and r["answer"] == "Peru" and r["xp"] == 0
    assert client.post("/api/hotcold/start", json={}).get_json()["run_id"] != run


# ---------- Neighbours ----------

def test_neighbours_win(client, db):
    start = client.post("/api/neighbours/start", json={}).get_json()
    run = start["run_id"]
    force_state(db, run, target="ESP")
    guess = lambda text: client.post("/api/neighbours/guess", json={"run_id": run, "guess": text}).get_json()

    assert guess("Spain")["status"] == "self"
    r = guess("Portugal")
    assert r["status"] == "found" and r["total"] == 5 and r["found"][0]["id"] == "PRT"
    assert guess("portugal")["status"] == "repeat"
    assert guess("Wakanda")["status"] == "unknown"
    for name in ["France", "Andorra", "Morocco"]:
        assert guess(name)["status"] == "found"
    last = guess("Gibraltar")
    assert last["finished"] and last["won"] and last["missed"] == []
    assert last["xp"] == 3 * 5 + 5


def test_neighbours_three_strikes(client, db):
    run = client.post("/api/neighbours/start", json={}).get_json()["run_id"]
    force_state(db, run, target="DEU")
    guess = lambda text: client.post("/api/neighbours/guess", json={"run_id": run, "guess": text}).get_json()

    assert guess("France")["status"] == "found"
    assert guess("Italy")["status"] == "wrong"
    assert guess("Spain")["strikes_left"] == 1
    end = guess("Hungary")
    assert end["finished"] and not end["won"] and end["xp"] == 3
    assert {m["id"] for m in end["missed"]} == {"AUT", "BEL", "CZE", "DNK", "LUX", "NLD", "POL", "CHE"}
    mixup = db.execute("SELECT guessed_id FROM attempts WHERE game = 'neighbours'").fetchone()[0]
    assert mixup == "ITA"  # the first wrong neighbour is saved as a mix-up


# ---------- Name them all ----------

def test_name_them_all(client, db):
    r = client.post("/api/nameall/start", json={"variant": "south-america"}).get_json()
    run = r["run_id"]
    assert r["total"] == 12 and r["seconds"] == 180
    brazil = next(t for t in r["targets"] if t["id"] == "BRA")
    assert "brazil" in brazil["names"]

    check = lambda text: client.post("/api/nameall/check", json={"run_id": run, "guess": text}).get_json()
    assert check("Brazl") == {"ok": True, "id": "BRA", "name": "Brazil", "typo": True}
    assert check("France")["message"] == "France is in Europe."
    assert "isn't counted" in check("Falkland Islands")["message"]
    assert check("Wakanda")["ok"] is False

    done = client.post("/api/nameall/finish", json={"run_id": run, "found": ["BRA", "ARG", "ARG", "FRA"]}).get_json()
    assert done["score"] == 2 and done["total"] == 12 and len(done["missed"]) == 10
    assert done["xp"] == 4 and done["new_best"]
    assert tuple(db.execute("SELECT COUNT(*), SUM(correct) FROM attempts WHERE game = 'nameall'").fetchone()) == (12, 2)
    assert db.execute("SELECT box FROM mastery WHERE game = 'nameall' AND item_id = 'BRA'").fetchone()[0] == 1

    again = client.post("/api/nameall/start", json={"variant": "south-america"}).get_json()["run_id"]
    worse = client.post("/api/nameall/finish", json={"run_id": again, "found": ["BRA"]}).get_json()
    assert not worse["new_best"] and worse["best_before"]["score"] == 2


def test_name_them_all_complete_bonus_and_variants(client):
    from challenges.nameall import TARGETS
    assert len(TARGETS["world"]) == 197 and len(TARGETS["africa"]) == 54 and len(TARGETS["europe"]) == 46
    run = client.post("/api/nameall/start", json={"variant": "oceania"}).get_json()["run_id"]
    done = client.post("/api/nameall/finish", json={"run_id": run, "found": TARGETS["oceania"]}).get_json()
    assert done["score"] == done["total"] == 14 and done["bonus"] == 14 and done["xp"] == 14 * 2 + 14
    assert client.post("/api/nameall/start", json={"variant": "mars"}).status_code == 400


# ---------- Higher or Lower ----------

def test_higher_or_lower(client, db):
    r = client.post("/api/higherlower/start", json={"variant": "population"}).get_json()
    run = r["run_id"]
    assert r["a"]["value"] and r["b"]["name"] and "value" not in r["b"]
    force_state(db, run, a="NOR", b="IND", kind="population")

    right = client.post("/api/higherlower/guess", json={"run_id": run, "choice": "higher"}).get_json()
    assert right["correct"] and right["xp"] == 3 and right["reveal"]["value"] == "1.42 billion"
    assert right["next"]["a"]["id"] == "IND" and right["next"]["streak"] == 1

    force_state(db, run, a="IND", b="NOR", kind="population")
    wrong = client.post("/api/higherlower/guess", json={"run_id": run, "choice": "higher"}).get_json()
    assert not wrong["correct"] and wrong["streak"] == 1 and wrong["new_best"]
    assert tuple(db.execute("SELECT score, finished_at IS NOT NULL FROM runs WHERE id = %s", (run,)).fetchone()) == (1, 1)
    assert db.execute("SELECT COUNT(*) FROM mastery WHERE game = 'higherlower'").fetchone()[0] == 0


def test_higher_or_lower_formats_and_notes():
    from challenges.higherlower import fmt, note
    assert fmt("population", 5_509_733) == "5.5 million"
    assert fmt("area", 0.44) == "0.44 km²" and fmt("area", 323802) == "323,802 km²"
    assert fmt("gdp", 91100.0) == "$91,100" and fmt("life", 82.9) == "82.9 years" and fmt("elevation", 8849) == "8,849 m"
    assert note("NPL", "elevation") == "Nepal's highest point is Mount Everest (8,849 m)."


def test_higher_or_lower_mixed_gets_harder():
    from challenges.higherlower import pick_b, value
    for _ in range(50):
        b = pick_b("population", "NOR", ["NOR"], streak=10)
        ratio = max(value(b, "population"), value("NOR", "population")) / min(value(b, "population"), value("NOR", "population"))
        assert ratio <= 1.8


def test_neighbours_keeps_every_guess_in_order(client, db):
    run = client.post("/api/neighbours/start", json={}).get_json()["run_id"]
    force_state(db, run, target="SVN")
    for name in ["Italy", "Serbia", "Austria"]:
        r = client.post("/api/neighbours/guess", json={"run_id": run, "guess": name}).get_json()
    assert r["log"] == [{"name": "Italy", "ok": True}, {"name": "Serbia", "ok": False}, {"name": "Austria", "ok": True}]
    assert client.post("/api/neighbours/give-up", json={"run_id": run}).get_json()["missed"][0]["id"] in {"HRV", "HUN"}


def test_regions_are_framed_across_the_date_line():
    from challenges.common import view_box
    from challenges.nameall import TARGETS
    oceania = view_box(TARGETS["oceania"])
    assert oceania[2] - oceania[0] < 300   # Samoa and Tonga sit next to Australia, not on the far left
    europe = view_box(TARGETS["europe"])
    assert europe[2] - europe[0] < 250     # Russia doesn't squash the rest of Europe


def test_pins_past_the_date_line(client):
    from challenges.common import country_at
    x, y = geo.world_xy(178.5, 66.0)  # the far-eastern tip of Russia
    assert country_at(x % 1000, y) == "RUS"
    r = client.post("/api/pin/answer", json={"item_id": "RUS", "pick": "RUS", "x": x % 1000, "y": y}).get_json()
    assert r["correct"] and r["distance_km"] == 0


# ---------- Road trip ----------

def test_road_trip_colours():
    from challenges.roadtrip import between, judge
    assert between("NOR", "KOR") == 2
    colour = lambda x: judge("NOR", "KOR", x)["colour"]
    assert colour("RUS") == colour("PRK") == "green"          # Norway → Russia → North Korea → South Korea
    assert colour("CHN") == colour("FIN") == "yellow"         # possible, but a detour
    assert judge("NOR", "KOR", "CHN")["extra"] == 1
    assert colour("JPN") == colour("USA") == colour("PRT") == "red"
    assert "island" in judge("NOR", "KOR", "JPN")["why"]
    assert "not connected" in judge("NOR", "KOR", "USA")["why"]
    assert "dead end" in judge("NOR", "KOR", "PRT")["why"]     # Portugal only borders Spain


def test_road_trip_several_shortest_routes():
    from challenges.roadtrip import count_shortest_routes, judge, on_shortest_route
    assert on_shortest_route("EGY", "KEN") == {"SDN", "ETH", "SSD"}  # via Sudan, then Ethiopia or South Sudan
    assert count_shortest_routes("EGY", "KEN") == 2
    assert judge("EGY", "KEN", "UGA")["colour"] == "yellow"


def test_road_trip_greens_must_fit_on_one_route():
    from challenges.roadtrip import judge
    # Pakistan → Guinea goes ... Libya, then Niger or Algeria, then Mali: one or the other, never both.
    guesses = []
    for x, colour in [("MLI", "green"), ("NER", "green"), ("DZA", "yellow"), ("LBY", "green")]:
        verdict = judge("PAK", "GIN", x, guesses)
        assert verdict["colour"] == colour, x
        guesses.append(verdict)
    assert "not the one through Niger" in guesses[2]["why"]
    # Named the other way round, Algeria is the green one.
    first = judge("PAK", "GIN", "DZA")
    assert judge("PAK", "GIN", "NER", [first])["colour"] == "yellow"
    # Iraq and Türkiye are alternatives too, but each fits with Egypt.
    egypt = judge("PAK", "GIN", "EGY")
    assert judge("PAK", "GIN", "IRQ", [egypt])["colour"] == judge("PAK", "GIN", "TUR", [egypt])["colour"] == "green"


def test_road_trip_green_means_the_shortest_route_through_it():
    from challenges.roadtrip import between, distances, judge, route_through
    for a, b in [("FRA", "IND"), ("ZAF", "EGY"), ("CHL", "MEX")]:
        for x in distances(a):
            if x in (a, b):
                continue
            j, length = judge(a, b, x), route_through(a, b, x)
            assert (j["colour"] == "green") == (length == between(a, b)), (a, b, x)
            assert (j["colour"] == "red") == (length is None), (a, b, x)


def test_road_trip_levels():
    from challenges.roadtrip import LEVELS, between, familiar, one_shortest_route, pairs
    for level, rules in LEVELS.items():
        low, high = rules["between"]
        assert len(pairs(level)) > 300, level
        for a, b in pairs(level)[::50]:
            assert low <= between(a, b) <= high
            if level != "hard":
                assert familiar(a) and familiar(b)
                assert len(one_shortest_route(a, b, [c for c in COUNTRY_IDS if familiar(c)])) == between(a, b)


def trip(client, db, level="easy", **state):
    run = client.post("/api/roadtrip/start", json={"level": level}).get_json()
    assert run["level"] == level and run["guesses"] == []
    force_state(db, run["run_id"], **{"start": "NOR", "end": "KOR", "max_guesses": 6, **state})
    db.execute("UPDATE runs SET total = 2 WHERE id = %s", (run["run_id"],))  # 2 countries between Norway and South Korea
    db.commit()
    return lambda text: client.post("/api/roadtrip/guess", json={"run_id": run["run_id"], "guess": text}).get_json()


def test_road_trip_round(client, db):
    guess = trip(client, db)
    assert guess("Japan")["verdict"]["colour"] == "red"
    assert guess("china")["verdict"]["colour"] == "yellow"
    assert guess("Norway")["status"] == "endpoint"
    assert guess("Atlantis")["status"] == "unknown"
    r = guess("Russia")
    assert r["verdict"]["colour"] == "green" and not r.get("finished")
    assert guess("russia")["status"] == "repeat"
    r = guess("North Korea")
    assert r["finished"] and r["won"] and not r["perfect"] and r["used"] == 4
    assert r["xp"] == 15 - 3 * 2  # two wasted guesses
    assert [c["name"] for c in r["your_route"]] == ["Russia", "North Korea"] and r["other_routes"] == 0
    assert client.post("/api/roadtrip/guess", json={"run_id": r["run_id"], "guess": "China"}).status_code == 409


def test_road_trip_perfect_and_resume(client, db):
    assert client.post("/api/roadtrip/start", json={}).get_json()["run_id"] is None  # nothing to pick up
    guess = trip(client, db, level="hard")
    guess("Russia")
    resumed = client.post("/api/roadtrip/start", json={}).get_json()
    assert [g["name"] for g in resumed["guesses"]] == ["Russia"]
    r = guess("North Korea")
    assert r["perfect"] and r["xp"] == 40
    assert "shortcut" in {a["code"] for a in r["unlocked"]}


def test_road_trip_out_of_guesses_and_give_up(client, db):
    guess = trip(client, db, max_guesses=2)
    guess("Russia")
    r = guess("Japan")
    assert r["finished"] and not r["won"] and r["xp"] == 2  # 2 XP for the one green country
    assert [c["name"] for c in r["shortest_route"]] == ["Russia", "North Korea"]
    assert set(r["on_shortest"]) == {"RUS", "PRK"}

    guess = trip(client, db)
    guess("China")
    run_id = db.execute("SELECT MAX(id) FROM runs").fetchone()[0]
    r = client.post("/api/roadtrip/give-up", json={"run_id": run_id}).get_json()
    assert r["finished"] and not r["won"] and r["xp"] == 0


def test_road_trip_rejects_bad_level(client):
    assert client.post("/api/roadtrip/start", json={"level": "extreme"}).status_code == 400
