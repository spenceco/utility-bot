"""Read-only access to the book-price-tracker SQLite database.

The price tracker (a separate project) scrapes books.toscrape.com every day
and stores each book's price per run. This module finds a book by a fuzzy
title search and returns its current price plus history. The database is
opened in read-only mode, so the bot can never corrupt the tracker's data.
"""

from __future__ import annotations

import difflib
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


class PriceDatabaseError(Exception):
    """The price database is missing or unreadable. The message is user-facing."""


@dataclass(frozen=True)
class PricePoint:
    scraped_at: datetime
    price: float


@dataclass
class BookPrice:
    url: str
    title: str
    category: str
    price: float
    rating: int | None
    in_stock: bool
    active: bool          # False once the book disappeared from the store
    first_seen: datetime
    last_seen: datetime
    history: list[PricePoint] = field(default_factory=list)  # oldest first

    @property
    def lowest(self) -> float:
        return min((p.price for p in self.history), default=self.price)

    @property
    def highest(self) -> float:
        return max((p.price for p in self.history), default=self.price)

    @property
    def first_price(self) -> float:
        return self.history[0].price if self.history else self.price

    @property
    def change(self) -> float:
        """Current price minus the first price ever recorded."""
        return round(self.price - self.first_price, 2)

    @property
    def change_pct(self) -> float:
        return (self.change / self.first_price * 100) if self.first_price else 0.0

    @property
    def previous_price(self) -> float | None:
        """The price before the most recent change, if it ever changed."""
        changes = self.price_changes()
        return changes[-2].price if len(changes) >= 2 else None

    def price_changes(self) -> list[PricePoint]:
        """History collapsed to the moments the price actually moved.

        A daily scraper records the same price over and over; users only care
        about the points where it changed.
        """
        points: list[PricePoint] = []
        for point in self.history:
            if not points or point.price != points[-1].price:
                points.append(point)
        return points


@dataclass
class LookupResult:
    book: BookPrice | None
    suggestions: list[str] = field(default_factory=list)  # other close titles


def normalize(text: str) -> str:
    """Case- and punctuation-insensitive form used for matching titles."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return " ".join(text.casefold().split())


def main_title(normalized: str) -> str:
    """The part of a title before any subtitle, e.g. "sapiens" from "sapiens: a brief…"."""
    return re.split(r"[:(]", normalized, maxsplit=1)[0].strip() or normalized


def _parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value)


class PriceRepository:
    def __init__(self, db_path: Path | str) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.is_file():
            raise PriceDatabaseError(
                "The price database isn't available right now. The tracker may not have run yet."
            )
        try:
            # mode=ro: read-only, so the tracker's data can never be modified here.
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        except sqlite3.Error as exc:
            raise PriceDatabaseError("I couldn't open the price database.") from exc
        conn.row_factory = sqlite3.Row
        return conn

    def _titles(self, conn: sqlite3.Connection) -> list[sqlite3.Row]:
        return conn.execute("SELECT url, title, active FROM books").fetchall()

    def search_titles(self, partial: str, limit: int = 25) -> list[str]:
        """Titles for autocomplete: prefix matches first, then other substring matches."""
        needle = normalize(partial)
        with closing(self._connect()) as conn:
            rows = self._titles(conn)
        titles = sorted({r["title"] for r in rows if needle in normalize(r["title"])})
        titles.sort(key=lambda t: not normalize(t).startswith(needle))  # stable sort
        return titles[:limit]

    def find(self, query: str) -> LookupResult:
        """Best match for `query`: exact title, then substring, then fuzzy."""
        needle = normalize(query)
        if not needle:
            return LookupResult(None)

        with closing(self._connect()) as conn:
            rows = self._titles(conn)
            by_norm: dict[str, sqlite3.Row] = {}
            for row in rows:
                # Prefer active listings if two books share a title.
                key = normalize(row["title"])
                if key not in by_norm or (row["active"] and not by_norm[key]["active"]):
                    by_norm[key] = row

            # 1. Exact (normalised) title.
            if needle in by_norm:
                return LookupResult(self._load(conn, by_norm[needle]["url"]))

            # 2. Titles containing the query; the shortest is the closest fit.
            contains = sorted((k for k in by_norm if needle in k), key=len)
            if contains:
                others = [by_norm[k]["title"] for k in contains[1:6]]
                return LookupResult(self._load(conn, by_norm[contains[0]]["url"]), others)

            # 3. Fuzzy match to forgive typos ("sapeins"). Compare against both the
            #    full title and its main part (before any ":" or "("), so a short
            #    query isn't penalised for a long subtitle.
            fuzzy: dict[str, str] = {}
            for key in by_norm:
                fuzzy.setdefault(key, key)
                fuzzy.setdefault(main_title(key), key)
            close = difflib.get_close_matches(needle, list(fuzzy), n=8, cutoff=0.6)
            keys = list(dict.fromkeys(fuzzy[c] for c in close))  # dedupe, keep order
            if keys:
                others = [by_norm[k]["title"] for k in keys[1:6]]
                return LookupResult(self._load(conn, by_norm[keys[0]]["url"]), others)

            # Nothing good enough; offer a few near-misses as suggestions.
            loose = difflib.get_close_matches(needle, list(fuzzy), n=6, cutoff=0.5)
            keys = list(dict.fromkeys(fuzzy[c] for c in loose))[:3]
            return LookupResult(None, [by_norm[k]["title"] for k in keys])

    def _load(self, conn: sqlite3.Connection, url: str) -> BookPrice:
        book = conn.execute("SELECT * FROM books WHERE url = ?", (url,)).fetchone()
        history = conn.execute(
            "SELECT scraped_at, price FROM price_history WHERE url = ? ORDER BY scraped_at, id",
            (url,),
        ).fetchall()
        return BookPrice(
            url=book["url"],
            title=book["title"],
            category=book["category"],
            price=book["price"],
            rating=book["rating"],
            in_stock=bool(book["in_stock"]),
            active=bool(book["active"]),
            first_seen=_parse_ts(book["first_seen"]),
            last_seen=_parse_ts(book["last_seen"]),
            history=[PricePoint(_parse_ts(h["scraped_at"]), h["price"]) for h in history],
        )

    def summary(self) -> tuple[int, datetime | None]:
        """(number of tracked books, time of the latest finished scrape)."""
        with closing(self._connect()) as conn:
            count = conn.execute("SELECT COUNT(*) FROM books WHERE active = 1").fetchone()[0]
            last = conn.execute("SELECT MAX(finished_at) FROM runs").fetchone()[0]
        return count, _parse_ts(last) if last else None
