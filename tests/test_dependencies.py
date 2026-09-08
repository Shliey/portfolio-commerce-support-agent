from pathlib import Path
from typing import Any

import pytest

from commerce_support.config import ConfigurationError, Settings
from commerce_support.dependencies import DependencyFactories, build_dependency_graph
from commerce_support.rag import HashEmbedding
from commerce_support.repository import SQLiteRepository


def test_dependency_graph_constructs_with_all_fakes(tmp_path: Path) -> None:
    calls: list[tuple[str, object]] = []
    fake_chat = object()
    fake_checkpoint = object()
    settings = Settings(
        app_secret="test-secret-at-least-sixteen",
        business_db=tmp_path / "business.db",
        checkpoint_db=tmp_path / "checkpoints.db",
        llm_embedding_model="fake-embedding",
    )

    def repository(path: Path) -> SQLiteRepository:
        calls.append(("repository", path))
        return SQLiteRepository(path)

    def embedding(name: str) -> HashEmbedding:
        calls.append(("embedding", name))
        return HashEmbedding(dimensions=16)

    def chat(received: Settings) -> Any:
        calls.append(("chat", received.llm_model_name))
        return fake_chat

    def checkpointer(path: Path) -> Any:
        calls.append(("checkpointer", path))
        return fake_checkpoint

    graph = build_dependency_graph(
        settings,
        DependencyFactories(repository, embedding, chat, checkpointer),
    )
    assert graph.chat_model is fake_chat
    assert graph.checkpointer is fake_checkpoint
    assert isinstance(graph.embedding, HashEmbedding)
    assert [call[0] for call in calls] == ["repository", "embedding", "chat", "checkpointer"]


def test_missing_required_environment_raises_typed_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_SECRET", raising=False)
    with pytest.raises(ConfigurationError, match="APP_SECRET"):
        Settings.from_env()
