import json

from fastapi.testclient import TestClient

from commerce_support.models import ConversationState, RequestScope, Role
from commerce_support.repository import SQLiteRepository
from commerce_support.runtime import ROLE_TOOLS, CommerceRuntime, route_message


def test_roles_have_explicit_tool_allowlists() -> None:
    assert ROLE_TOOLS[Role.TRIAGE] == frozenset()
    assert "create_approval" in ROLE_TOOLS[Role.RETURN]
    assert "create_approval" not in ROLE_TOOLS[Role.ORDER]


def test_deterministic_routing() -> None:
    assert route_message("return order-1001") == Role.RETURN
    assert route_message("what is the warranty policy?") == Role.POLICY
    assert route_message("show my orders") == Role.ORDER


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
