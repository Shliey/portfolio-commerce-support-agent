from fastapi.testclient import TestClient


def test_login_and_owner_can_read_order(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/orders/order-1001", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"


def test_invalid_credentials_and_token_are_rejected(client: TestClient) -> None:
    response = client.post("/login", json={"username": "demo", "password": "wrong"})
    assert response.status_code == 401
    assert client.get("/orders", headers={"Authorization": "Bearer tampered"}).status_code == 401


def test_missing_and_foreign_orders_share_external_error(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/orders/unknown", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "order_not_found"
