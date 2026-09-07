from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .models import Order, OrderStatus, ReturnDraft


def evaluate_return(order: Order, reason: str, now: datetime | None = None) -> ReturnDraft:
    now = now or datetime.now(UTC)
    failures: list[str] = []
    if order.status != OrderStatus.DELIVERED or order.delivered_at is None:
        failures.append("order_not_delivered")
    elif now - order.delivered_at > timedelta(days=7):
        failures.append("return_window_expired")
    if any(not item.returnable for item in order.items):
        failures.append("contains_non_returnable_item")
    return ReturnDraft(order_id=order.id, reason=reason, eligible=not failures, reasons=failures)
