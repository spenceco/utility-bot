"""Small text helpers shared by several commands."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def humanize_duration(delta: timedelta, max_parts: int = 3) -> str:
    """Render a timedelta as e.g. "2 days, 3 hours, 5 minutes"."""
    seconds = int(delta.total_seconds())
    if seconds <= 0:
        return "0 seconds"
    parts: list[str] = []
    for name, size in (("day", 86400), ("hour", 3600), ("minute", 60), ("second", 1)):
        amount, seconds = divmod(seconds, size)
        if amount:
            parts.append(f"{amount} {name}{'' if amount == 1 else 's'}")
    return ", ".join(parts[:max_parts])


def progress_bar(fraction: float, width: int = 12) -> str:
    """A text bar like "█████░░░░░░░" for 0.0..1.0."""
    fraction = min(max(fraction, 0.0), 1.0)
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled)


def sparkline(values: Sequence[float]) -> str:
    """A one-line chart such as "▁▃▅█▆" (flat data gives a flat line)."""
    if not values:
        return ""
    low, high = min(values), max(values)
    if high == low:
        return _SPARK_CHARS[3] * len(values)
    scale = (len(_SPARK_CHARS) - 1) / (high - low)
    return "".join(_SPARK_CHARS[round((v - low) * scale)] for v in values)


def star_rating(rating: int | None, out_of: int = 5) -> str:
    """Show a 0-5 rating as stars, e.g. "★★★☆☆"."""
    if rating is None:
        return "Not rated"
    rating = min(max(rating, 0), out_of)
    return "★" * rating + "☆" * (out_of - rating)


def truncate(text: str, limit: int) -> str:
    """Shorten text to `limit` characters, adding an ellipsis if cut."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
