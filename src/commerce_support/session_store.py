from __future__ import annotations

import sqlite3
from pathlib import Path

from .models import Role


class SessionStateStore:
    """Small runtime-state store colocated with, but independent from, graph checkpoints."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS session_state (
                  user_id TEXT NOT NULL,
                  thread_id TEXT NOT NULL,
                  active_agent TEXT NOT NULL,
                  PRIMARY KEY (user_id, thread_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=30)

    def load(self, user_id: str, thread_id: str) -> Role:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT active_agent FROM session_state WHERE user_id=? AND thread_id=?",
                (user_id, thread_id),
            ).fetchone()
        return Role(row[0]) if row else Role.TRIAGE

    def save(self, user_id: str, thread_id: str, role: Role) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO session_state (user_id, thread_id, active_agent)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, thread_id)
                DO UPDATE SET active_agent=excluded.active_agent
                """,
                (user_id, thread_id, role.value),
            )
