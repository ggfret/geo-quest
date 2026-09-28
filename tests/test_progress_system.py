"""Day streaks, the daily goal, fading knowledge, achievements and the leaderboards."""

from collections import Counter

import achievements
import knowledge
import leaderboard
import progress


def answer(db, user, day_offset, game="flags", item="NOR", correct=1, xp=10):
    """An answer given `day_offset` days ago (0 = today)."""
    db.execute(
        "INSERT INTO attempts (user_id, game, item_id, guess, correct, xp, created_at) "
        "VALUES (?, ?, ?, '', ?, ?, datetime('now', ?))",
        (user, game, item, correct, xp, f"-{day_offset} days"),
    )
    db.commit()


def add_player(db, name):
    return db.execute("INSERT INTO users (name, password_hash) VALUES (?, 'x')", (name,)).lastrowid


# ---------- Day streak and daily goal ----------

def test_day_streak(client, db):
    assert progress.day_streak(db, 1) == {"streak": 0, "played_today": False}
    for day in [1, 2, 3, 5]:  # yesterday, the two days before, and a gap
        answer(db, 1, day)
    assert progress.day_streak(db, 1) == {"streak": 3, "played_today": False}  # still alive until tonight
    answer(db, 1, 0)
    assert progress.day_streak(db, 1) == {"streak": 4, "played_today": True}


def test_streak_breaks_after_a_missed_day(client, db):
    answer(db, 1, 2)
    assert progress.day_streak(db, 1)["streak"] == 0


def test_daily_and_weekly_xp(client, db):
    answer(db, 1, 0, xp=30)
    answer(db, 1, 0, xp=25)
    answer(db, 1, 30, xp=100)  # long ago: counts for the level, not today or this week
    me = progress.summary(db, 1)
    assert me["today_xp"] == 55 and me["daily_goal"] == 50 and me["week_xp"] == 55 and me["xp"] == 155
    assert client.get("/").status_code == 200


# ---------- Knowledge fades ----------

def test_due_for_review(client, db):
    db.executemany(
        "INSERT INTO mastery (user_id, game, item_id, seen, correct, box, last_seen) "
        "VALUES (1, 'flags', ?, 5, 5, ?, datetime('now', ?))",
        [("NOR", 5, "-40 days"),   # mastered, but 40 days ago: due (every 30 days)
         ("SWE", 5, "-2 days"),    # mastered 2 days ago: not due
         ("FIN", 2, "-4 days"),    # box 2 comes back after 3 days: due
         ("DNK", 0, "-1 days")],   # still struggling: not counted as 'review'
    )
    db.commit()
    assert progress.due_counts(db, 1) == {"flags": 1 + 1}
    report = knowledge.report(db, 1)
    assert report["mastery"]["flags"]["NOR"][3] is True and report["mastery"]["flags"]["SWE"][3] is False


def test_items_that_are_not_due_come_up_less(client, db):
    db.executemany(
        "INSERT INTO mastery (user_id, game, item_id, seen, correct, box, last_seen) "
        "VALUES (1, 'flags', ?, 3, 3, 3, datetime('now', ?))",
        [("NOR", "-10 days"), ("SWE", "-1 days")],  # box 3 = every 7 days: Norway is due, Sweden isn't
    )
    db.commit()
    picks = Counter(progress.pick_next(db, 1, "flags", ["NOR", "SWE"]) for _ in range(2000))
    assert picks["NOR"] > 3 * picks["SWE"]


# ---------- Achievements ----------

def test_achievements_unlock_once_and_give_xp(client, db):
    r = client.post("/api/flags/answer", json={"item_id": "NOR", "guess": "Norway"}).get_json()
    assert [a["code"] for a in r["unlocked"]] == ["first_steps"]
    assert r["me"]["xp"] == 10 + 10
    again = client.post("/api/flags/answer", json={"item_id": "SWE", "guess": "Sweden"}).get_json()
    assert again["unlocked"] == []
    listing = achievements.listing(db, 1)
    assert sum(1 for a in listing if a["unlocked_at"]) == 1 and len(listing) == len(achievements.ACHIEVEMENTS)


def test_streak_and_goal_achievements(client, db):
    for day in range(7):
        answer(db, 1, day, xp=60)
    codes = {a["code"] for a in achievements.check(db, 1)}
    assert {"first_steps", "goal_getter", "daily_habit"} <= codes and "month_of_maps" not in codes


def test_map_game_achievements(client, db):
    db.execute("INSERT INTO runs (user_id, game, variant, score, total, solved, finished_at) "
               "VALUES (1, 'hotcold', '', 1, NULL, 1, CURRENT_TIMESTAMP)")
    db.execute("INSERT INTO runs (user_id, game, variant, score, total, solved, finished_at) "
               "VALUES (1, 'nameall', 'europe', 46, 46, 1, CURRENT_TIMESTAMP)")
    db.commit()
    codes = {a["code"] for a in achievements.check(db, 1)}
    assert {"lucky_guess", "sharp_shooter", "full_house"} <= codes and "whole_world" not in codes


# ---------- Leaderboards ----------

def test_weekly_league_and_champion(client, db):
    ana, ben = add_player(db, "ana"), add_player(db, "ben")
    week_start_offset = db.execute("SELECT julianday('now') - julianday(date('now', 'weekday 0', '-6 days'))").fetchone()[0]
    last_week = int(week_start_offset) + 3  # a day in last week
    answer(db, ana, last_week, xp=500)
    answer(db, ben, last_week, xp=100)
    answer(db, ben, 0, xp=40)  # this week, ben leads

    week = leaderboard.weekly(db)
    assert [p["name"] for p in week][:2] == ["ben", "ana"]
    assert next(p for p in week if p["name"] == "ana")["champion"]
    assert leaderboard.all_time(db)[0]["name"] == "ana"
    table = client.get("/leaderboard").get_data(as_text=True).split("<tbody>")[1]
    assert "👑" in table and table.index("ben") < table.index("ana")

    assert "champion" in {a["code"] for a in achievements.check(db, ana)}  # worth 100 XP, this week
    assert "champion" not in {a["code"] for a in achievements.check(db, ben)}
    assert leaderboard.weekly(db)[0]["name"] == "ana"


def test_records(client, db):
    ana = add_player(db, "ana")
    for user, score, seconds in [(1, 30, 400), (1, 35, 500), (ana, 35, 300)]:
        db.execute("INSERT INTO runs (user_id, game, variant, score, total, seconds, finished_at) "
                   "VALUES (?, 'nameall', 'africa', ?, 54, ?, CURRENT_TIMESTAMP)", (user, score, seconds))
    db.commit()
    africa = leaderboard.records(db)["nameall"]["africa"]
    assert [(r["name"], r["score"], r["seconds"]) for r in africa] == [("ana", 35, 300), ("tester", 35, 500)]
    assert leaderboard.personal_bests(db, 1)["nameall"]["africa"]["score"] == 35
    assert "ana" in client.get("/leaderboard?tab=records").get_data(as_text=True)


def test_knowledge_page_with_everything(client):
    client.post("/api/flags/answer", json={"item_id": "NOR", "guess": "Norway"})
    run = client.post("/api/nameall/start", json={"variant": "oceania"}).get_json()["run_id"]
    client.post("/api/nameall/finish", json={"run_id": run, "found": ["AUS", "NZL"]})
    page = client.get("/knowledge").get_data(as_text=True)
    for text in ["XP per day", "Achievements", "First steps", "Name them all", "Mastery map", "2 / 14"]:
        assert text in page, text
