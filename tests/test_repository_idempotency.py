import sqlite3

import pytest

from commerce_support.eligibility import evaluate_return
from commerce_support.models import RequestScope
from commerce_support.repository import IdempotencyConflict, SQLiteRepository


def test_same_request_creates_one_approval(repository: SQLiteRepository) -> None:
    order = repository.get_order("user-1", "order-1001")
    scope = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1")
    draft = evaluate_return(order, "damaged")
    first = repository.create_approval(scope, draft)
    second = repository.create_approval(scope, draft)
    assert first.id == second.id
    assert len(repository.list_approvals("user-1")) == 1


def test_request_reuse_with_changed_parameters_conflicts(repository: SQLiteRepository) -> None:
    order = repository.get_order("user-1", "order-1001")
    scope = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1")
    repository.create_approval(scope, evaluate_return(order, "damaged"))
    with pytest.raises(IdempotencyConflict):
        repository.create_approval(scope, evaluate_return(order, "wrong size"))


def test_approval_retry_writes_exactly_one_ticket(repository: SQLiteRepository) -> None:
    order = repository.get_order("user-1", "order-1001")
    scope = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1")
    approval = repository.create_approval(scope, evaluate_return(order, "damaged"))
    first = repository.decide_approval("user-1", approval.id, True)
    second = repository.decide_approval("user-1", approval.id, True)
    assert first is not None and second is not None
    assert first.id == second.id


def test_database_rejects_duplicate_ticket_request_id(repository: SQLiteRepository) -> None:
    values = ("ticket-direct-1", "direct-request", "user-1", "order-1001", "reason", "now")
    with repository.connection() as connection:
        connection.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)", values)
    duplicate = ("ticket-direct-2", *values[1:])
    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        with repository.connection() as connection:
            connection.execute("INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?)", duplicate)
    assert repository.count_tickets("direct-request") == 1
