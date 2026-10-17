"""Counts how often each slash command is used (kept across restarts)."""

from __future__ import annotations

import sqlite3


class UsageStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record(self, command: str) -> None:
        self._conn.execute(
            "INSERT INTO command_usage (command, uses) VALUES (?, 1)"
            " ON CONFLICT(command) DO UPDATE SET uses = uses + 1",
            (command,),
        )
        self._conn.commit()

    def total(self) -> int:
        return self._conn.execute("SELECT COALESCE(SUM(uses), 0) FROM command_usage").fetchone()[0]

    def top(self, limit: int = 5) -> list[tuple[str, int]]:
        rows = self._conn.execute(
            "SELECT command, uses FROM command_usage ORDER BY uses DESC, command LIMIT ?", (limit,)
        ).fetchall()
        return [(r["command"], r["uses"]) for r in rows]
