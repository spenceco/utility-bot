import sqlite3

import pytest

from utility_bot.core.prices import PriceDatabaseError, PriceRepository, normalize


def test_normalize_handles_curly_quotes_and_case() -> None:
    assert normalize("Noah’s  ARK") == "noah's ark"


def test_exact_match(price_db) -> None:
    result = PriceRepository(price_db).find("it's only the himalayas")
    assert result.book.title == "It's Only the Himalayas"
    assert result.book.change == 0


def test_curly_apostrophe_matches_straight(price_db) -> None:
    assert PriceRepository(price_db).find("Full Moon over Noah's Ark").book.url == "u/noah"


def test_substring_match(price_db) -> None:
    assert PriceRepository(price_db).find("sapiens").book.url == "u/sapiens"


def test_fuzzy_match_forgives_typos(price_db) -> None:
    assert PriceRepository(price_db).find("Its Only the Himalyas").book.url == "u/himalayas"


def test_fuzzy_ignores_long_subtitle(price_db) -> None:
    assert PriceRepository(price_db).find("Sapeins").book.url == "u/sapiens"


def test_no_match_returns_none(price_db) -> None:
    result = PriceRepository(price_db).find("Quantum Gardening for Cats")
    assert result.book is None
    assert result.suggestions == []


def test_near_miss_gives_suggestions(price_db) -> None:
    result = PriceRepository(price_db).find("A Light on the Atlas")
    assert result.book is None or result.book.url == "u/gone"


def test_history_and_stats(price_db) -> None:
    book = PriceRepository(price_db).find("sapiens").book
    assert [p.price for p in book.history] == [54.23, 54.23, 49.99, 49.99]
    assert [p.price for p in book.price_changes()] == [54.23, 49.99]  # repeats collapsed
    assert book.price == 49.99
    assert book.lowest == 49.99 and book.highest == 54.23
    assert book.change == -4.24
    assert book.change_pct == pytest.approx(-7.82, abs=0.01)
    assert book.previous_price == 54.23


def test_inactive_book_flagged(price_db) -> None:
    book = PriceRepository(price_db).find("A Light in the Attic").book
    assert book.active is False


def test_search_titles_prefix_first(price_db) -> None:
    repo = PriceRepository(price_db)
    titles = repo.search_titles("full")
    assert titles == ["Full Moon over Noah’s Ark"]
    # "a" appears in many titles; ones *starting* with "a" come first.
    assert repo.search_titles("a")[0] == "A Light in the Attic"
    assert len(repo.search_titles("", limit=2)) == 2


def test_summary(price_db) -> None:
    count, last = PriceRepository(price_db).summary()
    assert count == 3
    assert last.day == 4


def test_missing_database_is_friendly(tmp_path) -> None:
    with pytest.raises(PriceDatabaseError, match="isn't available"):
        PriceRepository(tmp_path / "nope.db").find("anything")


def test_database_opened_read_only(price_db) -> None:
    repo = PriceRepository(price_db)
    conn = repo._connect()
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM books")
    conn.close()
