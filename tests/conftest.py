"""Shared fixtures: an in-memory bot database and a fake price-tracker DB."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from utility_bot.core.database import connect

# Same schema the book-price-tracker project creates.
TRACKER_SCHEMA = """
CREATE TABLE runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL,
    finished_at TEXT, books_scraped INTEGER DEFAULT 0, new_books INTEGER DEFAULT 0,
    removed_books INTEGER DEFAULT 0, price_changes INTEGER DEFAULT 0, errors INTEGER DEFAULT 0);
CREATE TABLE books (url TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
    price REAL NOT NULL, rating INTEGER, in_stock INTEGER, first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE price_history (id INTEGER PRIMARY KEY AUTOINCREMENT, url TEXT NOT NULL,
    run_id INTEGER NOT NULL, price REAL NOT NULL, scraped_at TEXT NOT NULL);
"""

BOOKS = [
    # url, title, category, rating, in_stock, active, prices over 4 daily runs
    ("u/sapiens", "Sapiens: A Brief History of Humankind", "History", 5, 1, 1, [54.23, 54.23, 49.99, 49.99]),
    ("u/himalayas", "It's Only the Himalayas", "Travel", 2, 1, 1, [45.17, 45.17, 45.17, 45.17]),
    ("u/noah", "Full Moon over Noah’s Ark", "Travel", 4, 0, 1, [49.43, 51.00, 51.00, 52.10]),
    ("u/gone", "A Light in the Attic", "Poetry", 3, 1, 0, [51.77, 51.77]),
]


@pytest.fixture
def bot_db() -> sqlite3.Connection:
    conn = connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def price_db(tmp_path: Path) -> Path:
    path = tmp_path / "price_history.db"
    conn = sqlite3.connect(path)
    conn.executescript(TRACKER_SCHEMA)
    for run in range(1, 5):
        conn.execute(
            "INSERT INTO runs (started_at, finished_at) VALUES (?, ?)",
            (f"2026-10-0{run}T06:00:00+00:00", f"2026-10-0{run}T06:05:00+00:00"),
        )
    for url, title, category, rating, in_stock, active, prices in BOOKS:
        conn.execute(
            "INSERT INTO books VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (url, title, category, prices[-1], rating, in_stock,
             "2026-10-01T06:00:00+00:00", f"2026-10-0{len(prices)}T06:00:00+00:00", active),
        )
        for run, price in enumerate(prices, start=1):
            conn.execute(
                "INSERT INTO price_history (url, run_id, price, scraped_at) VALUES (?, ?, ?, ?)",
                (url, run, price, f"2026-10-0{run}T06:00:00+00:00"),
            )
    conn.commit()
    conn.close()
    return path
