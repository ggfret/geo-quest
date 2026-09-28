"""The map games: Pin it, Hot & Cold, Neighbours, Name them all and Higher or Lower.

Each game is one module with its own page and API routes, registered on this blueprint.
"""

from flask import Blueprint

from games import COUNTRY_BY_ID

bp = Blueprint("challenges", __name__)

from challenges import hotcold, higherlower, nameall, neighbours, pin  # noqa: E402  (registers the routes)

CHALLENGES = [pin.GAME, hotcold.GAME, neighbours.GAME, nameall.GAME, higherlower.GAME]


def item_rows():
    """(game, item id, name, region) for the `items` table: the countries each map game tracks mastery for."""
    for game in CHALLENGES:
        for cid in game.pool:
            yield game.slug, cid, COUNTRY_BY_ID[cid]["name"], COUNTRY_BY_ID[cid]["continent"]
