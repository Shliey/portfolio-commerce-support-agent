from __future__ import annotations

from .models import Logistics, Order
from .ports import BusinessRepository


class OrderTools:
    """Ownership-safe deterministic order and logistics tool boundary."""

    def __init__(self, repository: BusinessRepository) -> None:
        self.repository = repository

    def list_orders(self, user_id: str) -> list[Order]:
        return self.repository.list_orders(user_id)

    def get_order(self, user_id: str, order_id: str) -> Order:
        return self.repository.get_order(user_id, order_id)

    def get_logistics(self, user_id: str, order_id: str) -> Logistics:
        return self.repository.get_logistics(user_id, order_id)
