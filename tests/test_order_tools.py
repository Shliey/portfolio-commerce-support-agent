import pytest

from commerce_support.repository import NotFound, SQLiteRepository
from commerce_support.tools import OrderTools


def test_order_tools_return_structured_owned_data(repository: SQLiteRepository) -> None:
    tools = OrderTools(repository)
    order = tools.get_order("user-1", "order-1001")
    logistics = tools.get_logistics("user-1", "order-1001")
    assert order.id == "order-1001"
    assert logistics.order_id == order.id
    assert logistics.tracking_number == "DEMO-1001"


def test_order_tools_do_not_widen_repository_ownership(repository: SQLiteRepository) -> None:
    tools = OrderTools(repository)
    with pytest.raises(NotFound, match="order_not_found"):
        tools.get_order("attacker", "order-1001")
    with pytest.raises(NotFound, match="order_not_found"):
        tools.get_logistics("attacker", "order-1001")
