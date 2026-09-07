from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Citation, PolicyAnswer


@dataclass(frozen=True)
class PolicyChunk:
    text: str
    source: str
    title: str
    section: str


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
        "A delayed shipment does not create an automatic cash compensation entitlement.",
        "policy/logistics.md",
        "Logistics Policy",
        "Delays",
    ),
]


class OfflinePolicyRetriever:
    """Deterministic lexical test stub; production must inject a semantic retriever."""

    def __init__(self, chunks: list[PolicyChunk] | None = None) -> None:
        self.chunks = chunks or DEFAULT_POLICY

    def answer(self, question: str) -> PolicyAnswer:
        terms = {term for term in re.findall(r"[a-z]+", question.lower()) if len(term) > 3}
        ranked = sorted(
            (
                (len(terms & set(re.findall(r"[a-z]+", chunk.text.lower()))), chunk)
                for chunk in self.chunks
            ),
            reverse=True,
            key=lambda item: item[0],
        )
        if not ranked or ranked[0][0] == 0:
            return PolicyAnswer(
                answer="The policy corpus does not contain enough evidence.",
                insufficient_evidence=True,
            )
        chunk = ranked[0][1]
        return PolicyAnswer(
            answer=chunk.text,
            citations=[Citation(source=chunk.source, title=chunk.title, section=chunk.section)],
        )
