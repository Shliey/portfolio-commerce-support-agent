import sqlite3
from pathlib import Path

import pytest

from commerce_support.models import RequestScope
from commerce_support.repository import NotFound, SQLiteRepository
from commerce_support.return_workflow import ReturnWorkflow


def test_interrupt_survives_new_workflow_instance(
    repository: SQLiteRepository, tmp_path: Path
) -> None:
    checkpoint_path = tmp_path / "checkpoints.db"
    scope = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1")

    started = ReturnWorkflow(repository, checkpoint_path).start(scope, "order-1001", "damaged")
    assert "__interrupt__" in started
    approval = repository.get_approval_by_request("user-1", "request-1")
    assert approval.status == "pending"

    # A new graph and SQLite connection simulate an application restart.
    resumed = ReturnWorkflow(repository, checkpoint_path).resume(scope, True)
    assert resumed["status"] == "approved"
    assert resumed["ticket"]["request_id"] == "request-1"


def test_cross_user_scope_cannot_find_pending_approval(
    repository: SQLiteRepository, tmp_path: Path
) -> None:
    scope = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1")
    ReturnWorkflow(repository, tmp_path / "checkpoints.db").start(scope, "order-1001", "damaged")
    with pytest.raises(NotFound):
        repository.get_approval_by_request("attacker", "request-1")


def test_resume_replay_returns_same_ticket(repository: SQLiteRepository, tmp_path: Path) -> None:
    workflow = ReturnWorkflow(repository, tmp_path / "checkpoints.db")
    scope = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1")
    workflow.start(scope, "order-1001", "damaged")
    first = workflow.resume(scope, True)
    second = workflow.resume(scope, True)
    assert first["ticket"]["id"] == second["ticket"]["id"]


def test_business_and_checkpoint_schemas_are_separate(
    repository: SQLiteRepository, tmp_path: Path
) -> None:
    checkpoint_path = tmp_path / "checkpoints.db"
    scope = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1")
    ReturnWorkflow(repository, checkpoint_path).start(scope, "order-1001", "damaged")

    with sqlite3.connect(repository.path) as business:
        business_tables = {
            row[0] for row in business.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    with sqlite3.connect(checkpoint_path) as checkpoints:
        checkpoint_tables = {
            row[0]
            for row in checkpoints.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "tickets" in business_tables
    assert "checkpoints" not in business_tables
    assert "checkpoints" in checkpoint_tables
    assert "tickets" not in checkpoint_tables
