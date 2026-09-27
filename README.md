# Geo Quest

A geography learning website with five games, an XP system, and a page that shows what you know and what you keep mixing up.

Built with [Flask](https://flask.palletsprojects.com/) and SQLite, with plain JavaScript and no build step.

## The games

| Game | You see | You answer |
|---|---|---|
| 🏳️ Flags | A flag | Type the country |
| 🗺️ Outlines | A country's border shape | Type the country |
| 🏛️ Capitals | A country | Type its capital |
| 👥 Ethnicities | A bar chart of the ethnic groups (groups named after the country are hidden) | Type the country |
| 🗣️ Languages | A sentence in one of 66 languages | Pick from 4 look-alike languages |

After every answer you get something to help you remember: a fact card, a lookalike tip (Chad vs Romania, Slovenia vs Slovakia), a "how to spot it" clue for languages, and a mini-map zoomed in on where the country is.

## Features

- **Forgiving typing:** accents, upper/lower case and small typos are fine, and alternative names count ("USA", "Holland", "Burma"). A *different* real country is always wrong, and is saved as a mix-up.
- **Spaced repetition:** each country has a mastery level from 0 to 5 in each game. Weak and new countries come up often; mastered ones rarely.
- **XP and levels** shared across all games, with streak bonuses.
- **My Knowledge page:** mastery maps per game, accuracy by continent, your easiest and hardest areas, and your most common mix-ups.
- 233 countries and territories, including partly recognised states (Taiwan, Kosovo) and self-governing territories (Greenland, Faroe Islands, Hong Kong).
- Responsive layout with automatic light and dark mode.

## Getting started

You need Python 3.10 or newer.

```bash
git clone https://github.com/ggfret/geo-quest.git
cd geo-quest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5070.

Your progress is saved in `geo.db`, which is created on first run and ignored by git, so it stays on your machine.

Run the tests with `pytest`.

## Project structure

```
app.py              Flask routes: pages and the JSON API the games talk to
games.py            The five games: what each asks, which answers count, what it explains afterwards
answers.py          The answer checker (accents, alternative names, typo tolerance)
progress.py         XP, levels and spaced repetition (which country to ask next)
knowledge.py        SQL queries behind the My Knowledge page
schema.sql          Tables: users, attempts, mastery, items
templates/          HTML pages (Jinja templates)
static/             game.js (play loop), knowledge.js, style.css, world.svg
data/               Game data (countries, flags, capitals, outlines, ethnicities, languages)
data/raw/           The downloaded source datasets
scripts/            Rebuild data/ from data/raw/
tests/              pytest tests
```

## How it works

Every answer is saved as a row in the `attempts` table, and each country's mastery level (0–5) in each game is kept in `mastery`. A correct answer moves it up one level and a wrong answer down two. When picking the next question, `progress.pick_next` weights countries by their level, so a country at level 0 comes up about 16 times as often as one at level 5.

The My Knowledge page is plain SQL over those tables, joined with `items` (every askable country or language with its continent or writing system).

To rebuild the game data from the raw sources:

```bash
python scripts/build_countries.py
python scripts/build_outlines.py
python scripts/build_ethnicities.py
```

## Data sources

| Data | Source | License |
|---|---|---|
| Country names, capitals, regions | [mledoze/countries](https://github.com/mledoze/countries) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| Borders and world map | [Natural Earth](https://www.naturalearthdata.com/) via [world-atlas](https://github.com/topojson/world-atlas) | Public domain |
| Ethnic groups | CIA World Factbook via [factbook.json](https://github.com/factbook/factbook.json) | Public domain (CC0) |
| Flag images | [flagcdn.com](https://flagcdn.com/), loaded in the browser | Public domain |

`data/countries.json` is derived from mledoze/countries and is therefore also under the ODbL. The fact cards, lookalike tips, language sentences and clues were written for this project and may contain mistakes. Corrections are welcome.

## Ideas for later

- User accounts, so friends can play and compare
- A more detailed map for tiny countries in Outlines
- More fact cards
- Deploy it online

## License

Code: [MIT](LICENSE). Data: see the table above.
