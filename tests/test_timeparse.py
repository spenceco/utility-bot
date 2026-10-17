from datetime import timedelta

import pytest

from utility_bot.core.timeparse import TimeParseError, parse_duration, validate_reminder_delay


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("10m", timedelta(minutes=10)),
        ("30s", timedelta(seconds=30)),
        ("2h", timedelta(hours=2)),
        ("1h30m", timedelta(hours=1, minutes=30)),
        ("1h 30m", timedelta(hours=1, minutes=30)),
        ("2 hours 15 minutes", timedelta(hours=2, minutes=15)),
        ("1 hour and 5 mins", timedelta(hours=1, minutes=5)),
        ("in 3 days", timedelta(days=3)),
        ("1w 2d", timedelta(weeks=1, days=2)),
        ("1.5h", timedelta(minutes=90)),
        ("15", timedelta(minutes=15)),  # bare number = minutes
        ("  10M  ", timedelta(minutes=10)),
        ("1d, 4h", timedelta(days=1, hours=4)),
    ],
)
def test_parses_valid_durations(text: str, expected: timedelta) -> None:
    assert parse_duration(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "soon", "10 parsecs", "abc 10m", "10m xyz", "1h30", "-5m"])
def test_rejects_garbage(text: str) -> None:
    with pytest.raises(TimeParseError):
        parse_duration(text)


def test_unknown_unit_error_names_the_unit() -> None:
    with pytest.raises(TimeParseError, match="parsecs"):
        parse_duration("10 parsecs")


def test_validate_bounds() -> None:
    validate_reminder_delay(timedelta(seconds=10))
    validate_reminder_delay(timedelta(days=365))
    with pytest.raises(TimeParseError):
        validate_reminder_delay(timedelta(seconds=5))
    with pytest.raises(TimeParseError):
        validate_reminder_delay(timedelta(days=366))
