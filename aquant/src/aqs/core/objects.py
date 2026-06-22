"""Core trading domain objects: orders, trades, positions, portfolio.

These are shared by the backtest engine, the paper-trading sandbox and the live
trading gateway so a strategy sees the exact same interface everywhere.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional

import pandas as pd


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"      # 市价单
    LIMIT = "limit"        # 限价单


class OrderStatus(str, Enum):
    PENDING = "pending"        # 已提交，待撮合
    PARTIAL = "partial"        # 部分成交
    FILLED = "filled"          # 全部成交
    CANCELLED = "cancelled"    # 已撤单
    REJECTED = "rejected"      # 被拒（风控/合规/资金不足等）


_order_seq = itertools.count(1)


@dataclass
class Order:
    symbol: str
    side: OrderSide
    quantity: int                       # 委托数量（股）
    order_type: OrderType = OrderType.MARKET
    limit_price: Optional[float] = None
    created_at: Optional[pd.Timestamp] = None
    order_id: str = field(default_factory=lambda: f"O{next(_order_seq):08d}")
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: int = 0
    avg_fill_price: float = 0.0
    reason: str = ""                    # rejection / cancel reason
    tag: str = ""                       # strategy / signal tag for attribution

    @property
    def remaining(self) -> int:
        return self.quantity - self.filled_quantity

    @property
    def is_open(self) -> bool:
        return self.status in (OrderStatus.PENDING, OrderStatus.PARTIAL)


@dataclass
class Trade:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    commission: float
    stamp_duty: float
    transfer_fee: float
    timestamp: pd.Timestamp
    tag: str = ""

    @property
    def total_cost(self) -> float:
        return self.commission + self.stamp_duty + self.transfer_fee

    @property
    def gross_value(self) -> float:
        return self.price * self.quantity


@dataclass
class Position:
    symbol: str
    quantity: int = 0                   # 总持仓
    available: int = 0                  # 可卖数量（T+1 约束）
    avg_cost: float = 0.0               # 持仓均价（含成本）
    last_price: float = 0.0

    @property
    def market_value(self) -> float:
        return self.quantity * self.last_price

    @property
    def cost_value(self) -> float:
        return self.quantity * self.avg_cost

    @property
    def unrealized_pnl(self) -> float:
        return (self.last_price - self.avg_cost) * self.quantity

    @property
    def return_pct(self) -> float:
        if self.avg_cost <= 0:
            return 0.0
        return (self.last_price - self.avg_cost) / self.avg_cost


class Portfolio:
    """Tracks cash, positions and realised PnL.

    Implements A-share T+1: shares bought today are not sellable until the next
    trading day. Call :meth:`settle` at the start of each new session.
    """

    def __init__(self, initial_cash: float) -> None:
        self.initial_cash = float(initial_cash)
        self.cash = float(initial_cash)
        self.positions: Dict[str, Position] = {}
        self.realized_pnl = 0.0
        self.total_commission = 0.0

    # --------------------------------------------------------------- helpers
    def position(self, symbol: str) -> Position:
        return self.positions.get(symbol, Position(symbol=symbol))

    def settle(self) -> None:
        """Begin a new session: today's buys become available (T+1)."""
        for pos in self.positions.values():
            pos.available = pos.quantity

    def mark_prices(self, price_map: Dict[str, float]) -> None:
        for sym, pos in self.positions.items():
            px = price_map.get(sym)
            if px is not None:
                pos.last_price = px

    @property
    def positions_value(self) -> float:
        return sum(p.market_value for p in self.positions.values())

    @property
    def total_value(self) -> float:
        return self.cash + self.positions_value

    # ------------------------------------------------------------ accounting
    def apply_trade(self, trade: Trade) -> None:
        pos = self.positions.setdefault(trade.symbol, Position(symbol=trade.symbol))
        if trade.side == OrderSide.BUY:
            new_qty = pos.quantity + trade.quantity
            total_cost = pos.avg_cost * pos.quantity + trade.gross_value + trade.total_cost
            pos.avg_cost = total_cost / new_qty if new_qty else 0.0
            pos.quantity = new_qty
            # bought today -> not yet available (T+1)
            self.cash -= trade.gross_value + trade.total_cost
        else:  # SELL
            realized = (trade.price - pos.avg_cost) * trade.quantity - trade.total_cost
            self.realized_pnl += realized
            pos.quantity -= trade.quantity
            pos.available -= trade.quantity
            self.cash += trade.gross_value - trade.total_cost
            if pos.quantity <= 0:
                pos.quantity = 0
                pos.available = 0
                pos.avg_cost = 0.0
        pos.last_price = trade.price
        self.total_commission += trade.total_cost

    def snapshot(self, when: Optional[pd.Timestamp] = None) -> Dict:
        return {
            "timestamp": when,
            "cash": round(self.cash, 2),
            "positions_value": round(self.positions_value, 2),
            "total_value": round(self.total_value, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "n_positions": sum(1 for p in self.positions.values() if p.quantity > 0),
        }
