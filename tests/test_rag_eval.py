import json
from pathlib import Path

import pytest

from commerce_support.rag import HashEmbedding, production_policy_retriever
from evals.run import evaluate


def test_versioned_eval_has_at_least_thirty_cases() -> None:
    path = Path(__file__).parents[1] / "evals" / "v1" / "cases.json"
    cases = json.loads(path.read_text(encoding="utf-8"))
    assert len(cases) >= 30
    report = evaluate(cases)
    assert report.source_legality_rate == 1.0
    assert report.refusal_recall == 1.0
    assert report.cited_source_not_retrieved == 0
    assert report.policy_fabricated_without_evidence == 0
    assert not any(item["reason"] == "unsafe_non_refusal" for item in report.failures)


def test_hash_embedding_is_deterministic_and_normalized() -> None:
    embeddings = HashEmbedding()
    first = embeddings.embed_query("manufacturing warranty defect")
    assert first == embeddings.embed_query("manufacturing warranty defect")
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_production_retriever_requires_real_model_name() -> None:
    with pytest.raises(ValueError, match="LLM_EMBEDDING_MODEL"):
        production_policy_retriever("")
