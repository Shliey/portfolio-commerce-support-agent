from __future__ import annotations

import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypedDict

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .eligibility import evaluate_return
from .models import RequestScope
from .ports import BusinessRepository


def strict_checkpoint_serializer() -> JsonPlusSerializer:
    return JsonPlusSerializer(
        pickle_fallback=False,
        allowed_json_modules=None,
        allowed_msgpack_modules=None,
    )


class ReturnWorkflowState(TypedDict, total=False):
    user_id: str
    thread_id: str
    request_id: str
    order_id: str
    reason: str
    approval_id: str
    status: str
    reasons: list[str]
    ticket: dict[str, Any] | None


class ReturnWorkflow:
    """A restart-resumable return workflow backed by a separate checkpoint database."""

    def __init__(
        self,
        repository: BusinessRepository,
        checkpoint_path: Path | str,
        *,
        after_business_write: Callable[[], None] | None = None,
    ) -> None:
        self.repository = repository
        self.checkpoint_path = Path(checkpoint_path)
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.after_business_write = after_business_write

    @staticmethod
    def checkpoint_key(scope: RequestScope) -> str:
        return scope.checkpoint_key

    def _build(self, saver: SqliteSaver) -> Any:
        graph: StateGraph[ReturnWorkflowState] = StateGraph(ReturnWorkflowState)

        def review(state: ReturnWorkflowState) -> ReturnWorkflowState:
            scope = RequestScope(
                user_id=state["user_id"],
                thread_id=state["thread_id"],
                request_id=state["request_id"],
            )
            order = self.repository.get_order(scope.user_id, state["order_id"])
            draft = evaluate_return(order, state["reason"])
            if not draft.eligible:
                return {**state, "status": "ineligible", "reasons": draft.reasons, "ticket": None}

            approval = self.repository.create_approval(scope, draft)
            decision = interrupt(
                {
                    "approval_id": approval.id,
                    "draft": approval.draft.model_dump(mode="json"),
                }
            )
            approved = bool(decision.get("approve")) if isinstance(decision, dict) else False
            ticket = self.repository.decide_approval(scope.user_id, approval.id, approved)
            if ticket is not None and self.after_business_write is not None:
                self.after_business_write()
            return {
                **state,
                "approval_id": approval.id,
                "status": "approved" if approved else "rejected",
                "ticket": ticket.model_dump(mode="json") if ticket else None,
            }

        graph.add_node("review", review)
        graph.add_edge(START, "review")
        graph.add_edge("review", END)
        return graph.compile(checkpointer=saver)

    def start(self, scope: RequestScope, order_id: str, reason: str) -> dict[str, Any]:
        initial: ReturnWorkflowState = {
            "user_id": scope.user_id,
            "thread_id": scope.thread_id,
            "request_id": scope.request_id,
            "order_id": order_id,
            "reason": reason,
            "status": "started",
        }
        return self._invoke(scope, initial)

    def resume(self, scope: RequestScope, approve: bool) -> dict[str, Any]:
        # Re-check ownership here; callers cannot rely on API middleware alone.
        self.repository.get_approval_by_request(scope.user_id, scope.request_id)
        return self._invoke(scope, Command(resume={"approve": approve}))

    def _invoke(
        self, scope: RequestScope, value: ReturnWorkflowState | Command[Any]
    ) -> dict[str, Any]:
        connection = sqlite3.connect(self.checkpoint_path, check_same_thread=False)
        try:
            saver = SqliteSaver(connection, serde=strict_checkpoint_serializer())
            saver.setup()
            graph = self._build(saver)
            result = graph.invoke(
                value,
                {"configurable": {"thread_id": self.checkpoint_key(scope)}},
            )
            return dict(result)
        finally:
            connection.close()
