from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commerce_support.api import create_app_from_env


def test_production_factory_uses_separate_databases_and_serves_web(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>deployed</h1>", encoding="utf-8")
    business = tmp_path / "business.db"
    checkpoints = tmp_path / "checkpoints.db"
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_SECRET", "production-test-secret")
    monkeypatch.setenv("BUSINESS_DB", str(business))
    monkeypatch.setenv("CHECKPOINT_DB", str(checkpoints))
    monkeypatch.setenv("WEB_DIST", str(web))

    with TestClient(create_app_from_env()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert "deployed" in client.get("/").text
        response = client.post("/login", json={"username": "demo", "password": "demo-password"})
        assert response.status_code == 200
        token = response.json()["access_token"]
        chat = client.post(
            "/chat",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "thread_id": "production-thread",
                "request_id": "production-request",
                "message": "show my orders",
            },
        )
        assert chat.status_code == 200

    assert business.exists()
    assert checkpoints.exists()
    assert checkpoints != business


def test_production_factory_requires_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_SECRET", raising=False)
    with pytest.raises(ValueError, match="APP_SECRET is required"):
        create_app_from_env()
