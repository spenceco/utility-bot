"""The bot's own SQLite database (reminders, polls, command usage).

Every query here is a tiny indexed lookup that finishes in well under a
millisecond, so the stores call sqlite3 directly instead of pulling in an
async driver. The schema is created on first run and is safe to re-run.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    guild_id    INTEGER,                -- NULL when created in a DM
    message     TEXT    NOT NULL,
    created_at  INTEGER NOT NULL,       -- unix seconds (UTC)
    due_at      INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_reminders_due  ON reminders(due_at);
CREATE INDEX IF NOT EXISTS idx_reminders_user ON reminders(user_id);

CREATE TABLE IF NOT EXISTS polls (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    message_id  INTEGER,                -- filled in once the poll is posted
    author_id   INTEGER NOT NULL,
    question    TEXT    NOT NULL,
    options     TEXT    NOT NULL,       -- JSON list of option labels
    created_at  INTEGER NOT NULL,
    closed      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS poll_votes (
    poll_id     INTEGER NOT NULL REFERENCES polls(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL,
    option      INTEGER NOT NULL,
    PRIMARY KEY (poll_id, user_id)      -- one vote per user per poll
);

CREATE TABLE IF NOT EXISTS command_usage (
    command     TEXT PRIMARY KEY,
    uses        INTEGER NOT NULL DEFAULT 0
);
"""


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (and if needed create) the database with sensible settings."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # safer writes if the process dies
    conn.executescript(SCHEMA)
    return conn
