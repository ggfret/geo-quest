from collections import Counter

import progress
from answers import Result


def test_levels():
    assert progress.level_info(0)["level"] == 1
    assert progress.level_info(99)["level"] == 1
    assert progress.level_info(100)["level"] == 2
    assert progress.level_info(250)["level"] == 3  # 100 + 150


def test_xp_and_streak(client, db):
    assert progress.record(db, 1, "flags", "NOR", "Norway", Result(True)) == 10
    assert progress.record(db, 1, "flags", "SWE", "Sweden", Result(True)) == 12  # streak of 1
    assert progress.record(db, 1, "flags", "FIN", "Norway", Result(False, guessed_id="NOR")) == 0
    assert progress.current_streak(db, 1, "flags") == 0
    assert progress.summary(db, 1)["xp"] == 22


def test_mastery_boxes(client, db):
    for _ in range(3):
        progress.record(db, 1, "flags", "NOR", "Norway", Result(True))
    box = lambda: db.execute("SELECT box FROM mastery WHERE item_id = 'NOR'").fetchone()["box"]
    assert box() == 3
    progress.record(db, 1, "flags", "NOR", "Sweden", Result(False))
    assert box() == 1


def test_mastered_items_are_picked_less(client, db):
    # Master NOR (box 5); leave the others unseen.
    db.execute("INSERT INTO mastery (user_id, game, item_id, seen, correct, box) VALUES (1, 'flags', 'NOR', 9, 9, 5)")
    picks = Counter(progress.pick_next(db, 1, "flags", ["NOR", "SWE", "FIN", "DNK"]) for _ in range(3000))
    assert picks["NOR"] < picks["SWE"] / 5


def test_recent_items_are_not_repeated(client, db):
    progress.record(db, 1, "flags", "NOR", "Norway", Result(True))
    picks = {progress.pick_next(db, 1, "flags", ["NOR", "SWE"]) for _ in range(200)}
    assert picks == {"SWE"}
