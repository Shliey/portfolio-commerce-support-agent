from evals.load_smoke import run_load_smoke


def test_fake_load_smoke_is_bounded_and_labeled() -> None:
    report = run_load_smoke(requests=10, threshold_ms_p95=500.0)
    assert report.success_rate == 1.0
    assert report.threshold_passed
    assert report.real_model_used is False
    assert report.environment == "local-testclient-fake-no-llm"
