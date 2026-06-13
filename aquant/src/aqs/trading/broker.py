"""Broker gateway abstraction and a simulated broker for paper trading.

``BrokerGateway`` is the seam where a real broker API (e.g. via a trading
terminal) plugs in. ``SimulatedBroker`` implements the same interface and fills
orders against market data using the A-share rules (price limits, suspension,
T+1, lot size, costs), so paper trading behaves like the backtest matcher.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from aqs.config import SystemConfig, DEFAULT_CONFIG
from aqs.backtest.costs import CostModel
from aqs.core.objects import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
    Trade,
)


@dataclass
class BrokerAccount:
    cash: float
    total_value: float
    positions_value: float
    positions: Dict[str, Position] = field(default_factory=dict)


class BrokerGateway(abc.ABC):
    """Interface every broker connector must implement."""

    @abc.abstractmethod
    def connect(self) -> bool: ...

    @abc.abstractmethod
    def disconnect(self) -> None: ...

    @property
    @abc.abstractmethod
    def connected(self) -> bool: ...

    @abc.abstractmethod
    def submit(self, order: Order) -> Order: ...

    @abc.abstractmethod
    def cancel(self, order_id: str) -> bool: ...

    @abc.abstractmethod
    def query_account(self) -> BrokerAccount: ...

    @abc.abstractmethod
    def query_positions(self) -> Dict[str, Position]: ...

    @abc.abstractmethod
    def query_orders(self) -> List[Order]: ...

    @abc.abstractmethod
    def query_trades(self) -> List[Trade]: ...


class SimulatedBroker(BrokerGateway):
    """Fills orders against a :class:`MarketDataManager` at the current time."""

    def __init__(self, data, config: SystemConfig = DEFAULT_CONFIG) -> None:
        self.data = data
        self.config = config
        self.cost_model = CostModel(config.cost)
        self.portfolio = Portfolio(config.initial_cash)
        self._connected = False
        self._orders: Dict[str, Order] = {}
        self._trades: List[Trade] = []
        self.now: pd.Timestamp = pd.Timestamp.min

    # --------------------------------------------------------- connection
    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    def set_time(self, when) -> None:
        self.now = pd.Timestamp(when)
        self.data.set_as_of(self.now)

    def settle(self) -> None:
        self.portfolio.settle()

    # ------------------------------------------------------------- orders
    def submit(self, order: Order) -> Order:
        if not self._connected:
            order.status = OrderStatus.REJECTED
            order.reason = "券商未连接"
            return order
        self._orders[order.order_id] = order
        self._fill(order)
        return order

    def cancel(self, order_id: str) -> bool:
        order = self._orders.get(order_id)
        if order and order.is_open:
            order.status = OrderStatus.CANCELLED
            order.reason = "用户撤单"
            return True
        return False

    def _fill(self, order: Order) -> None:
        sym = order.symbol
        if self.data.is_suspended(sym, self.now) or not self.data.is_active(sym, self.now):
            order.status = OrderStatus.REJECTED
            order.reason = "停牌/退市"
            return
        ref = self.data.current_price(sym, self.now, "close")
        if ref is None:
            order.status = OrderStatus.REJECTED
            order.reason = "无行情"
            return

        limits = self.data.price_limits(sym, self.now)
        if limits is not None:
            upper, lower = limits
            if order.side == OrderSide.BUY and ref >= upper - 1e-9:
                order.status = OrderStatus.REJECTED
                order.reason = "涨停无法买入"
                return
            if order.side == OrderSide.SELL and ref <= lower + 1e-9:
                order.status = OrderStatus.REJECTED
                order.reason = "跌停无法卖出"
                return

        price = self.cost_model.apply_slippage(order.side, ref)
        if order.order_type == OrderType.LIMIT and order.limit_price is not None:
            if order.side == OrderSide.BUY and price > order.limit_price:
                order.status = OrderStatus.PENDING
                return
            if order.side == OrderSide.SELL and price < order.limit_price:
                order.status = OrderStatus.PENDING
                return
            price = order.limit_price

        qty = order.remaining
        if order.side == OrderSide.BUY:
            fee_per = price * (self.config.cost.commission_rate + self.config.cost.transfer_fee_rate)
            affordable = int(self.portfolio.cash / (price + fee_per + 1e-9))
            lot = self.config.rules.lot_size
            qty = min(qty, (affordable // lot) * lot)
            if qty <= 0:
                order.status = OrderStatus.REJECTED
                order.reason = "资金不足"
                return
        else:
            qty = min(qty, self.portfolio.position(sym).available)
            if qty <= 0:
                order.status = OrderStatus.REJECTED
                order.reason = "可用持仓不足(T+1)"
                return

        fees = self.cost_model.fees(order.side, price, qty)
        trade = Trade(
            order_id=order.order_id, symbol=sym, side=order.side, quantity=qty,
            price=round(price, 4), commission=fees.commission, stamp_duty=fees.stamp_duty,
            transfer_fee=fees.transfer_fee, timestamp=self.now, tag=order.tag,
        )
        self.portfolio.apply_trade(trade)
        self._trades.append(trade)
        order.filled_quantity += qty
        order.avg_fill_price = price
        order.status = OrderStatus.FILLED if order.remaining == 0 else OrderStatus.PARTIAL

    # ------------------------------------------------------------ queries
    def mark_prices(self) -> None:
        pm = {}
        for s in self.portfolio.positions:
            px = self.data.current_price(s, self.now, "close")
            if px is not None:
                pm[s] = px
        self.portfolio.mark_prices(pm)

    def query_account(self) -> BrokerAccount:
        self.mark_prices()
        p = self.portfolio
        return BrokerAccount(cash=p.cash, total_value=p.total_value,
                             positions_value=p.positions_value,
                             positions={s: v for s, v in p.positions.items() if v.quantity > 0})

    def query_positions(self) -> Dict[str, Position]:
        return {s: v for s, v in self.portfolio.positions.items() if v.quantity > 0}

    def query_orders(self) -> List[Order]:
        return list(self._orders.values())

    def query_trades(self) -> List[Trade]:
        return list(self._trades)
