"""Turn human durations like "10m", "1h30m" or "2 days" into timedeltas."""

from __future__ import annotations

import re
from datetime import timedelta

MIN_DURATION = timedelta(seconds=10)
MAX_DURATION = timedelta(days=365)

# Every accepted spelling of each unit, mapped to its length in seconds.
_UNITS: dict[str, int] = {}
for _names, _seconds in (
    (("s", "sec", "secs", "second", "seconds"), 1),
    (("m", "min", "mins", "minute", "minutes"), 60),
    (("h", "hr", "hrs", "hour", "hours"), 3600),
    (("d", "day", "days"), 86400),
    (("w", "wk", "wks", "week", "weeks"), 604800),
):
    for _name in _names:
        _UNITS[_name] = _seconds

# One "<number><unit>" chunk, e.g. "1.5h" or "20 minutes".
_CHUNK = re.compile(r"(\d+(?:\.\d+)?)\s*([a-z]+)")


class TimeParseError(ValueError):
    """The text could not be understood as a duration. The message is user-facing."""


def parse_duration(text: str) -> timedelta:
    """Parse a duration string.

    Accepts one or more number+unit chunks, optionally separated by spaces,
    commas or "and", with an optional leading "in":
        "10m", "1h30m", "2 hours 15 minutes", "in 3 days", "1.5h", "1w 2d"
    A bare number is read as minutes ("15" -> 15 minutes).
    """
    cleaned = text.strip().lower()
    cleaned = re.sub(r"^in\s+", "", cleaned)
    cleaned = re.sub(r"(,|\band\b)", " ", cleaned).strip()
    if not cleaned:
        raise TimeParseError("Please give a time, like `10m`, `2h` or `1d 4h`.")

    if re.fullmatch(r"\d+(?:\.\d+)?", cleaned):
        return timedelta(minutes=float(cleaned))

    total = 0.0
    position = 0
    for match in _CHUNK.finditer(cleaned):
        # Anything between chunks other than whitespace means junk input.
        if cleaned[position : match.start()].strip():
            break
        number, unit = match.groups()
        if unit not in _UNITS:
            raise TimeParseError(
                f"I don't know the unit `{unit}`. Try s, m, h, d or w (e.g. `1h30m`)."
            )
        total += float(number) * _UNITS[unit]
        position = match.end()

    if position == 0 or cleaned[position:].strip():
        raise TimeParseError(
            f"I couldn't read `{text.strip()}` as a time. Try `10m`, `2h` or `1d 4h`."
        )
    return timedelta(seconds=total)


def validate_reminder_delay(delay: timedelta) -> None:
    """Reject delays that are too short to be useful or too far away."""
    if delay < MIN_DURATION:
        raise TimeParseError("Reminders need to be at least 10 seconds away.")
    if delay > MAX_DURATION:
        raise TimeParseError("Reminders can be at most 365 days away.")
