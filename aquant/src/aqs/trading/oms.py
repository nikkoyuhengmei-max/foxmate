"""Order Management System (OMS).

Manages the full order lifecycle on top of a :class:`BrokerGateway`: submission
with duplicate-order protection, cancellation, status tracking and reconciliation
between local and broker state. Includes safety switches required for live
trading (read-only mode, global cancel, kill switch).
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import pandas as pd

from aqs.core.objects import Order, OrderSide, OrderStatus
from aqs.trading.broker import BrokerGateway


class OrderManagementSystem:
    def __init__(
        self,
        broker: BrokerGateway,
        dedup_window_seconds: float = 1.0,
        on_event: Optional[Callable[[str, Order], None]] = None,
    ) -> None:
        self.broker = broker
        self.dedup_window = pd.Timedelta(seconds=dedup_window_seconds)
        self.orders: Dict[str, Order] = {}
        self._recent: List[tuple] = []  # (key, timestamp)
        self.read_only = False
        self.kill_switch = False
        self.on_event = on_event

    # --------------------------------------------------------- safety
    def set_read_only(self, value: bool = True) -> None:
        self.read_only = value

    def engage_kill_switch(self) -> None:
        """One-click stop: cancel all open orders and block new ones."""
        self.kill_switch = True
        self.cancel_all()

    def reset_kill_switch(self) -> None:
        self.kill_switch = False

    # --------------------------------------------------------- lifecycle
    def _dup_key(self, order: Order) -> tuple:
        return (order.symbol, order.side.value, order.quantity, order.tag)

    def _is_duplicate(self, order: Order, when: pd.Timestamp) -> bool:
        key = self._dup_key(order)
        self._recent = [(k, t) for (k, t) in self._recent if when - t <= self.dedup_window]
        for k, _ in self._recent:
            if k == key:
                return True
        self._recent.append((key, when))
        return False

    def submit(self, order: Order) -> Order:
        when = order.created_at or pd.Timestamp.utcnow()
        if self.kill_switch:
            order.status = OrderStatus.REJECTED
            order.reason = "已触发一键停止(kill switch)"
            self._emit("reject", order)
            return order
        if self.read_only:
            order.status = OrderStatus.REJECTED
            order.reason = "只读模式，禁止下单"
            self._emit("reject", order)
            return order
        if self._is_duplicate(order, when):
            order.status = OrderStatus.REJECTED
            order.reason = "重复下单保护"
            self._emit("reject", order)
            return order

        self.orders[order.order_id] = order
        self.broker.submit(order)
        self._emit("submit", order)
        return order

    def cancel(self, order_id: str) -> bool:
        ok = self.broker.cancel(order_id)
        if ok and order_id in self.orders:
            self._emit("cancel", self.orders[order_id])
        return ok

    def cancel_all(self) -> int:
        n = 0
        for oid, o in self.orders.items():
            if o.is_open and self.broker.cancel(oid):
                n += 1
                self._emit("cancel", o)
        return n

    def open_orders(self) -> List[Order]:
        return [o for o in self.orders.values() if o.is_open]

    def reconcile(self) -> Dict[str, int]:
        """Compare local vs broker order state; return counts by status."""
        broker_orders = {o.order_id: o for o in self.broker.query_orders()}
        for oid, bo in broker_orders.items():
            if oid in self.orders:
                self.orders[oid].status = bo.status
                self.orders[oid].filled_quantity = bo.filled_quantity
        counts: Dict[str, int] = {}
        for o in self.orders.values():
            counts[o.status.value] = counts.get(o.status.value, 0) + 1
        return counts

    def _emit(self, event: str, order: Order) -> None:
        if self.on_event:
            self.on_event(event, order)
