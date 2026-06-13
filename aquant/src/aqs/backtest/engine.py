"""Event-driven backtest engine that models real A-share trading.

Models the rules that make or break a backtest's realism:

* **T+1 settlement** - shares bought today cannot be sold until tomorrow.
* **Price limits** - cannot buy at 涨停 (limit up) or sell at 跌停 (limit down);
  ratios differ by board / ST status.
* **Lot size** - buys rounded down to 100-share lots.
* **Suspensions / delisting** - no trading on suspended or delisted bars.
* **Costs** - commission (with minimum), stamp duty (sell), transfer fee, slippage.
* **Matching** - configurable: next-bar open (default, no look-ahead), close, or
  a volume-participation cap that produces partial fills.

It is wired to the risk and compliance modules so every order passes pre-trade
risk checks and is recorded in the audit log.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence

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
from aqs.data.market_data import MarketDataManager
from aqs.strategy.api import Context, Strategy


def _round_lot(shares: int, lot: int) -> int:
    if shares <= 0:
        return 0
    return (shares // lot) * lot


@dataclass
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    benchmark: pd.Series
    trades: List[Trade]
    orders: List[Order]
    positions_history: pd.DataFrame
    portfolio: Portfolio
    logs: List[str]
    config: SystemConfig
    data_version: str

    def to_frame(self) -> pd.DataFrame:
        df = pd.DataFrame({"equity": self.equity_curve})
        if len(self.benchmark):
            bench = self.benchmark.reindex(self.equity_curve.index).ffill()
            df["benchmark"] = bench / bench.iloc[0] * self.equity_curve.iloc[0]
        return df


class _BacktestContext(Context):
    """Concrete Context bound to a running :class:`BacktestEngine`."""

    def __init__(self, engine: "BacktestEngine") -> None:
        self._e = engine

    # clock / universe
    @property
    def now(self) -> pd.Timestamp:
        return self._e.now

    @property
    def universe(self) -> List[str]:
        return self._e.universe

    def set_universe(self, symbols) -> None:
        self._e.universe = list(symbols)

    # ordering -------------------------------------------------------------
    def order(self, symbol: str, amount: int, tag: str = "") -> Optional[str]:
        return self._e.submit_order(symbol, int(amount), tag=tag)

    def order_target_shares(self, symbol: str, target: int, tag: str = "") -> Optional[str]:
        pos = self.get_position(symbol)
        return self.order(symbol, int(target) - pos.quantity, tag=tag)

    def order_value(self, symbol: str, value: float, tag: str = "") -> Optional[str]:
        px = self.current(symbol, "close")
        if not px:
            return None
        return self.order(symbol, int(value / px), tag=tag)

    def order_target_value(self, symbol: str, value: float, tag: str = "") -> Optional[str]:
        px = self.current(symbol, "close")
        if not px:
            return None
        pos = self.get_position(symbol)
        delta_value = value - pos.quantity * px
        return self.order(symbol, int(delta_value / px), tag=tag)

    def order_target_percent(self, symbol: str, pct: float, tag: str = "") -> Optional[str]:
        total = self._e.portfolio.total_value
        return self.order_target_value(symbol, pct * total, tag=tag)

    # account --------------------------------------------------------------
    def get_position(self, symbol: str) -> Position:
        return self._e.portfolio.position(symbol)

    def get_account(self) -> dict:
        p = self._e.portfolio
        return {
            "cash": p.cash,
            "total_value": p.total_value,
            "positions_value": p.positions_value,
            "realized_pnl": p.realized_pnl,
            "positions": {s: pos for s, pos in p.positions.items() if pos.quantity > 0},
        }

    # data -----------------------------------------------------------------
    def get_price(self, symbol, start=None, end=None, fields=None, adjust="none") -> pd.DataFrame:
        return self._e.data.get_price(symbol, start, end, fields, adjust)

    def current(self, symbol: str, field: str = "close") -> Optional[float]:
        return self._e.data.current_price(symbol, self._e.now, field)

    def history(self, symbol: str, field: str = "close", n: int = 20, adjust: str = "none") -> pd.Series:
        df = self._e.data.get_price(symbol, end=self._e.now, fields=[field], adjust=adjust)
        return df[field].dropna().tail(n)

    def get_fundamentals(self, symbols, fields=None) -> pd.DataFrame:
        return self._e.data.get_fundamentals(symbols, when=self._e.now, fields=fields)

    def can_trade(self, symbol: str) -> bool:
        return self._e.can_trade(symbol)

    # utilities ------------------------------------------------------------
    def schedule_function(self, func: Callable, when: str = "daily") -> None:
        self._e.schedules.append((func, when))

    def log(self, message: str, level: str = "INFO") -> None:
        self._e.log(message, level)


class BacktestEngine:
    def __init__(
        self,
        data: MarketDataManager,
        strategy: Strategy,
        config: SystemConfig = DEFAULT_CONFIG,
        risk_manager=None,
        compliance=None,
        fill_mode: str = "next_open",
        participation_rate: float = 0.25,
    ) -> None:
        self.data = data
        self.strategy = strategy
        self.config = config
        self.cost_model = CostModel(config.cost)
        self.portfolio = Portfolio(config.initial_cash)
        self.risk = risk_manager
        self.compliance = compliance
        self.fill_mode = fill_mode  # "next_open" | "close"
        self.participation_rate = participation_rate

        self.now: pd.Timestamp = pd.Timestamp.min
        self.universe: List[str] = data.symbols
        self.schedules: List[tuple] = []
        self.pending: List[Order] = []
        self.all_orders: List[Order] = []
        self.trades: List[Trade] = []
        self.logs: List[str] = []
        self._equity: List[float] = []
        self._dates: List[pd.Timestamp] = []
        self._pos_rows: List[dict] = []
        self.ctx = _BacktestContext(self)

    # --------------------------------------------------------------- logging
    def log(self, message: str, level: str = "INFO") -> None:
        stamp = self.now.date() if self.now != pd.Timestamp.min else "init"
        self.logs.append(f"[{stamp}] {level}: {message}")

    # -------------------------------------------------------------- helpers
    def can_trade(self, symbol: str) -> bool:
        if symbol not in self.data.symbols:
            return False
        if not self.data.is_active(symbol, self.now):
            return False
        return not self.data.is_suspended(symbol, self.now)

    def _mark_prices(self, dt: pd.Timestamp) -> None:
        price_map = {}
        for sym in self.portfolio.positions:
            px = self.data.current_price(sym, dt, "close")
            if px is not None:
                price_map[sym] = px
        self.portfolio.mark_prices(price_map)

    # ---------------------------------------------------------- order entry
    def submit_order(self, symbol: str, amount: int, tag: str = "") -> Optional[str]:
        if amount == 0:
            return None
        side = OrderSide.BUY if amount > 0 else OrderSide.SELL
        qty = abs(int(amount))

        lot = self.config.rules.lot_size
        if side == OrderSide.BUY:
            qty = _round_lot(qty, lot)
        else:
            pos = self.portfolio.position(symbol)
            # selling more than held -> clamp; allow odd-lot only when closing all
            qty = min(qty, pos.available)
            if qty < pos.available:
                qty = _round_lot(qty, lot)
        if qty <= 0:
            return None

        order = Order(
            symbol=symbol,
            side=side,
            quantity=qty,
            order_type=OrderType.MARKET,
            created_at=self.now,
            tag=tag,
        )

        # Pre-trade risk check
        if self.risk is not None:
            ok, reason = self.risk.check_order(order, self.portfolio, self.data, self.now)
            if not ok:
                order.status = OrderStatus.REJECTED
                order.reason = reason
                self.all_orders.append(order)
                if self.compliance is not None:
                    self.compliance.on_order(order, self.now, rejected=True)
                self.log(f"风控拦截 {symbol} {side.value} {qty}: {reason}", "RISK")
                return order.order_id

        if self.compliance is not None:
            self.compliance.on_order(order, self.now)
        self.pending.append(order)
        self.all_orders.append(order)
        return order.order_id

    # ------------------------------------------------------------ matching
    def _match_orders(self, dt: pd.Timestamp, price_field: str) -> None:
        still_open: List[Order] = []
        for order in self.pending:
            self._try_fill(order, dt, price_field)
            if order.is_open:
                # one matching attempt per bar; leftover market orders cancel
                order.status = OrderStatus.CANCELLED
                if not order.reason:
                    order.reason = "未完全成交，收盘撤单"
                if self.compliance is not None:
                    self.compliance.on_cancel(order, dt)
        self.pending = still_open

    def _try_fill(self, order: Order, dt: pd.Timestamp, price_field: str) -> None:
        sym = order.symbol
        if not self.can_trade(sym):
            order.status = OrderStatus.REJECTED
            order.reason = "停牌/退市，无法成交"
            return
        ref_price = self.data.current_price(sym, dt, price_field)
        if ref_price is None:
            order.status = OrderStatus.REJECTED
            order.reason = "无行情，无法成交"
            return

        limits = self.data.price_limits(sym, dt)
        if limits is not None:
            upper, lower = limits
            if order.side == OrderSide.BUY and ref_price >= upper - 1e-9:
                order.status = OrderStatus.REJECTED
                order.reason = "涨停无法买入"
                return
            if order.side == OrderSide.SELL and ref_price <= lower + 1e-9:
                order.status = OrderStatus.REJECTED
                order.reason = "跌停无法卖出"
                return

        fill_price = self.cost_model.apply_slippage(order.side, ref_price)

        # volume-participation cap -> possible partial fill
        bar = self.data.get_bar(sym, dt)
        max_by_volume = order.remaining
        if bar is not None and not pd.isna(bar.get("volume", np.nan)):
            cap = int(float(bar["volume"]) * self.participation_rate)
            max_by_volume = min(order.remaining, max(cap, 0))

        fill_qty = max_by_volume
        if order.side == OrderSide.BUY:
            # cash constraint (reserve for fees)
            fees_per_share = fill_price * (
                self.config.cost.commission_rate + self.config.cost.transfer_fee_rate
            )
            affordable = int(self.portfolio.cash / (fill_price + fees_per_share + 1e-9))
            affordable = _round_lot(affordable, self.config.rules.lot_size)
            fill_qty = min(fill_qty, affordable)
            fill_qty = _round_lot(fill_qty, self.config.rules.lot_size)
            if fill_qty <= 0:
                order.status = OrderStatus.REJECTED
                order.reason = "资金不足"
                return
        else:
            fill_qty = min(fill_qty, self.portfolio.position(sym).available)
            if fill_qty <= 0:
                order.status = OrderStatus.REJECTED
                order.reason = "可用持仓不足(T+1)"
                return

        fees = self.cost_model.fees(order.side, fill_price, fill_qty)
        trade = Trade(
            order_id=order.order_id,
            symbol=sym,
            side=order.side,
            quantity=fill_qty,
            price=round(fill_price, 4),
            commission=fees.commission,
            stamp_duty=fees.stamp_duty,
            transfer_fee=fees.transfer_fee,
            timestamp=dt,
            tag=order.tag,
        )
        self.portfolio.apply_trade(trade)
        self.trades.append(trade)

        order.filled_quantity += fill_qty
        total_notional = order.avg_fill_price * (order.filled_quantity - fill_qty) + fill_price * fill_qty
        order.avg_fill_price = total_notional / order.filled_quantity
        order.status = OrderStatus.FILLED if order.remaining == 0 else OrderStatus.PARTIAL

        if self.compliance is not None:
            self.compliance.on_trade(trade)
        self.strategy.on_order(self.ctx, order)

    # ---------------------------------------------------------- scheduling
    def _should_run_schedule(self, when: str, dt: pd.Timestamp, prev: Optional[pd.Timestamp]) -> bool:
        if when == "daily":
            return True
        if prev is None:
            return True
        if when == "weekly":
            return dt.isocalendar().week != prev.isocalendar().week or dt.year != prev.year
        if when == "monthly":
            return (dt.year, dt.month) != (prev.year, prev.month)
        return True

    # ---------------------------------------------------------------- run
    def run(self, start=None, end=None) -> BacktestResult:
        sessions = self.data.trading_dates(start, end)
        if len(sessions) == 0:
            raise ValueError("no trading sessions in the requested range")

        # initialize strategy
        self.now = sessions[0]
        self.data.set_as_of(self.now)
        self.strategy.initialize(self.ctx)

        prev: Optional[pd.Timestamp] = None
        for i, dt in enumerate(sessions):
            self.now = dt
            self.data.set_as_of(dt)
            self.portfolio.settle()  # T+1: yesterday's buys available

            # 1) next-open matching of orders placed on the previous session
            if self.fill_mode == "next_open" and self.pending:
                self._match_orders(dt, "open")

            self._mark_prices(dt)

            # 2) session hooks + scheduled functions + per-bar logic
            self.strategy.before_trading(self.ctx)
            for func, when in self.schedules:
                if self._should_run_schedule(when, dt, prev):
                    func(self.ctx)
            self.strategy.handle_data(self.ctx)

            # 3) close matching
            if self.fill_mode == "close" and self.pending:
                self._match_orders(dt, "close")

            self.strategy.after_trading(self.ctx)
            self._mark_prices(dt)

            # 4) record equity / positions
            self._equity.append(self.portfolio.total_value)
            self._dates.append(dt)
            snap = self.portfolio.snapshot(dt)
            snap["n_positions"] = sum(1 for p in self.portfolio.positions.values() if p.quantity > 0)
            self._pos_rows.append(snap)

            # real-time risk monitoring hook
            if self.risk is not None:
                self.risk.monitor(self.portfolio, dt, self)

            prev = dt

        self.data.set_as_of(None)
        return self._build_result(sessions)

    def _build_result(self, sessions: pd.DatetimeIndex) -> BacktestResult:
        equity = pd.Series(self._equity, index=pd.DatetimeIndex(self._dates), name="equity")
        returns = equity.pct_change().fillna(0.0)
        bench = self.data.benchmark()
        bench_close = bench["close"].reindex(equity.index).ffill() if len(bench) else pd.Series(dtype=float)
        positions_history = pd.DataFrame(self._pos_rows).set_index("timestamp") if self._pos_rows else pd.DataFrame()
        return BacktestResult(
            equity_curve=equity,
            returns=returns,
            benchmark=bench_close,
            trades=self.trades,
            orders=self.all_orders,
            positions_history=positions_history,
            portfolio=self.portfolio,
            logs=self.logs,
            config=self.config,
            data_version=self.data.data_version,
        )
