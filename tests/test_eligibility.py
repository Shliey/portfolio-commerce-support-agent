from datetime import UTC, datetime, timedelta

from commerce_support.eligibility import evaluate_return
from commerce_support.models import Order, OrderItem, OrderStatus


def make_order(*, days: int = 1, returnable: bool = True) -> Order:
    return Order(
        id="order-1",
        user_id="user-1",
        status=OrderStatus.DELIVERED,
        delivered_at=datetime.now(UTC) - timedelta(days=days),
        items=[
            OrderItem(
                sku="sku", name="item", quantity=1, unit_price_cents=100, returnable=returnable
            )
        ],
    )


def test_eligible_within_seven_days() -> None:
    assert evaluate_return(make_order(), "does not fit").eligible


def test_expired_and_non_returnable_are_deterministic() -> None:
    draft = evaluate_return(make_order(days=8, returnable=False), "changed mind")
    assert not draft.eligible
    assert draft.reasons == ["return_window_expired", "contains_non_returnable_item"]


def test_non_delivered_and_missing_delivery_timestamp_are_ineligible() -> None:
    order = make_order()
    order.status = OrderStatus.SHIPPED
    draft = evaluate_return(order, "changed mind")
    assert not draft.eligible
    assert draft.reasons == ["order_not_delivered"]

    order.status = OrderStatus.DELIVERED
    order.delivered_at = None
    missing_timestamp = evaluate_return(order, "changed mind")
    assert not missing_timestamp.eligible
    assert missing_timestamp.reasons == ["order_not_delivered"]
