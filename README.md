# Geo Quest

A geography learning website with ten games, XP and levels, day streaks, a weekly league with friends, achievements, and a page that shows what you know, what you keep mixing up and what's due for review.

Built with [Flask](https://flask.palletsprojects.com/) and SQLite, with plain JavaScript and no build step.

## The games

**Quizzes**

| Game | You see | You answer |
|---|---|---|
| 🏳️ Flags | A flag | Type the country |
| 🗺️ Outlines | A country's border shape | Type the country |
| 🏛️ Capitals | A country | Type its capital |
| 👥 Ethnicities | A bar chart of the ethnic groups (groups named after the country are hidden) | Type the country |
| 🗣️ Languages | A sentence in one of 66 languages | Pick from 4 look-alike languages |

**Map games**

| Game | How it works |
|---|---|
| 📍 Pin it | Click where a country is on a zoomable blank map. A hit counts if you're inside it (or within 50 km, for tiny countries and coasts); near misses still earn some XP. |
| 🔥 Hot & Cold | Guess a mystery country. Each guess shows the distance, a direction arrow and whether it's a neighbour, and colours the map warmer as you get closer. |
| 🤝 Neighbours | Name every country that borders the one shown. They fill in on the map; three wrong names end the round. |
| ⏱️ Name them all | Name every country of a continent (or all 197) before the timer runs out. Names are accepted the moment they're typed; afterwards the map shows what you forgot. |
| ⬆️ Higher or Lower | Is country B's population, area, GDP per person, life expectancy or highest point higher or lower than country A's? The pairs get closer as your streak grows. |

After every answer you get something to help you remember: a fact card, a lookalike tip (Chad vs Romania, Slovenia vs Slovakia), a "how to spot it" clue for languages, and a map of where the country is.

## Features

- **Forgiving typing:** accents, upper/lower case and small typos are fine, and alternative names count ("USA", "Holland", "Burma"). A *different* real country is always wrong, and is saved as a mix-up.
- **Spaced repetition that fades:** each country has a mastery level from 0 to 5 in each game. Weak and new countries come up often. Known ones come back for review after 1, 3, 7, 14 and then 30 days, so you don't forget them.
- **XP, levels, a 🔥 day streak and a daily goal** of 50 XP, shown in the header.
- **Accounts and leaderboards:** a weekly league that resets every Monday (👑 for last week's winner), all-time totals, and records for the map games (best Name them all per continent, longest Higher or Lower streak, and more).
- **25 achievements**, each worth some XP, from "First steps" to "The whole world".
- **My Knowledge page:** XP per day, mastery maps per game (with what's due for review), accuracy by continent, your hardest countries, your most common mix-ups, your records and your badges.
- 233 countries and territories, including partly recognised states (Taiwan, Kosovo) and self-governing territories (Greenland, Faroe Islands, Hong Kong).
- Responsive layout with automatic light and dark mode.

## Getting started

You need Python 3.10 or newer.

```bash
git clone https://github.com/ggfret/geo-quest.git
cd geo-quest
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python app.py
```

Then open http://127.0.0.1:5070.

Create an account on the sign-up page. Progress is saved in `geo.db`, which is created on first run and ignored by git, so it stays on your machine. To use another database file or port, set `GEO_DATABASE` or `PORT`, e.g. `GEO_DATABASE=test.db PORT=5071 python app.py`.

Logins are kept in a signed cookie. Locally, the signing key is generated into `instance/secret_key` (also ignored by git). To put the site online for friends, follow [DEPLOY.md](DEPLOY.md).

Run the tests with `pytest`.

## Project structure

```
app.py              Flask routes: pages, the quiz API, the leaderboard and the Knowledge page
games.py            The five quizzes: what each asks, which answers count, what it explains afterwards
challenges/         The five map games, one module each (pin, hotcold, neighbours, nameall, higherlower)
answers.py          The answer checker (accents, alternative names, typo tolerance)
geo.py              Map geometry: projection, distances, directions, which country a click is in
progress.py         XP, levels, day streaks, the daily goal and spaced repetition (what to ask next)
achievements.py     The 25 badges and when they unlock
leaderboard.py      The weekly league, all-time totals and records
knowledge.py        SQL queries behind the My Knowledge page
auth.py             Sign up and log in (hashed passwords, login throttling)
database.py         The SQLite connection and the logged-in user
schema.sql          Tables: users, attempts, mastery, items, runs, achievements, plus the xp_events view
templates/          HTML pages (Jinja templates)
static/             common.js (shared helpers), worldmap.js (zoomable map), one script per game, style.css
data/               Game data (countries, flags, capitals, outlines, ethnicities, languages, stats)
data/raw/           The downloaded source datasets
scripts/            Rebuild data/ from data/raw/
tests/              pytest tests
```

## How it works

Every answer is saved as a row in the `attempts` table, and each country's mastery level (0–5) in each game is kept in `mastery`. A correct answer moves it up one level and a wrong answer down two. When picking the next question, `progress.pick_next` weights countries by their level and by whether they're due for review, so a struggling country comes up far more often than a mastered one that isn't due yet.

The map games that take several steps (Hot & Cold, Neighbours, Name them all, Higher or Lower) save each round in `runs`, so a round survives leaving the page. All XP, from answers, round bonuses and badges, is added up by the `xp_events` view, which the levels, the daily goal and the leaderboards read.

The My Knowledge page and the leaderboards are plain SQL over those tables, joined with `items` (every askable country or language with its continent or writing system).

To rebuild the game data from the raw sources:

```bash
python scripts/build_countries.py
python scripts/build_outlines.py
python scripts/build_ethnicities.py
python scripts/build_stats.py
```

To refresh the Factbook extracts, download [factbook.json](https://github.com/factbook/factbook.json) and run `python scripts/extract_factbook.py <unzipped folder>` first.

## Data sources

| Data | Source | License |
|---|---|---|
| Country names, capitals, regions, borders, area | [mledoze/countries](https://github.com/mledoze/countries) | [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) |
| Country shapes and world map | [Natural Earth](https://www.naturalearthdata.com/) via [world-atlas](https://github.com/topojson/world-atlas) | Public domain |
| Ethnic groups, population, GDP per person, life expectancy, highest points | CIA World Factbook via [factbook.json](https://github.com/factbook/factbook.json) | Public domain (CC0) |
| Flag images | [flagcdn.com](https://flagcdn.com/), loaded in the browser | Public domain |

`data/countries.json` is derived from mledoze/countries and is therefore also under the ODbL. The fact cards, lookalike tips, language sentences and clues were written for this project and may contain mistakes. Corrections are welcome.

## Ideas for later

- A more detailed map for tiny countries in Outlines and Pin it
- More fact cards
- A daily challenge everyone plays, for the league

## License

Code: [MIT](LICENSE). Data: see the table above.
