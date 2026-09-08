from dataclasses import dataclass
from typing import Any

import pytest

from evals.model_smoke import evaluate_model, require_real_model_credentials


@dataclass
class FakeResponse:
    content: str
    usage_metadata: dict[str, int]


class FakeRoutingModel:
    def invoke(self, value: Any) -> FakeResponse:
        message = str(value[-1][1]).lower()
        if "return" in message or "refund" in message:
            label = "return"
        elif "order" in message or "shipment" in message or "purchases" in message:
            label = "order"
        elif "days" in message or "warranty" in message:
            label = "policy"
        else:
            label = "triage"
        return FakeResponse(label, {"input_tokens": 10, "output_tokens": 1})


def test_model_runner_records_provenance_usage_latency_and_failures() -> None:
    cases = [
        {"id": "one", "message": "return this", "expected": "return"},
        {"id": "two", "message": "tell me a joke", "expected": "triage"},
    ]
    report = evaluate_model(
        FakeRoutingModel(), cases, model_id="fake-routing", real_model_used=False
    )
    assert report.sample_size == 2
    assert report.success_rate == 1.0
    assert report.input_tokens == 20
    assert report.output_tokens == 2
    assert report.latency_ms_p50 >= 0
    assert not report.real_model_used


def test_real_model_runner_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RUN_REAL_MODEL_EVAL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="RUN_REAL_MODEL_EVAL=1"):
        require_real_model_credentials()


def test_real_model_runner_requires_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RUN_REAL_MODEL_EVAL", "1")
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="API_KEY"):
        require_real_model_credentials()
