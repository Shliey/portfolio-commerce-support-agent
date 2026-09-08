from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from .eligibility import evaluate_return
from .models import ConversationState, EventType, Role, StreamEvent
from .observability import ToolExecutor, ToolLimitExceeded
from .ports import BusinessRepository
from .rag import OfflinePolicyRetriever, SemanticPolicyRetriever
from .repository import IdempotencyConflict, NotFound
from .return_workflow import ReturnWorkflow
from .session_store import SessionStateStore
from .tools import OrderTools

ROLE_TOOLS: dict[Role, frozenset[str]] = {
    Role.TRIAGE: frozenset(),
    Role.ORDER: frozenset({"get_order", "list_orders"}),
    Role.RETURN: frozenset({"get_order", "evaluate_return", "create_approval"}),
    Role.POLICY: frozenset({"search_policy"}),
}


class ToolNotAllowed(Exception):
    pass


class StepLimitExceeded(Exception):
    pass


def require_allowed_tool(
    role: Role, tool: str, audit_sink: Any = None, context: dict[str, str] | None = None
) -> None:
    if tool not in ROLE_TOOLS[role]:
        if audit_sink is not None:
            audit_sink(
                {
                    **(context or {}),
                    "call_type": "tool_authorization",
                    "role": role.value,
                    "name": tool,
                    "status": "rejected",
                }
            )
        raise ToolNotAllowed("tool_not_allowed")


class RoutingDecision(BaseModel):
    role: Role
    order_id: str | None = None
    reason: str | None = None


class IntentRouter(Protocol):
    def route(self, message: str, current: Role) -> RoutingDecision: ...


class KeywordIntentRouter:
    """Deterministic zero-cost router used by tests and the local demo."""

    def route(self, message: str, current: Role) -> RoutingDecision:
        role = route_from_current(message, current)
        order_match = re.search(r"order-\d+", message, re.IGNORECASE)
        return RoutingDecision(
            role=role,
            order_id=order_match.group(0).lower() if order_match else None,
            reason=message if role == Role.RETURN else None,
        )


class GraphState(TypedDict, total=False):
    active_agent: str
    message: str
    order_id: str | None
    reason: str | None


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


def build_routing_graph(router: IntentRouter | None = None) -> Any:
    resolved_router = router or KeywordIntentRouter()
    graph: StateGraph[GraphState] = StateGraph(GraphState)

    def triage(state: GraphState) -> GraphState:
        current = Role(state.get("active_agent", Role.TRIAGE.value))
        decision = resolved_router.route(state["message"], current)
        return {
            **state,
            "active_agent": decision.role.value,
            "order_id": decision.order_id,
            "reason": decision.reason,
        }

    graph.add_node("triage", triage)
    graph.add_edge(START, "triage")
    graph.add_edge("triage", END)
    return graph.compile()


class CommerceRuntime:
    def __init__(
        self,
        repository: BusinessRepository,
        checkpoint_path: Path | str | None = None,
        *,
        audit_sink: Any = None,
        policy_retriever: SemanticPolicyRetriever | None = None,
        intent_router: IntentRouter | None = None,
        max_steps: int = 20,
        max_tool_calls: int = 4,
    ) -> None:
        self.repository = repository
        self.order_tools = OrderTools(repository)
        self.policy = policy_retriever or OfflinePolicyRetriever()
        self.graph = build_routing_graph(intent_router)
        resolved_checkpoint_path = Path(
            checkpoint_path or repository.path.with_name("checkpoints.db")
        )
        self.sessions = SessionStateStore(resolved_checkpoint_path)
        self.returns = ReturnWorkflow(repository, resolved_checkpoint_path)
        self.audit_sink = audit_sink
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls

    def stream(self, state: ConversationState) -> Iterable[StreamEvent]:
        run_id = f"run-{uuid.uuid4().hex}"
        sequence = 0
        tools = ToolExecutor(
            context={
                "run_id": run_id,
                "user_id": state.scope.user_id,
                "thread_id": state.scope.thread_id,
            },
            sink=self.audit_sink,
            max_calls=self.max_tool_calls,
        )

        def event(kind: EventType, data: dict[str, Any]) -> StreamEvent:
            nonlocal sequence
            if sequence >= self.max_steps:
                raise StepLimitExceeded("step_limit_exceeded")
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
        state = state.model_copy(
            update={
                "order_id": state.order_id or routed.get("order_id"),
                "reason": state.reason or routed.get("reason"),
            }
        )
        self.sessions.save(state.scope.user_id, state.scope.thread_id, role)
        if role != previous_role:
            yield event("handoff", {"from": previous_role.value, "to": role.value})
        if role == Role.TRIAGE:
            yield event("message_update", {"text": "请说明是订单、退货还是政策问题。"})
        elif role == Role.ORDER:
            yield from self._order(state, event, tools, role)
        elif role == Role.RETURN:
            yield from self._return(state, event, tools, role)
        else:
            yield from self._policy(state, event, tools, role)
        yield event("completed", {"active_agent": role.value})

    def _order(
        self, state: ConversationState, event: Any, tools: ToolExecutor, role: Role
    ) -> Iterable[StreamEvent]:
        require_allowed_tool(role, "list_orders")
        yield event("tool_start", {"tool": "list_orders"})
        orders = tools.call(
            "list_orders",
            lambda: self.order_tools.list_orders(state.scope.user_id),
            {"user_id": state.scope.user_id},
        )
        yield event("tool_end", {"tool": "list_orders", "count": len(orders)})
        yield event(
            "message_update", {"orders": [order.model_dump(mode="json") for order in orders]}
        )

    def _return(
        self, state: ConversationState, event: Any, tools: ToolExecutor, role: Role
    ) -> Iterable[StreamEvent]:
        order_id = state.order_id or self._extract_order_id(state.message)
        if not order_id:
            yield event("message_update", {"text": "请提供订单号。"})
            return
        reason = state.reason or state.message
        require_allowed_tool(role, "get_order")
        yield event("tool_start", {"tool": "get_order"})
        order = tools.call(
            "get_order",
            lambda: self.order_tools.get_order(state.scope.user_id, order_id),
            {"user_id": state.scope.user_id, "order_id": order_id},
        )
        yield event("tool_end", {"tool": "get_order", "order_id": order_id})
        draft = evaluate_return(order, reason)
        if not draft.eligible:
            yield event("message_update", {"eligible": False, "reasons": draft.reasons})
            return
        require_allowed_tool(role, "create_approval")
        tools.call(
            "create_approval",
            lambda: self.returns.start(state.scope, order_id, reason),
            {"user_id": state.scope.user_id, "order_id": order_id, "reason": reason},
        )
        approval = self.repository.get_approval_by_request(
            state.scope.user_id, state.scope.request_id
        )
        yield event("approval_required", approval.model_dump(mode="json"))

    def resume_return(self, user_id: str, approval_id: str, approve: bool) -> dict[str, Any]:
        approval = self.repository.get_approval(user_id, approval_id)
        return self.returns.resume(approval.scope, approve)

    def _policy(
        self, state: ConversationState, event: Any, tools: ToolExecutor, role: Role
    ) -> Iterable[StreamEvent]:
        require_allowed_tool(role, "search_policy")
        yield event("tool_start", {"tool": "search_policy"})
        answer = tools.call(
            "search_policy", lambda: self.policy.answer(state.message), {"question": state.message}
        )
        yield event("tool_end", {"tool": "search_policy", "citations": len(answer.citations)})
        yield event("message_update", answer.model_dump(mode="json"))

    @staticmethod
    def _extract_order_id(message: str) -> str | None:
        match = re.search(r"order-\d+", message, re.IGNORECASE)
        return match.group(0).lower() if match else None

    def sse(self, state: ConversationState) -> Iterable[str]:
        last_event: StreamEvent | None = None
        try:
            for item in self.stream(state):
                last_event = item
                self.sessions.append_event(item)
                yield self._encode_sse(item)
        except Exception as error:
            if isinstance(error, (StepLimitExceeded, ToolLimitExceeded)):
                code = str(error)
                event_type: EventType = "limit_exceeded"
            elif isinstance(error, NotFound):
                code = "order_not_found"
                event_type = "error"
            elif isinstance(error, IdempotencyConflict):
                code = "idempotency_conflict"
                event_type = "error"
            else:
                code = "internal_error"
                event_type = "error"
            failure = StreamEvent(
                type=event_type,
                run_id=last_event.run_id if last_event else f"run-{uuid.uuid4().hex}",
                thread_id=state.scope.thread_id,
                user_id=state.scope.user_id,
                seq=(last_event.seq + 1) if last_event else 1,
                data={"code": code},
            )
            self.sessions.append_event(failure)
            yield self._encode_sse(failure)

    @staticmethod
    def _encode_sse(item: StreamEvent) -> str:
        return f"event: {item.type}\ndata: {json.dumps(item.model_dump(mode='json'))}\n\n"
