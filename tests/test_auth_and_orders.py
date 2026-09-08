from fastapi.testclient import TestClient

from commerce_support.auth import AuthenticationError, TokenService
from commerce_support.repository import SQLiteRepository


def test_login_and_owner_can_read_order(client: TestClient, auth_headers: dict[str, str]) -> None:
    assert client.get("/health").json() == {"status": "ok"}
    response = client.get("/orders/order-1001", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["user_id"] == "user-1"
    logistics = client.get("/orders/order-1001/logistics", headers=auth_headers)
    assert logistics.status_code == 200
    assert logistics.json() == {
        "order_id": "order-1001",
        "status": "delivered",
        "carrier": "Demo Express",
        "tracking_number": "DEMO-1001",
        "delivered_at": response.json()["delivered_at"],
    }


def test_invalid_credentials_and_token_are_rejected(client: TestClient) -> None:
    wrong = client.post("/login", json={"username": "demo", "password": "wrong"})
    unknown = client.post("/login", json={"username": "unknown", "password": "wrong"})
    assert (wrong.status_code, wrong.json()) == (unknown.status_code, unknown.json())
    assert client.get("/orders", headers={"Authorization": "Bearer tampered"}).status_code == 401


def test_seeded_password_is_hashed(repository: SQLiteRepository) -> None:
    with repository.connection() as connection:
        stored = connection.execute(
            "SELECT password_hash FROM users WHERE username='demo'"
        ).fetchone()["password_hash"]
    assert stored != "demo-password"
    assert "demo-password" not in stored
    assert repository.authenticate("demo", "demo-password") is not None


def test_expired_token_is_rejected() -> None:
    service = TokenService("test-secret-at-least-sixteen", ttl_seconds=-1)
    try:
        service.verify(service.issue("user-1"))
    except AuthenticationError:
        pass
    else:
        raise AssertionError("expired token was accepted")


def test_missing_and_foreign_orders_share_external_error(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/orders/unknown", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "order_not_found"
    logistics = client.get("/orders/unknown/logistics", headers=auth_headers)
    assert (logistics.status_code, logistics.json()) == (response.status_code, response.json())


def test_openapi_lists_order_and_logistics_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    paths = schema["paths"]
    assert "/orders" in paths
    assert "/orders/{order_id}" in paths
    assert "/orders/{order_id}/logistics" in paths
    assert paths["/orders/{order_id}"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("/Order")
    assert paths["/orders/{order_id}"]["get"]["responses"]["404"]["description"] == (
        "order_not_found"
    )
    assert paths["/login"]["post"]["responses"]["401"]["description"] == ("invalid_credentials")
