from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from typing import Protocol

from fastembed import TextEmbedding
from langchain.embeddings import init_embeddings
from langchain_core.embeddings import Embeddings

from .models import Citation, PolicyAnswer


@dataclass(frozen=True)
class PolicyChunk:
    text: str
    source: str
    title: str
    section: str


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: PolicyChunk
    score: float


DEFAULT_POLICY = [
    PolicyChunk(
        "Delivered returnable items may be returned within seven calendar days.",
        "policy/returns.md",
        "Returns Policy",
        "Eligibility",
    ),
    PolicyChunk(
        "Opened hygiene products and personalized goods are non-returnable.",
        "policy/returns.md",
        "Returns Policy",
        "Exclusions",
    ),
    PolicyChunk(
        "Electronics include a twelve-month limited warranty for manufacturing defects.",
        "policy/warranty.md",
        "Electronics Warranty",
        "Coverage",
    ),
    PolicyChunk(
        "The electronics warranty excludes accidental damage, misuse, and normal wear.",
        "policy/warranty.md",
        "Electronics Warranty",
        "Exclusions",
    ),
    PolicyChunk(
        "A delayed shipment does not create an automatic cash compensation entitlement.",
        "policy/logistics.md",
        "Logistics Policy",
        "Delays",
    ),
    PolicyChunk(
        "Contact support when tracking has not updated for five business days.",
        "policy/logistics.md",
        "Logistics Policy",
        "Stalled tracking",
    ),
    PolicyChunk(
        "A refund for a returned promotional purchase uses the amount actually paid.",
        "policy/promotions.md",
        "Promotion Refunds",
        "Refund amount",
    ),
    PolicyChunk(
        "Returning one item from a bundle may reduce the refund by the retained bundle discount.",
        "policy/promotions.md",
        "Promotion Refunds",
        "Bundles",
    ),
]


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


_STOP_WORDS = {
    "about",
    "after",
    "does",
    "from",
    "have",
    "item",
    "policy",
    "purchase",
    "what",
    "when",
    "with",
}


class HashEmbedding:
    """Deterministic offline test stub. It is not a semantic production embedding."""

    def __init__(self, dimensions: int = 65536) -> None:
        self.dimensions = dimensions

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        terms = {
            term
            for term in re.findall(r"[a-z0-9]+", text.lower())
            if len(term) > 3 and term not in _STOP_WORDS
        }
        for term in terms:
            digest = hashlib.sha256(term.encode()).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


class FastEmbedProvider:
    """Local production-grade semantic embeddings without browser or API credentials."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model = TextEmbedding(
            model_name=model_name,
            cache_dir=os.getenv("FASTEMBED_CACHE_DIR", ".model-cache"),
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(value) for value in vector] for vector in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self._model.query_embed(text)))
        return [float(value) for value in vector]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


class SemanticPolicyRetriever:
    def __init__(
        self,
        embeddings: EmbeddingProvider,
        chunks: list[PolicyChunk] | None = None,
        *,
        minimum_score: float = 0.15,
    ) -> None:
        self.embeddings = embeddings
        self.chunks = chunks or DEFAULT_POLICY
        self.minimum_score = minimum_score
        self._vectors = embeddings.embed_documents([chunk.text for chunk in self.chunks])

    def retrieve(self, question: str, limit: int = 3) -> list[RetrievedChunk]:
        query = self.embeddings.embed_query(question)
        ranked = sorted(
            (
                RetrievedChunk(chunk=chunk, score=_cosine(query, vector))
                for chunk, vector in zip(self.chunks, self._vectors, strict=True)
            ),
            key=lambda result: result.score,
            reverse=True,
        )
        return [result for result in ranked if result.score >= self.minimum_score][:limit]

    def answer(self, question: str) -> PolicyAnswer:
        retrieved = self.retrieve(question)
        if not retrieved:
            return PolicyAnswer(
                answer="The policy corpus does not contain enough evidence.",
                insufficient_evidence=True,
            )
        best = retrieved[0].chunk
        return PolicyAnswer(
            answer=best.text,
            citations=[Citation(source=best.source, title=best.title, section=best.section)],
        )


class OfflinePolicyRetriever(SemanticPolicyRetriever):
    """CI-only policy retriever with the explicitly non-semantic HashEmbedding stub."""

    def __init__(self, chunks: list[PolicyChunk] | None = None) -> None:
        super().__init__(HashEmbedding(), chunks)


def production_policy_retriever(
    embedding_model: str, chunks: list[PolicyChunk] | None = None
) -> SemanticPolicyRetriever:
    """Create the production path; provider packages and credentials must be configured."""
    if not embedding_model.strip():
        raise ValueError("LLM_EMBEDDING_MODEL is required for semantic RAG")
    if embedding_model.startswith("fastembed:"):
        model_name = embedding_model.removeprefix("fastembed:")
        if not model_name:
            raise ValueError("fastembed model name is required")
        # Calibrated on the versioned v1 suite: answerable minimum 0.7200,
        # unanswerable maximum 0.5886. Keep margin on both sides.
        return SemanticPolicyRetriever(FastEmbedProvider(model_name), chunks, minimum_score=0.65)
    embeddings: Embeddings = init_embeddings(embedding_model)
    return SemanticPolicyRetriever(embeddings, chunks)
