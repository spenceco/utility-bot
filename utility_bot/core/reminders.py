"""Storage for reminders. Because they live in SQLite they survive restarts."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

MAX_ACTIVE_PER_USER = 25
MAX_MESSAGE_LENGTH = 1000


@dataclass(frozen=True)
class Reminder:
    id: int
    user_id: int
    channel_id: int
    guild_id: int | None
    message: str
    created_at: int
    due_at: int

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> Reminder:
        return cls(**{key: row[key] for key in row.keys()})


class ReminderStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(
        self,
        *,
        user_id: int,
        channel_id: int,
        guild_id: int | None,
        message: str,
        created_at: int,
        due_at: int,
    ) -> Reminder:
        cur = self._conn.execute(
            "INSERT INTO reminders (user_id, channel_id, guild_id, message, created_at, due_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, channel_id, guild_id, message, created_at, due_at),
        )
        self._conn.commit()
        return Reminder(cur.lastrowid, user_id, channel_id, guild_id, message, created_at, due_at)

    def due(self, now: int, limit: int = 50) -> list[Reminder]:
        """Reminders whose time has come (oldest first)."""
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE due_at <= ? ORDER BY due_at LIMIT ?", (now, limit)
        ).fetchall()
        return [Reminder.from_row(r) for r in rows]

    def for_user(self, user_id: int) -> list[Reminder]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE user_id = ? ORDER BY due_at", (user_id,)
        ).fetchall()
        return [Reminder.from_row(r) for r in rows]

    def count_for_user(self, user_id: int) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM reminders WHERE user_id = ?", (user_id,)
        ).fetchone()[0]

    def count_pending(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM reminders").fetchone()[0]

    def delete(self, reminder_id: int) -> None:
        self._conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        self._conn.commit()

    def cancel(self, reminder_id: int, user_id: int) -> bool:
        """Delete a reminder only if it belongs to this user. True if removed."""
        cur = self._conn.execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?", (reminder_id, user_id)
        )
        self._conn.commit()
        return cur.rowcount > 0
