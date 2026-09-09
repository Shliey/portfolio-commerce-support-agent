from pathlib import Path


def test_web_ci_provisions_backend_runtime_before_e2e() -> None:
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    web_job = workflow.split("  web:\n", maxsplit=1)[1]
    setup_uv = web_job.index("astral-sh/setup-uv@v5")
    sync = web_job.index("uv sync --frozen")
    e2e = web_job.index("npm run e2e")
    assert setup_uv < sync < e2e
    assert 'python-version: "3.12"' in web_job
    assert "working-directory: ." in web_job
