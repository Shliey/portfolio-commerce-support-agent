from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from commerce_support.api import create_app
from commerce_support.repository import SQLiteRepository


@pytest.fixture
def repository(tmp_path: Path) -> SQLiteRepository:
    repo = SQLiteRepository(tmp_path / "business.db")
    repo.seed()
    return repo


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(tmp_path / "business.db", "test-secret-at-least-sixteen"))


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post("/login", json={"username": "demo", "password": "demo-password"})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
