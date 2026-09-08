from pathlib import Path

import pytest

from commerce_support.repository import SQLiteRepository


def test_repository_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    repository = SQLiteRepository(tmp_path / "rollback.db")
    with pytest.raises(RuntimeError, match="abort"):
        with repository.connection() as connection:
            connection.execute(
                "INSERT INTO users VALUES (?, ?, ?)",
                ("rollback-user", "rollback", "not-a-real-hash"),
            )
            raise RuntimeError("abort")
    with repository.connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM users WHERE id='rollback-user'"
        ).fetchone()[0]
    assert count == 0


def test_repository_releases_file_after_repeated_operations(tmp_path: Path) -> None:
    database = tmp_path / "windows lifecycle.db"
    repository = SQLiteRepository(database)
    repository.seed()
    for _ in range(20):
        assert repository.list_orders("user-1")
    renamed = tmp_path / "renamed.db"
    database.rename(renamed)
    renamed.unlink()
    assert not renamed.exists()


def test_repository_context_manager_closes_lifecycle_and_file(tmp_path: Path) -> None:
    database = tmp_path / "context managed lifecycle.db"
    with SQLiteRepository(database) as repository:
        repository.seed()
        assert repository.list_orders("user-1")
    with pytest.raises(RuntimeError, match="repository_closed"):
        repository.list_orders("user-1")
    renamed = tmp_path / "closed-context.db"
    database.rename(renamed)
    renamed.unlink()
    assert not renamed.exists()
