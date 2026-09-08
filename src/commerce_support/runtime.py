from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from .eligibility import evaluate_return
from .models import ConversationState, EventType, Role, StreamEvent
from .rag import OfflinePolicyRetriever
from .repository import SQLiteRepository
from .return_workflow import ReturnWorkflow
from .session_store import SessionStateStore

ROLE_TOOLS: dict[Role, frozenset[str]] = {
    Role.TRIAGE: frozenset(),
    Role.ORDER: frozenset({"get_order", "list_orders"}),
    Role.RETURN: frozenset({"get_order", "evaluate_return", "create_approval"}),
    Role.POLICY: frozenset({"search_policy"}),
}


class GraphState(TypedDict, total=False):
    active_agent: str
    message: str


def route_message(message: str) -> Role:
    lowered = message.lower()
    if any(word in lowered for word in ("return", "refund", "退货", "退款")):
        return Role.RETURN
    if any(word in lowered for word in ("policy", "warranty", "规则", "政策", "几天")):
        return Role.POLICY
    if any(word in lowered for word in ("order", "shipment", "订单", "物流")):
        return Role.ORDER
    return Role.TRIAGE


def route_from_current(message: str, current: Role) -> Role:
    routed = route_message(message)
    return current if routed == Role.TRIAGE and current != Role.TRIAGE else routed


def build_routing_graph() -> Any:
    graph: StateGraph[GraphState] = StateGraph(GraphState)

    def triage(state: GraphState) -> GraphState:
        current = Role(state.get("active_agent", Role.TRIAGE.value))
        return {**state, "active_agent": route_from_current(state["message"], current).value}

    graph.add_node("triage", triage)
    graph.add_edge(START, "triage")
    graph.add_edge("triage", END)
    return graph.compile()


class CommerceRuntime:
    def __init__(
        self, repository: SQLiteRepository, checkpoint_path: Path | str | None = None
    ) -> None:
        self.repository = repository
        self.policy = OfflinePolicyRetriever()
        self.graph = build_routing_graph()
        resolved_checkpoint_path = Path(
            checkpoint_path or repository.path.with_name("checkpoints.db")
        )
        self.sessions = SessionStateStore(resolved_checkpoint_path)
        self.returns = ReturnWorkflow(repository, resolved_checkpoint_path)

    def stream(self, state: ConversationState) -> Iterable[StreamEvent]:
        run_id = f"run-{uuid.uuid4().hex}"
        sequence = 0

        def event(kind: EventType, data: dict[str, Any]) -> StreamEvent:
            nonlocal sequence
            sequence += 1
            return StreamEvent(
                type=kind,
                run_id=run_id,
                thread_id=state.scope.thread_id,
                user_id=state.scope.user_id,
                seq=sequence,
                data=data,
            )

        previous_role = self.sessions.load(state.scope.user_id, state.scope.thread_id)
        routed = self.graph.invoke({"message": state.message, "active_agent": previous_role.value})
        role = Role(routed["active_agent"])
        self.sessions.save(state.scope.user_id, state.scope.thread_id, role)
        if role != previous_role:
            yield event("handoff", {"from": previous_role.value, "to": role.value})
        if role == Role.TRIAGE:
            yield event("message_update", {"text": "请说明是订单、退货还是政策问题。"})
        elif role == Role.ORDER:
            yield from self._order(state, event)
        elif role == Role.RETURN:
            yield from self._return(state, event)
        else:
            yield from self._policy(state, event)
        yield event("completed", {"active_agent": role.value})

    def _order(self, state: ConversationState, event: Any) -> Iterable[StreamEvent]:
        yield event("tool_start", {"tool": "list_orders"})
        orders = self.repository.list_orders(state.scope.user_id)
        yield event("tool_end", {"tool": "list_orders", "count": len(orders)})
        yield event(
            "message_update", {"orders": [order.model_dump(mode="json") for order in orders]}
        )

    def _return(self, state: ConversationState, event: Any) -> Iterable[StreamEvent]:
        order_id = state.order_id or self._extract_order_id(state.message)
        if not order_id:
            yield event("message_update", {"text": "请提供订单号。"})
            return
        reason = state.reason or state.message
        yield event("tool_start", {"tool": "get_order"})
        order = self.repository.get_order(state.scope.user_id, order_id)
        yield event("tool_end", {"tool": "get_order", "order_id": order_id})
        draft = evaluate_return(order, reason)
        if not draft.eligible:
            yield event("message_update", {"eligible": False, "reasons": draft.reasons})
            return
        self.returns.start(state.scope, order_id, reason)
        approval = self.repository.get_approval_by_request(
            state.scope.user_id, state.scope.request_id
        )
        yield event("approval_required", approval.model_dump(mode="json"))

    def resume_return(self, user_id: str, approval_id: str, approve: bool) -> dict[str, Any]:
        approval = self.repository.get_approval(user_id, approval_id)
        return self.returns.resume(approval.scope, approve)

    def _policy(self, state: ConversationState, event: Any) -> Iterable[StreamEvent]:
        yield event("tool_start", {"tool": "search_policy"})
        answer = self.policy.answer(state.message)
        yield event("tool_end", {"tool": "search_policy", "citations": len(answer.citations)})
        yield event("message_update", answer.model_dump(mode="json"))

    @staticmethod
    def _extract_order_id(message: str) -> str | None:
        match = re.search(r"order-\d+", message, re.IGNORECASE)
        return match.group(0).lower() if match else None

    def sse(self, state: ConversationState) -> Iterable[str]:
        for item in self.stream(state):
            self.sessions.append_event(item)
            yield f"event: {item.type}\ndata: {json.dumps(item.model_dump(mode='json'))}\n\n"
