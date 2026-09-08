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


def test_token_is_opaque_and_contains_no_identity_or_password() -> None:
    service = TokenService("test-secret-at-least-sixteen")
    token = service.issue("user-1")
    assert "user-1" not in token
    assert "demo" not in token
    assert "password" not in token
    assert service.verify(token) == "user-1"


def test_missing_and_foreign_orders_share_external_error(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    repository = client.app.state.repository
    with repository.connection() as connection:
        connection.execute(
            "INSERT INTO users VALUES (?, ?, ?)",
            ("user-2", "other", "irrelevant-hash"),
        )
        connection.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            ("order-foreign", "user-2", "delivered", None, "[]"),
        )
    missing = client.get("/orders/unknown", headers=auth_headers)
    foreign = client.get("/orders/order-foreign", headers=auth_headers)
    assert (missing.status_code, missing.json()) == (foreign.status_code, foreign.json())
    assert missing.status_code == 404
    assert missing.json()["detail"]["code"] == "order_not_found"
    missing_logistics = client.get("/orders/unknown/logistics", headers=auth_headers)
    foreign_logistics = client.get("/orders/order-foreign/logistics", headers=auth_headers)
    assert (missing_logistics.status_code, missing_logistics.json()) == (
        foreign_logistics.status_code,
        foreign_logistics.json(),
    )
    assert (missing_logistics.status_code, missing_logistics.json()) == (
        missing.status_code,
        missing.json(),
    )


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
    logistics_responses = paths["/orders/{order_id}/logistics"]["get"]["responses"]
    assert logistics_responses["409"]["description"] == "order_status_unavailable"
    assert logistics_responses["503"]["description"] == "logistics_unavailable"


def test_logistics_failures_have_stable_codes(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    repository = client.app.state.repository
    with repository.connection() as connection:
        connection.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            ("order-placed", "user-1", "placed", None, "[]"),
        )
        connection.execute(
            "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
            ("order-shipped", "user-1", "shipped", None, "[]"),
        )
    placed = client.get("/orders/order-placed/logistics", headers=auth_headers)
    shipped = client.get("/orders/order-shipped/logistics", headers=auth_headers)
    assert (placed.status_code, placed.json()["detail"]["code"]) == (
        409,
        "order_status_unavailable",
    )
    assert (shipped.status_code, shipped.json()["detail"]["code"]) == (
        503,
        "logistics_unavailable",
    )
