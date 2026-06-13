"""Execution Management System (EMS): order-slicing algorithms.

Turns a large "parent" order into a schedule of child orders to reduce market
impact: TWAP (even over time), VWAP (weighted by a volume profile) and iceberg
(show only a small slice at a time). The planners return child orders; the
caller (e.g. :class:`PaperTrader`) submits them on the appropriate steps.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

import numpy as np

from aqs.core.objects import Order, OrderSide, OrderType


def _round_lot(qty: int, lot: int) -> int:
    return max((qty // lot) * lot, 0)


class ExecutionManagementSystem:
    def __init__(self, lot_size: int = 100) -> None:
        self.lot_size = lot_size

    def _split_quantities(self, total: int, weights: Sequence[float]) -> List[int]:
        weights = np.array(weights, dtype=float)
        weights = weights / weights.sum()
        raw = weights * total
        qtys = [_round_lot(int(x), self.lot_size) for x in raw]
        # distribute any leftover lots one lot at a time across slices
        leftover = total - sum(qtys)
        i = 0
        while leftover >= self.lot_size and qtys:
            qtys[i % len(qtys)] += self.lot_size
            leftover -= self.lot_size
            i += 1
        return qtys

    def twap(self, symbol: str, side: OrderSide, total_qty: int, slices: int = 5, tag: str = "twap") -> List[Order]:
        weights = [1.0] * max(slices, 1)
        return self._build(symbol, side, total_qty, weights, tag)

    def vwap(self, symbol: str, side: OrderSide, total_qty: int, volume_profile: Sequence[float], tag: str = "vwap") -> List[Order]:
        if not len(volume_profile):
            volume_profile = [1.0]
        return self._build(symbol, side, total_qty, list(volume_profile), tag)

    def iceberg(self, symbol: str, side: OrderSide, total_qty: int, display_qty: int, tag: str = "iceberg") -> List[Order]:
        display_qty = max(_round_lot(display_qty, self.lot_size), self.lot_size)
        slices = max(int(np.ceil(total_qty / display_qty)), 1)
        weights = [1.0] * slices
        return self._build(symbol, side, total_qty, weights, tag)

    def _build(self, symbol: str, side: OrderSide, total_qty: int, weights: Sequence[float], tag: str) -> List[Order]:
        qtys = self._split_quantities(total_qty, weights)
        orders = []
        for i, q in enumerate(qtys):
            if q <= 0:
                continue
            orders.append(
                Order(symbol=symbol, side=side, quantity=q, order_type=OrderType.MARKET, tag=f"{tag}_{i+1}")
            )
        return orders
