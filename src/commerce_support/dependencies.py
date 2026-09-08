from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from langchain.chat_models import init_chat_model

from .config import ConfigurationError, Settings
from .ports import BusinessRepository
from .rag import EmbeddingProvider, create_embedding_provider
from .repository import SQLiteRepository


class RepositoryFactory(Protocol):
    def __call__(self, path: Path) -> BusinessRepository: ...


class EmbeddingFactory(Protocol):
    def __call__(self, embedding_model: str) -> EmbeddingProvider: ...


class ChatFactory(Protocol):
    def __call__(self, settings: Settings) -> Any: ...


class CheckpointerFactory(Protocol):
    def __call__(self, path: Path) -> Any: ...


@dataclass(frozen=True)
class DependencyFactories:
    repository: RepositoryFactory
    embedding: EmbeddingFactory
    chat: ChatFactory
    checkpointer: CheckpointerFactory


@dataclass(frozen=True)
class DependencyGraph:
    repository: BusinessRepository
    embedding: EmbeddingProvider
    chat_model: Any
    checkpointer: Any


def create_chat_model(settings: Settings) -> Any:
    if not settings.llm_api_key:
        raise ConfigurationError("LLM_API_KEY is required for a chat model")
    options: dict[str, Any] = {
        "api_key": settings.llm_api_key,
        "temperature": settings.llm_temperature,
    }
    if settings.llm_api_base_url:
        options["base_url"] = settings.llm_api_base_url
    return init_chat_model(settings.llm_model_name, **options)


def default_factories() -> DependencyFactories:
    return DependencyFactories(
        repository=SQLiteRepository,
        embedding=create_embedding_provider,
        chat=create_chat_model,
        checkpointer=lambda path: path,
    )


def build_dependency_graph(
    settings: Settings, factories: DependencyFactories | None = None
) -> DependencyGraph:
    resolved = factories or default_factories()
    if not settings.llm_embedding_model:
        raise ConfigurationError("LLM_EMBEDDING_MODEL is required")
    return DependencyGraph(
        repository=resolved.repository(settings.business_db),
        embedding=resolved.embedding(settings.llm_embedding_model),
        chat_model=resolved.chat(settings),
        checkpointer=resolved.checkpointer(settings.checkpoint_db),
    )
