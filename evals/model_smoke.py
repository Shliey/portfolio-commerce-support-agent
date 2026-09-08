from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

from langchain.chat_models import init_chat_model

PROMPT_VERSION = "routing-v1"
SYSTEM = """Classify a commerce support request. Return exactly one lowercase label:
order, return, policy, or triage. Use triage for unrelated or unclear requests."""


class Invokable(Protocol):
    def invoke(self, value: Any) -> Any: ...


@dataclass(frozen=True)
class ModelEvalReport:
    suite_version: str
    prompt_version: str
    sample_size: int
    model_id: str
    real_model_used: bool
    success_rate: float
    latency_ms_p50: float
    latency_ms_p95: float
    input_tokens: int
    output_tokens: int
    failures: list[dict[str, str]]


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * fraction)))
    return ordered[index]


def evaluate_model(
    model: Invokable,
    cases: list[dict[str, str]],
    *,
    model_id: str,
    real_model_used: bool,
) -> ModelEvalReport:
    if not cases:
        raise ValueError("model evaluation requires at least one case")
    latencies: list[float] = []
    failures: list[dict[str, str]] = []
    input_tokens = 0
    output_tokens = 0
    for case in cases:
        started = time.perf_counter()
        response = model.invoke([("system", SYSTEM), ("human", case["message"])])
        latencies.append((time.perf_counter() - started) * 1000)
        content = str(response.content).strip().lower()
        if content != case["expected"]:
            failures.append({"id": case["id"], "expected": case["expected"], "actual": content})
        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens += int(usage.get("input_tokens", 0))
        output_tokens += int(usage.get("output_tokens", 0))
    return ModelEvalReport(
        suite_version="model-v1",
        prompt_version=PROMPT_VERSION,
        sample_size=len(cases),
        model_id=model_id,
        real_model_used=real_model_used,
        success_rate=(len(cases) - len(failures)) / len(cases),
        latency_ms_p50=statistics.median(latencies),
        latency_ms_p95=_percentile(latencies, 0.95),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        failures=failures,
    )


def require_real_model_credentials() -> tuple[str, str]:
    if os.getenv("RUN_REAL_MODEL_EVAL") != "1":
        raise RuntimeError("RUN_REAL_MODEL_EVAL=1 is required; default CI must not call a model")
    model_id = os.getenv("LLM_MODEL_NAME", "anthropic:claude-sonnet-4-5")
    api_key = os.getenv("LLM_API_KEY", "") or os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("LLM_API_KEY or ANTHROPIC_API_KEY is required")
    return model_id, api_key


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("artifacts/model-eval-v1.json"))
    args = parser.parse_args()
    try:
        model_id, api_key = require_real_model_credentials()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    cases = json.loads(
        (Path(__file__).parent / "model_v1" / "cases.json").read_text(encoding="utf-8")
    )
    model = init_chat_model(model_id, api_key=api_key, temperature=0, max_tokens=8)
    report = evaluate_model(model, cases, model_id=model_id, real_model_used=True)
    rendered = json.dumps(asdict(report), ensure_ascii=False, indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
