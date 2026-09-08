from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .models import Role, StreamEvent


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
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS stream_events (
                  event_index INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id TEXT NOT NULL,
                  thread_id TEXT NOT NULL,
                  run_id TEXT NOT NULL,
                  seq INTEGER NOT NULL,
                  payload_json TEXT NOT NULL,
                  UNIQUE (user_id, thread_id, run_id, seq)
                )
                """
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

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

    def get(self, user_id: str, thread_id: str) -> Role | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT active_agent FROM session_state WHERE user_id=? AND thread_id=?",
                (user_id, thread_id),
            ).fetchone()
        return Role(row[0]) if row else None

    def append_event(self, event: StreamEvent) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO stream_events
                  (user_id, thread_id, run_id, seq, payload_json)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    event.user_id,
                    event.thread_id,
                    event.run_id,
                    event.seq,
                    event.model_dump_json(),
                ),
            )

    def list_events(self, user_id: str, thread_id: str) -> list[StreamEvent]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT payload_json FROM stream_events
                WHERE user_id=? AND thread_id=? ORDER BY event_index
                """,
                (user_id, thread_id),
            ).fetchall()
        return [StreamEvent.model_validate(json.loads(row[0])) for row in rows]
