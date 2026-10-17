from datetime import timedelta

from utility_bot.core.formatting import humanize_duration, progress_bar, sparkline, star_rating, truncate


def test_humanize_duration() -> None:
    assert humanize_duration(timedelta(0)) == "0 seconds"
    assert humanize_duration(timedelta(seconds=1)) == "1 second"
    assert humanize_duration(timedelta(days=2, hours=3, minutes=5, seconds=9)) == "2 days, 3 hours, 5 minutes"
    assert humanize_duration(timedelta(hours=1, seconds=4), max_parts=1) == "1 hour"


def test_progress_bar() -> None:
    assert progress_bar(0, 4) == "░░░░"
    assert progress_bar(0.5, 4) == "██░░"
    assert progress_bar(1, 4) == "████"
    assert progress_bar(7, 4) == "████"  # clamped


def test_sparkline() -> None:
    assert sparkline([]) == ""
    assert sparkline([3, 3, 3]) == "▄▄▄"
    line = sparkline([1, 2, 3, 4, 5, 6, 7, 8])
    assert line[0] == "▁" and line[-1] == "█" and len(line) == 8


def test_star_rating() -> None:
    assert star_rating(3) == "★★★☆☆"
    assert star_rating(None) == "Not rated"
    assert star_rating(9) == "★★★★★"


def test_truncate() -> None:
    assert truncate("short", 10) == "short"
    assert truncate("a" * 20, 10) == "a" * 9 + "…"
    assert len(truncate("x" * 500, 100)) == 100
