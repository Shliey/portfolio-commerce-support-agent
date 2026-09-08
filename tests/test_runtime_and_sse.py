import json

from fastapi.testclient import TestClient

from commerce_support.auth import TokenService
from commerce_support.models import ConversationState, RequestScope, Role
from commerce_support.repository import SQLiteRepository
from commerce_support.runtime import ROLE_TOOLS, CommerceRuntime, route_from_current, route_message


def test_roles_have_explicit_tool_allowlists() -> None:
    assert ROLE_TOOLS[Role.TRIAGE] == frozenset()
    assert "create_approval" in ROLE_TOOLS[Role.RETURN]
    assert "create_approval" not in ROLE_TOOLS[Role.ORDER]


def test_deterministic_routing() -> None:
    assert route_message("return order-1001") == Role.RETURN
    assert route_message("what is the warranty policy?") == Role.POLICY
    assert route_message("show my orders") == Role.ORDER
    assert route_from_current("what about yesterday?", Role.ORDER) == Role.ORDER
    assert route_from_current("return this", Role.ORDER) == Role.RETURN


def test_return_stream_has_correlated_monotonic_events(repository: SQLiteRepository) -> None:
    runtime = CommerceRuntime(repository)
    state = ConversationState(
        scope=RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1"),
        message="return order-1001",
        reason="damaged",
    )
    events = list(runtime.stream(state))
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert len({event.run_id for event in events}) == 1
    assert [event.type for event in events] == [
        "handoff",
        "tool_start",
        "tool_end",
        "approval_required",
        "completed",
    ]


def test_chat_sse_and_disconnect_safe_approval(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/chat",
        headers=auth_headers,
        json={
            "thread_id": "t-1",
            "request_id": "r-1",
            "message": "return order-1001",
            "reason": "damaged",
        },
    )
    assert response.status_code == 200
    data_lines = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    events = [json.loads(line) for line in data_lines]
    approval_event = next(item for item in events if item.get("type") == "approval_required")
    approval_id = approval_event["data"]["id"]
    first = client.post(
        f"/approvals/{approval_id}/decide", headers=auth_headers, json={"approve": True}
    )
    second = client.post(
        f"/approvals/{approval_id}/decide", headers=auth_headers, json={"approve": True}
    )
    assert first.json()["ticket"]["id"] == second.json()["ticket"]["id"]

    thread = client.get("/threads/t-1", headers=auth_headers)
    assert thread.json() == {"thread_id": "t-1", "active_agent": "return", "event_count": 5}
    replay = client.get("/chat/t-1/events", headers=auth_headers)
    replay_data = [line for line in replay.text.splitlines() if line.startswith("data: ")]
    assert len(replay_data) == 5


def test_thread_replay_is_user_scoped(client: TestClient, auth_headers: dict[str, str]) -> None:
    client.post(
        "/chat",
        headers=auth_headers,
        json={"thread_id": "private", "request_id": "private-1", "message": "show orders"},
    )
    # A valid token for a different identity cannot observe the existing thread.
    attacker_headers = {
        "Authorization": f"Bearer {TokenService('test-secret-at-least-sixteen').issue('attacker')}"
    }
    assert client.get("/threads/private", headers=attacker_headers).status_code == 404
    assert client.get("/chat/private/events", headers=attacker_headers).text == ""


def test_active_agent_persists_across_runtime_restart(repository: SQLiteRepository) -> None:
    checkpoint_path = repository.path.with_name("checkpoints.db")
    scope1 = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-1")
    first = list(
        CommerceRuntime(repository, checkpoint_path).stream(
            ConversationState(scope=scope1, message="show my orders")
        )
    )
    assert first[0].data == {"from": "triage", "to": "order"}

    scope2 = RequestScope(user_id="user-1", thread_id="thread-1", request_id="request-2")
    second = list(
        CommerceRuntime(repository, checkpoint_path).stream(
            ConversationState(scope=scope2, message="what about yesterday?")
        )
    )
    assert all(item.type != "handoff" for item in second)
    assert second[-1].data["active_agent"] == "order"


def test_same_thread_id_is_isolated_between_users(repository: SQLiteRepository) -> None:
    checkpoint_path = repository.path.with_name("checkpoints.db")
    runtime = CommerceRuntime(repository, checkpoint_path)
    runtime.sessions.save("user-1", "shared-thread", Role.RETURN)
    assert runtime.sessions.load("user-1", "shared-thread") == Role.RETURN
    assert runtime.sessions.load("attacker", "shared-thread") == Role.TRIAGE
