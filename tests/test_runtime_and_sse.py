import json

from fastapi.testclient import TestClient

from commerce_support.auth import TokenService
from commerce_support.models import ConversationState, RequestScope, Role
from commerce_support.repository import SQLiteRepository
from commerce_support.runtime import (
    ROLE_TOOLS,
    CommerceRuntime,
    RoutingDecision,
    ToolNotAllowed,
    require_allowed_tool,
    route_from_current,
    route_message,
)


def test_roles_have_explicit_tool_allowlists() -> None:
    assert ROLE_TOOLS[Role.TRIAGE] == frozenset()
    assert "create_approval" in ROLE_TOOLS[Role.RETURN]
    assert "create_approval" not in ROLE_TOOLS[Role.ORDER]


def test_out_of_allowlist_tool_is_rejected_before_execution() -> None:
    entries: list[dict[str, object]] = []
    try:
        require_allowed_tool(Role.ORDER, "create_approval", entries.append, {"run_id": "run-1"})
    except ToolNotAllowed as error:
        assert str(error) == "tool_not_allowed"
    else:
        raise AssertionError("out-of-allowlist tool was accepted")
    assert entries == [
        {
            "run_id": "run-1",
            "call_type": "tool_authorization",
            "role": "order",
            "name": "create_approval",
            "status": "rejected",
        }
    ]


def test_deterministic_routing() -> None:
    assert route_message("return order-1001") == Role.RETURN
    assert route_message("what is the warranty policy?") == Role.POLICY
    assert route_message("show my orders") == Role.ORDER
    assert route_from_current("what about yesterday?", Role.ORDER) == Role.ORDER
    assert route_from_current("return this", Role.ORDER) == Role.RETURN


def test_injected_router_uses_structured_decision(repository: SQLiteRepository) -> None:
    class FakeRouter:
        def route(self, message: str, current: Role) -> RoutingDecision:
            assert message == "please help"
            assert current == Role.TRIAGE
            return RoutingDecision(role=Role.RETURN, order_id="order-1001", reason="damaged")

    events = list(
        CommerceRuntime(repository, intent_router=FakeRouter()).stream(
            ConversationState(
                scope=RequestScope(user_id="user-1", thread_id="structured", request_id="route-1"),
                message="please help",
            )
        )
    )
    approval = next(event for event in events if event.type == "approval_required")
    assert approval.data["draft"]["order_id"] == "order-1001"
    assert approval.data["draft"]["reason"] == "damaged"


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


def test_runtime_tool_calls_emit_correlated_audit_entries(repository: SQLiteRepository) -> None:
    entries: list[dict[str, object]] = []
    runtime = CommerceRuntime(repository, audit_sink=entries.append)
    state = ConversationState(
        scope=RequestScope(user_id="user-1", thread_id="audit-thread", request_id="audit-1"),
        message="show my orders",
    )
    list(runtime.stream(state))
    assert len(entries) == 1
    assert entries[0]["name"] == "list_orders"
    assert entries[0]["user_id"] == "user-1"
    assert entries[0]["thread_id"] == "audit-thread"
    assert str(entries[0]["run_id"]).startswith("run-")


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


def test_sse_error_is_correlated_sanitized_and_replayable(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/chat",
        headers=auth_headers,
        json={
            "thread_id": "error-thread",
            "request_id": "error-request",
            "message": "return order-9999",
        },
    )
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    error = events[-1]
    assert error["type"] == "error"
    assert error["thread_id"] == "error-thread"
    assert error["user_id"] == "user-1"
    assert error["seq"] == 3
    assert error["data"] == {"code": "order_not_found"}
    assert "sqlite" not in response.text.lower()
    replay = client.get("/chat/error-thread/events", headers=auth_headers)
    assert '"type":"error"' in replay.text


def test_step_limit_stops_before_tool_execution_and_emits_terminal_event(
    repository: SQLiteRepository,
) -> None:
    entries: list[dict[str, object]] = []
    runtime = CommerceRuntime(repository, audit_sink=entries.append, max_steps=1)
    state = ConversationState(
        scope=RequestScope(user_id="user-1", thread_id="step-limit", request_id="limit-1"),
        message="show orders",
    )
    frames = "".join(runtime.sse(state))
    assert "event: limit_exceeded" in frames
    assert '"code": "step_limit_exceeded"' in frames
    assert entries == []
    replay = runtime.sessions.list_events("user-1", "step-limit")
    assert [event.type for event in replay] == ["handoff", "limit_exceeded"]


def test_tool_limit_emits_limit_event(repository: SQLiteRepository) -> None:
    runtime = CommerceRuntime(repository, max_tool_calls=0)
    state = ConversationState(
        scope=RequestScope(user_id="user-1", thread_id="tool-limit", request_id="limit-2"),
        message="show orders",
    )
    frames = "".join(runtime.sse(state))
    assert "event: limit_exceeded" in frames
    assert '"code": "tool_limit_exceeded"' in frames


def test_openapi_documents_all_agent_endpoints_and_sse(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    for path in (
        "/chat",
        "/chat/{thread_id}/events",
        "/approvals",
        "/approvals/{approval_id}/decide",
        "/threads/{thread_id}",
    ):
        assert path in paths
    assert "text/event-stream" in paths["/chat"]["post"]["responses"]["200"]["content"]
    decide_responses = paths["/approvals/{approval_id}/decide"]["post"]["responses"]
    assert decide_responses["409"]["description"] == "idempotency_conflict"


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


def test_session_store_releases_checkpoint_file_on_windows(repository: SQLiteRepository) -> None:
    checkpoint_path = repository.path.with_name("deletable-checkpoints.db")
    runtime = CommerceRuntime(repository, checkpoint_path)
    list(
        runtime.stream(
            ConversationState(
                scope=RequestScope(
                    user_id="user-1", thread_id="cleanup-thread", request_id="cleanup-request"
                ),
                message="show orders",
            )
        )
    )
    checkpoint_path.unlink()
    assert not checkpoint_path.exists()
