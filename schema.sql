CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    password_hash TEXT,              -- NULL only for progress saved before accounts existed
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- One row per answer, in every game. Everything else can be computed from this.
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    game TEXT NOT NULL,              -- 'flags', 'capitals', 'outlines', 'ethnicities', 'languages'
    item_id TEXT NOT NULL,           -- country id like 'NOR', or a language name
    guess TEXT NOT NULL,             -- exactly what was typed / clicked
    correct INTEGER NOT NULL,        -- 1 or 0
    typo INTEGER NOT NULL DEFAULT 0, -- 1 if correct but misspelled
    guessed_id TEXT,                 -- the item the guess matched (for wrong answers: what you confused it with)
    xp INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_attempts_user_game ON attempts(user_id, game, id);

-- How well each user knows each item in each game (a summary of attempts, kept up to date).
-- box goes 0..5: up one step per correct answer, down two per wrong one. Higher box = shown less often.
CREATE TABLE IF NOT EXISTS mastery (
    user_id INTEGER NOT NULL REFERENCES users(id),
    game TEXT NOT NULL,
    item_id TEXT NOT NULL,
    seen INTEGER NOT NULL DEFAULT 0,
    correct INTEGER NOT NULL DEFAULT 0,
    box INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT,
    PRIMARY KEY (user_id, game, item_id)
);

-- Every askable item per game, with a readable name and a region, so stats can be
-- grouped with plain SQL (e.g. accuracy by continent). Refilled from the data files on startup.
CREATE TABLE IF NOT EXISTS items (
    game TEXT NOT NULL,
    item_id TEXT NOT NULL,
    name TEXT NOT NULL,
    region TEXT NOT NULL,            -- continent for country games, writing system for languages
    PRIMARY KEY (game, item_id)
);

-- Wrong passwords, to slow down anyone guessing: 5 per username per 10 minutes.
CREATE TABLE IF NOT EXISTS login_failures (
    username TEXT NOT NULL,
    at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attempts_user_time ON attempts(user_id, created_at);

-- Games with several steps per round (Hot & Cold, Neighbours, Name them all, Higher or Lower).
-- A run is one round; its answers still go into `attempts`, this keeps the round itself.
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    game TEXT NOT NULL,
    variant TEXT NOT NULL DEFAULT '',      -- continent for Name them all, stat for Higher or Lower
    state TEXT NOT NULL DEFAULT '{}',      -- JSON: the round's progress (mystery country, guesses, ...)
    score INTEGER NOT NULL DEFAULT 0,      -- countries named / streak / guesses used / neighbours found
    total INTEGER,                         -- how many there were to find, where that applies
    solved INTEGER NOT NULL DEFAULT 0,     -- 1 if the round was won (Hot & Cold found, all neighbours named, ...)
    seconds INTEGER,                       -- how long the round took
    bonus_xp INTEGER NOT NULL DEFAULT 0,   -- XP on top of the per-answer XP (e.g. naming a whole continent)
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT                       -- NULL while still playing
);
CREATE INDEX IF NOT EXISTS idx_runs_user_game ON runs(user_id, game, finished_at);

-- Badges, unlocked once per player.
CREATE TABLE IF NOT EXISTS achievements (
    user_id INTEGER NOT NULL REFERENCES users(id),
    code TEXT NOT NULL,
    xp INTEGER NOT NULL DEFAULT 0,
    unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, code)
);

-- Every bit of XP in one place: answers, round bonuses and achievement rewards.
-- Levels, the daily goal and the leaderboards all add up this view.
DROP VIEW IF EXISTS xp_events;
CREATE VIEW xp_events AS
    SELECT user_id, game, xp, created_at AS at FROM attempts WHERE xp > 0
    UNION ALL
    SELECT user_id, game, bonus_xp, finished_at FROM runs WHERE bonus_xp > 0 AND finished_at IS NOT NULL
    UNION ALL
    SELECT user_id, 'achievements', xp, unlocked_at FROM achievements WHERE xp > 0;
