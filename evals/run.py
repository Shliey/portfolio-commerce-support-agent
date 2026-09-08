from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from commerce_support.rag import (
    OfflinePolicyRetriever,
    SemanticPolicyRetriever,
    production_policy_retriever,
)


@dataclass(frozen=True)
class EvalReport:
    suite_version: str
    sample_size: int
    environment: str
    embedding: str
    real_model_used: bool
    hit_at_1: float
    hit_at_3: float
    mrr: float
    source_legality_rate: float
    refusal_recall: float
    cited_source_not_retrieved: int
    policy_fabricated_without_evidence: int
    failures: list[dict[str, Any]]


def evaluate(
    cases: list[dict[str, Any]],
    retriever: SemanticPolicyRetriever | None = None,
    *,
    environment: str = "offline-ci",
    embedding: str = "HashEmbedding test stub (non-semantic)",
) -> EvalReport:
    retriever = retriever or OfflinePolicyRetriever()
    hits1 = 0
    hits3 = 0
    reciprocal_rank = 0.0
    legal = 0
    refusals = 0
    unanswerable = 0
    failures: list[dict[str, Any]] = []
    illegal_citations = 0
    fabricated_policies = 0

    for case in cases:
        retrieved = retriever.retrieve(case["question"], limit=3)
        answer = retriever.answer(case["question"])
        sources = [item.chunk.source for item in retrieved]
        cited = {citation.source for citation in answer.citations}
        if cited.issubset(set(sources)):
            legal += 1
        else:
            illegal_citations += 1
        if not case["answerable"]:
            unanswerable += 1
            if answer.insufficient_evidence and not answer.citations:
                refusals += 1
            else:
                fabricated_policies += 1
                failures.append({"id": case["id"], "reason": "unsafe_non_refusal"})
            continue

        expected = case["expected_source"]
        if sources and sources[0] == expected:
            hits1 += 1
        if expected in sources:
            hits3 += 1
            reciprocal_rank += 1.0 / (sources.index(expected) + 1)
        else:
            failures.append({"id": case["id"], "reason": "source_not_retrieved"})

    answerable = len(cases) - unanswerable
    return EvalReport(
        suite_version="v1",
        sample_size=len(cases),
        environment=environment,
        embedding=embedding,
        real_model_used=False,
        hit_at_1=hits1 / answerable,
        hit_at_3=hits3 / answerable,
        mrr=reciprocal_rank / answerable,
        source_legality_rate=legal / len(cases),
        refusal_recall=refusals / unanswerable,
        cited_source_not_retrieved=illegal_citations,
        policy_fabricated_without_evidence=fabricated_policies,
        failures=failures,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="v1", choices=["v1"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--embedding", choices=["hash", "fastembed"], default="hash")
    args = parser.parse_args()
    cases_path = Path(__file__).parent / args.suite / "cases.json"
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    if args.embedding == "fastembed":
        model = "BAAI/bge-small-en-v1.5"
        retriever = production_policy_retriever(f"fastembed:{model}")
        report = evaluate(
            cases,
            retriever,
            environment="local-semantic",
            embedding=f"fastembed:{model}",
        )
    else:
        report = evaluate(cases)
    rendered = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
