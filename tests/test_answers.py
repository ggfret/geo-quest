import json
from pathlib import Path

import pytest

from answers import check, normalize

COUNTRIES = json.loads((Path(__file__).parent.parent / "data" / "countries.json").read_text())
NAMES = {c["id"]: c["names"] for c in COUNTRIES}


@pytest.mark.parametrize("guess, target", [
    ("Norway", "NOR"),
    ("  norway ", "NOR"),
    ("USA", "USA"),
    ("america", "USA"),
    ("UK", "GBR"),
    ("cote divoire", "CIV"),
    ("Côte d'Ivoire", "CIV"),
    ("Ivory Coast", "CIV"),
    ("Czech Republic", "CZE"),
    ("Turkey", "TUR"),
    ("st lucia", "LCA"),
    ("The Netherlands", "NLD"),
    ("Holland", "NLD"),
    ("DRC", "COD"),
    ("Burma", "MMR"),
    ("Congo", "COG"),
])
def test_accepted_names(guess, target):
    result = check(guess, target, NAMES)
    assert result.correct and not result.typo


@pytest.mark.parametrize("guess, target", [
    ("Kazakstan", "KAZ"),
    ("Phillipines", "PHL"),
    ("Mozambiqe", "MOZ"),
    ("Slovinia", "SVN"),
    ("Norwya", "NOR"),
])
def test_small_typos_are_forgiven(guess, target):
    result = check(guess, target, NAMES)
    assert result.correct and result.typo


@pytest.mark.parametrize("guess, target, confused_with", [
    ("Slovakia", "SVN", "SVK"),   # a real different country is never a "typo"
    ("Austria", "AUS", "AUT"),
    ("Niger", "NGA", "NER"),
    ("Iran", "IRQ", "IRN"),
    ("Romania", "TCD", "ROU"),
])
def test_other_countries_are_wrong(guess, target, confused_with):
    result = check(guess, target, NAMES)
    assert not result.correct
    assert result.guessed_id == confused_with


def test_nonsense_is_wrong():
    assert not check("asdfgh", "NOR", NAMES).correct
    assert not check("", "NOR", NAMES).correct
    assert not check("Nor", "NOR", NAMES).correct  # short answers must be exact


def test_normalize():
    assert normalize("  Côte d'Ivoire ") == "cote divoire"
    assert normalize("St. Kitts & Nevis") == "saint kitts and nevis"
    assert normalize("The Gambia") == "gambia"
