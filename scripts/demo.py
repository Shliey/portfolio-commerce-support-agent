from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from commerce_support.api import create_app


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        client = TestClient(create_app(Path(directory) / "demo.db", "demo-secret-at-least-sixteen"))
        token = client.post(
            "/login", json={"username": "demo", "password": "demo-password"}
        ).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        print("1. Orders", json.dumps(client.get("/orders", headers=headers).json(), indent=2))
        stream = client.post(
            "/chat",
            headers=headers,
            json={
                "thread_id": "demo-thread",
                "request_id": "demo-return-1",
                "message": "return order-1001",
                "reason": "ear cup arrived damaged",
            },
        )
        print("2. Agent stream\n", stream.text)
        approval_id = client.get("/approvals", headers=headers).json()[0]["id"]
        result = client.post(
            f"/approvals/{approval_id}/decide", headers=headers, json={"approve": True}
        ).json()
        print("3. Approved ticket", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
