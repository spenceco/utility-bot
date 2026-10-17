"""Poll rules (option parsing, voting, tallies) and their SQLite storage."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from enum import Enum

from .formatting import progress_bar

MIN_OPTIONS = 2
MAX_OPTIONS = 10            # keeps the buttons to two tidy rows
MAX_OPTION_LENGTH = 55      # leaves room for " · 123" inside an 80-char button label
MAX_QUESTION_LENGTH = 250   # embed titles are capped at 256 characters


class PollError(ValueError):
    """Invalid poll input. The message is shown to the user."""


class VoteResult(Enum):
    ADDED = "added"
    CHANGED = "changed"
    REMOVED = "removed"     # clicking your current choice again takes the vote back


def parse_options(raw: str) -> list[str]:
    """Split "Pizza, Tacos, Sushi" (or using | or ;) into a clean option list.

    The separator is picked by priority: "|" first, then ";", then ",". That way
    "Yes, definitely | No" keeps its comma inside an option.
    """
    separator = next((s for s in ("|", ";", ",") if s in raw), None)
    if separator is None:
        raise PollError(
            "Give at least two options separated by commas, e.g. `Pizza, Tacos, Sushi`."
        )

    options: list[str] = []
    seen: set[str] = set()
    for part in raw.split(separator):
        option = re.sub(r"\s+", " ", part).strip()
        if not option or option.casefold() in seen:
            continue  # skip blanks and duplicates
        if len(option) > MAX_OPTION_LENGTH:
            raise PollError(f"Option `{option[:20]}…` is too long (max {MAX_OPTION_LENGTH} characters).")
        seen.add(option.casefold())
        options.append(option)

    if len(options) < MIN_OPTIONS:
        raise PollError("A poll needs at least two different options.")
    if len(options) > MAX_OPTIONS:
        raise PollError(f"A poll can have at most {MAX_OPTIONS} options.")
    return options


def validate_question(question: str) -> str:
    question = question.strip()
    if not question:
        raise PollError("The poll needs a question.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise PollError(f"The question is too long (max {MAX_QUESTION_LENGTH} characters).")
    return question


@dataclass
class Poll:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    author_id: int
    question: str
    options: list[str]
    created_at: int
    closed: bool = False
    votes: dict[int, int] = field(default_factory=dict)  # user_id -> option index

    def tally(self) -> list[int]:
        counts = [0] * len(self.options)
        for option in self.votes.values():
            if 0 <= option < len(counts):
                counts[option] += 1
        return counts

    @property
    def total_votes(self) -> int:
        return len(self.votes)

    def winners(self) -> list[str]:
        """Options with the most votes (several if tied, none if no votes)."""
        counts = self.tally()
        best = max(counts, default=0)
        return [opt for opt, n in zip(self.options, counts) if n == best] if best else []

    def results_text(self, bar_width: int = 12) -> str:
        """Multi-line results block, one bar per option."""
        counts = self.tally()
        total = self.total_votes
        lines = []
        for option, count in zip(self.options, counts):
            share = count / total if total else 0.0
            noun = "vote" if count == 1 else "votes"
            lines.append(f"**{option}**\n`{progress_bar(share, bar_width)}` {count} {noun} ({share:.0%})")
        return "\n".join(lines)


class PollStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        guild_id: int,
        channel_id: int,
        author_id: int,
        question: str,
        options: list[str],
        created_at: int,
    ) -> Poll:
        cur = self._conn.execute(
            "INSERT INTO polls (guild_id, channel_id, author_id, question, options, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, author_id, question, json.dumps(options), created_at),
        )
        self._conn.commit()
        return Poll(cur.lastrowid, guild_id, channel_id, None, author_id, question, options, created_at)

    def set_message_id(self, poll_id: int, message_id: int) -> None:
        self._conn.execute("UPDATE polls SET message_id = ? WHERE id = ?", (message_id, poll_id))
        self._conn.commit()

    def get(self, poll_id: int) -> Poll | None:
        row = self._conn.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()
        if row is None:
            return None
        votes = dict(
            self._conn.execute(
                "SELECT user_id, option FROM poll_votes WHERE poll_id = ?", (poll_id,)
            ).fetchall()
        )
        return Poll(
            id=row["id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            author_id=row["author_id"],
            question=row["question"],
            options=json.loads(row["options"]),
            created_at=row["created_at"],
            closed=bool(row["closed"]),
            votes=votes,
        )

    def vote(self, poll_id: int, user_id: int, option: int) -> VoteResult:
        """Record a click. Same option twice = un-vote; another option = switch."""
        current = self._conn.execute(
            "SELECT option FROM poll_votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id)
        ).fetchone()
        if current is None:
            self._conn.execute(
                "INSERT INTO poll_votes (poll_id, user_id, option) VALUES (?, ?, ?)",
                (poll_id, user_id, option),
            )
            result = VoteResult.ADDED
        elif current["option"] == option:
            self._conn.execute(
                "DELETE FROM poll_votes WHERE poll_id = ? AND user_id = ?", (poll_id, user_id)
            )
            result = VoteResult.REMOVED
        else:
            self._conn.execute(
                "UPDATE poll_votes SET option = ? WHERE poll_id = ? AND user_id = ?",
                (option, poll_id, user_id),
            )
            result = VoteResult.CHANGED
        self._conn.commit()
        return result

    def close(self, poll_id: int) -> None:
        self._conn.execute("UPDATE polls SET closed = 1 WHERE id = ?", (poll_id,))
        self._conn.commit()
