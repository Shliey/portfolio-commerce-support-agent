from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from fastapi.testclient import TestClient

from commerce_support.api import create_app


@dataclass(frozen=True)
class LoadSmokeReport:
    environment: str
    real_model_used: bool
    endpoint: str
    requests: int
    successes: int
    success_rate: float
    latency_ms_p50: float
    latency_ms_p95: float
    latency_ms_max: float
    threshold_ms_p95: float
    threshold_passed: bool


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((len(ordered) - 1) * fraction))
    return ordered[index]


def run_load_smoke(requests: int = 100, threshold_ms_p95: float = 250.0) -> LoadSmokeReport:
    if requests < 1:
        raise ValueError("requests must be positive")
    latencies: list[float] = []
    successes = 0
    with tempfile.TemporaryDirectory() as directory:
        with TestClient(
            create_app(
                Path(directory) / "business.db",
                "load-smoke-secret-123",
                checkpoint_path=Path(directory) / "checkpoints.db",
            )
        ) as client:
            login = client.post("/login", json={"username": "demo", "password": "demo-password"})
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            for _ in range(requests):
                started = time.perf_counter()
                response = client.get("/orders", headers=headers)
                latencies.append((time.perf_counter() - started) * 1000)
                successes += int(response.status_code == 200)
    p95 = percentile(latencies, 0.95)
    return LoadSmokeReport(
        environment="local-testclient-fake-no-llm",
        real_model_used=False,
        endpoint="GET /orders",
        requests=requests,
        successes=successes,
        success_rate=successes / requests,
        latency_ms_p50=round(statistics.median(latencies), 3),
        latency_ms_p95=round(p95, 3),
        latency_ms_max=round(max(latencies), 3),
        threshold_ms_p95=threshold_ms_p95,
        threshold_passed=p95 <= threshold_ms_p95,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--threshold-ms-p95", type=float, default=250.0)
    parser.add_argument("--output", type=Path, default=Path("artifacts/load-smoke.json"))
    args = parser.parse_args()
    report = run_load_smoke(args.requests, args.threshold_ms_p95)
    rendered = json.dumps(asdict(report), indent=2)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    if not report.threshold_passed or report.success_rate != 1.0:
        raise SystemExit("load smoke threshold failed")


if __name__ == "__main__":
    main()
