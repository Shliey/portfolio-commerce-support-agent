from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from .models import Approval, Order, OrderItem, OrderStatus, RequestScope, ReturnDraft, Ticket, User


class NotFound(Exception):
    """Externally indistinguishable missing-or-forbidden record."""


class IdempotencyConflict(Exception):
    """A request id was reused with different business parameters."""


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, status TEXT NOT NULL,
  delivered_at TEXT, items_json TEXT NOT NULL,
  FOREIGN KEY(user_id) REFERENCES users(id)
);
CREATE TABLE IF NOT EXISTS approvals (
  id TEXT PRIMARY KEY, user_id TEXT NOT NULL, thread_id TEXT NOT NULL,
  request_id TEXT UNIQUE NOT NULL, order_id TEXT NOT NULL, reason TEXT NOT NULL,
  eligible INTEGER NOT NULL, reasons_json TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, user_id TEXT NOT NULL,
  order_id TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


class SQLiteRepository:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        with self.connection() as connection:
            connection.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def seed(self) -> None:
        items = [
            OrderItem(
                sku="SKU-100",
                name="Noise-cancelling headphones",
                quantity=1,
                unit_price_cents=12900,
            )
        ]
        with self.connection() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO users VALUES (?, ?, ?)",
                ("user-1", "demo", "demo-password"),
            )
            connection.execute(
                "INSERT OR IGNORE INTO orders VALUES (?, ?, ?, ?, ?)",
                (
                    "order-1001",
                    "user-1",
                    "delivered",
                    datetime.now(UTC).isoformat(),
                    json.dumps([item.model_dump(mode="json") for item in items]),
                ),
            )

    def authenticate(self, username: str, password: str) -> User | None:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT id, username FROM users WHERE username=? AND password_hash=?",
                (username, password),
            ).fetchone()
        return User.model_validate(dict(row)) if row else None

    def list_orders(self, user_id: str) -> list[Order]:
        with self.connection() as connection:
            rows = connection.execute("SELECT * FROM orders WHERE user_id=?", (user_id,)).fetchall()
        return [self._order(row) for row in rows]

    def get_order(self, user_id: str, order_id: str) -> Order:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, user_id)
            ).fetchone()
        if not row:
            raise NotFound("order_not_found")
        return self._order(row)

    @staticmethod
    def _order(row: sqlite3.Row) -> Order:
        return Order(
            id=row["id"],
            user_id=row["user_id"],
            status=OrderStatus(row["status"]),
            delivered_at=row["delivered_at"],
            items=[OrderItem.model_validate(item) for item in json.loads(row["items_json"])],
        )

    def create_approval(self, scope: RequestScope, draft: ReturnDraft) -> Approval:
        approval = Approval(id=f"approval-{uuid.uuid4().hex[:10]}", scope=scope, draft=draft)
        with self._write_lock, self.connection() as connection:
            existing = connection.execute(
                "SELECT * FROM approvals WHERE request_id=?", (scope.request_id,)
            ).fetchone()
            if existing:
                if (existing["user_id"], existing["order_id"], existing["reason"]) != (
                    scope.user_id,
                    draft.order_id,
                    draft.reason,
                ):
                    raise IdempotencyConflict("idempotency_conflict")
                return self._approval(existing)
            connection.execute(
                "INSERT INTO approvals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    approval.id,
                    scope.user_id,
                    scope.thread_id,
                    scope.request_id,
                    draft.order_id,
                    draft.reason,
                    int(draft.eligible),
                    json.dumps(draft.reasons),
                    approval.status,
                    approval.created_at.isoformat(),
                ),
            )
        return approval

    def list_approvals(self, user_id: str) -> list[Approval]:
        with self.connection() as connection:
            rows = connection.execute(
                "SELECT * FROM approvals WHERE user_id=? ORDER BY created_at", (user_id,)
            ).fetchall()
        return [self._approval(row) for row in rows]

    def get_approval(self, user_id: str, approval_id: str) -> Approval:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE id=? AND user_id=?", (approval_id, user_id)
            ).fetchone()
        if not row:
            raise NotFound("approval_not_found")
        return self._approval(row)

    def get_approval_by_request(self, user_id: str, request_id: str) -> Approval:
        with self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE request_id=? AND user_id=?", (request_id, user_id)
            ).fetchone()
        if not row:
            raise NotFound("approval_not_found")
        return self._approval(row)

    def decide_approval(self, user_id: str, approval_id: str, approve: bool) -> Ticket | None:
        with self._write_lock, self.connection() as connection:
            row = connection.execute(
                "SELECT * FROM approvals WHERE id=? AND user_id=?", (approval_id, user_id)
            ).fetchone()
            if not row:
                raise NotFound("approval_not_found")
            desired = "approved" if approve else "rejected"
            if row["status"] not in ("pending", desired):
                raise IdempotencyConflict("approval_already_decided")
            connection.execute("UPDATE approvals SET status=? WHERE id=?", (desired, approval_id))
            if not approve:
                return None
            existing = connection.execute(
                "SELECT * FROM tickets WHERE request_id=?", (row["request_id"],)
            ).fetchone()
            if existing:
                return self._ticket(existing)
            ticket = Ticket(
                id=f"ticket-{uuid.uuid4().hex[:10]}",
                request_id=row["request_id"],
                user_id=user_id,
                order_id=row["order_id"],
                reason=row["reason"],
                created_at=datetime.now(UTC),
            )
            connection.execute(
                "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)",
                (
                    ticket.id,
                    ticket.request_id,
                    ticket.user_id,
                    ticket.order_id,
                    ticket.reason,
                    ticket.created_at.isoformat(),
                ),
            )
            return ticket

    @staticmethod
    def _approval(row: sqlite3.Row) -> Approval:
        return Approval(
            id=row["id"],
            scope=RequestScope(
                user_id=row["user_id"], thread_id=row["thread_id"], request_id=row["request_id"]
            ),
            draft=ReturnDraft(
                order_id=row["order_id"],
                reason=row["reason"],
                eligible=bool(row["eligible"]),
                reasons=json.loads(row["reasons_json"]),
            ),
            status=row["status"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _ticket(row: sqlite3.Row) -> Ticket:
        return Ticket(
            id=row["id"],
            request_id=row["request_id"],
            user_id=row["user_id"],
            order_id=row["order_id"],
            reason=row["reason"],
            created_at=row["created_at"],
        )
