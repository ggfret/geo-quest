"""Checking typed answers: forgiving about accents, case and small typos,
but strict when the guess is really a *different* country.
"""

import re
import unicodedata
from dataclasses import dataclass


def normalize(text):
    """'  Côte d'Ivoire ' -> 'cote divoire',  'St. Lucia' -> 'saint lucia'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", " and ").replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    words = text.split()
    if words and words[0] == "the":
        words = words[1:]
    words = ["saint" if w == "st" else w for w in words]
    return " ".join(words)


def edit_distance(a, b):
    """How many single-letter edits turn a into b. Swapping two neighbouring
    letters ('norwya' -> 'norway') counts as one edit."""
    d = [[i + j if i * j == 0 else 0 for j in range(len(b) + 1)] for i in range(len(a) + 1)]
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (a[i - 1] != b[j - 1]))
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[-1][-1]


def typo_allowance(name):
    """Short names must be exact; longer ones may have 1-2 wrong letters."""
    if len(name) <= 4:
        return 0
    return 1 if len(name) <= 7 else 2


@dataclass
class Result:
    correct: bool
    typo: bool = False         # right, but misspelled
    guessed_id: str = None     # which item the guess matched, if any (for "you confused X with Y")


def identify(guess, names_by_id):
    """Which item does this guess name? Returns (item id, typo) or (None, False).

    Same forgiveness as check(): exact names first, then small typos when only one item is that close.
    """
    g = normalize(guess)
    if not g:
        return None, False
    for item_id, names in names_by_id.items():
        if any(normalize(n) == g for n in names):
            return item_id, False
    closest = sorted(
        (min((edit_distance(g, normalize(n)), typo_allowance(normalize(n))) for n in names), item_id)
        for item_id, names in names_by_id.items()
    )
    (best_dist, allowance), best_id = closest[0]
    tie = len(closest) > 1 and closest[1][0][0] == best_dist
    if best_dist <= allowance and not tie:
        return best_id, True
    return None, False


def check(guess, target_id, names_by_id):
    """Is `guess` a correct name for `target_id`?

    names_by_id maps every possible answer id to its accepted names, e.g.
    {"NOR": ["Norway", "Kingdom of Norway", ...], ...}. We need all of them to
    tell "a typo of the right answer" apart from "a different country".
    """
    g = normalize(guess)
    if not g:
        return Result(False)

    # 1. Exact match (after normalizing) on the target or on something else.
    exact = [i for i, names in names_by_id.items() if any(normalize(n) == g for n in names)]
    if target_id in exact:
        return Result(True)
    if exact:
        return Result(False, guessed_id=exact[0])

    # 2. Closest spelling across all items.
    closest = {}  # id -> (distance, allowance)
    for i, names in names_by_id.items():
        closest[i] = min((edit_distance(g, normalize(n)), typo_allowance(normalize(n))) for n in names)
    ranked = sorted(closest.items(), key=lambda kv: kv[1][0])
    best_id, (best_dist, allowance) = ranked[0]
    tie = len(ranked) > 1 and ranked[1][1][0] == best_dist

    if best_dist <= allowance and not tie:
        if best_id == target_id:
            return Result(True, typo=True)
        return Result(False, guessed_id=best_id)
    return Result(False)
