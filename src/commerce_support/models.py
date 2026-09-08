from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Role(StrEnum):
    TRIAGE = "triage"
    ORDER = "order"
    RETURN = "return"
    POLICY = "policy"


class OrderStatus(StrEnum):
    PLACED = "placed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"


class User(BaseModel):
    id: str
    username: str


class OrderItem(BaseModel):
    sku: str
    name: str
    quantity: int = Field(ge=1)
    unit_price_cents: int = Field(ge=0)
    returnable: bool = True


class Order(BaseModel):
    id: str
    user_id: str
    status: OrderStatus
    delivered_at: datetime | None = None
    items: list[OrderItem]


class Logistics(BaseModel):
    order_id: str
    status: OrderStatus
    carrier: str | None = None
    tracking_number: str | None = None
    delivered_at: datetime | None = None


class RequestScope(BaseModel):
    user_id: str
    thread_id: str
    request_id: str

    @property
    def checkpoint_key(self) -> str:
        return f"{self.user_id}:{self.thread_id}:{self.request_id}"


class ReturnDraft(BaseModel):
    order_id: str
    reason: str
    eligible: bool
    reasons: list[str] = Field(default_factory=list)


class Approval(BaseModel):
    id: str
    scope: RequestScope
    draft: ReturnDraft
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Ticket(BaseModel):
    id: str
    request_id: str
    user_id: str
    order_id: str
    reason: str
    created_at: datetime


class Citation(BaseModel):
    source: str
    title: str
    section: str


class PolicyAnswer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    insufficient_evidence: bool = False


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: RequestScope
    message: str
    active_agent: Role = Role.TRIAGE
    order_id: str | None = None
    reason: str | None = None
    result: dict[str, Any] = Field(default_factory=dict)


type EventType = Literal[
    "message_update",
    "tool_start",
    "tool_end",
    "handoff",
    "approval_required",
    "completed",
    "error",
]


class StreamEvent(BaseModel):
    type: EventType
    run_id: str
    thread_id: str
    user_id: str
    seq: int = Field(ge=1)
    data: dict[str, Any] = Field(default_factory=dict)
