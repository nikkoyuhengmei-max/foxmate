"""Paper-trading sandbox runner.

Drives a strategy over (replayed or live) market data, routing every order
through pre-trade risk -> compliance -> OMS -> broker. It uses the same
:class:`~aqs.strategy.api.Context` contract as the backtest engine, so going from
backtest to paper to live requires no strategy changes.

For *live* mode it enforces "先报告、后交易": trading is blocked until the
program-trading filing is complete (see :class:`ComplianceMonitor.can_go_live`).
"""

from __future__ import annotations

from typing import Callable, List, Optional

import pandas as pd

from aqs.config import SystemConfig, DEFAULT_CONFIG
from aqs.core.objects import Order, OrderSide, OrderStatus, OrderType, Position
from aqs.strategy.api import Context, Strategy
from aqs.trading.broker import SimulatedBroker
from aqs.trading.ems import ExecutionManagementSystem
from aqs.trading.oms import OrderManagementSystem


class _LiveContext(Context):
    def __init__(self, trader: "PaperTrader") -> None:
        self._t = trader

    @property
    def now(self) -> pd.Timestamp:
        return self._t.now

    @property
    def universe(self) -> List[str]:
        return self._t.universe

    @property
    def data(self):
        return self._t.data

    def set_universe(self, symbols) -> None:
        self._t.universe = list(symbols)

    def order(self, symbol: str, amount: int, tag: str = "") -> Optional[str]:
        return self._t.submit_order(symbol, int(amount), tag=tag)

    def order_target_shares(self, symbol: str, target: int, tag: str = "") -> Optional[str]:
        pos = self.get_position(symbol)
        return self.order(symbol, int(target) - pos.quantity, tag=tag)

    def order_value(self, symbol: str, value: float, tag: str = "") -> Optional[str]:
        px = self.current(symbol, "close")
        return self.order(symbol, int(value / px), tag=tag) if px else None

    def order_target_value(self, symbol: str, value: float, tag: str = "") -> Optional[str]:
        px = self.current(symbol, "close")
        if not px:
            return None
        pos = self.get_position(symbol)
        return self.order(symbol, int((value - pos.quantity * px) / px), tag=tag)

    def order_target_percent(self, symbol: str, pct: float, tag: str = "") -> Optional[str]:
        total = self._t.broker.query_account().total_value
        return self.order_target_value(symbol, pct * total, tag=tag)

    def get_position(self, symbol: str) -> Position:
        return self._t.broker.get_portfolio().position(symbol)

    def get_account(self) -> dict:
        acct = self._t.broker.query_account()
        return {
            "cash": acct.cash,
            "total_value": acct.total_value,
            "positions_value": acct.positions_value,
            "positions": acct.positions,
        }

    def get_price(self, symbol, start=None, end=None, fields=None, adjust="none"):
        return self._t.data.get_price(symbol, start, end, fields, adjust)

    def current(self, symbol: str, field: str = "close") -> Optional[float]:
        return self._t.data.current_price(symbol, self._t.now, field)

    def history(self, symbol: str, field: str = "close", n: int = 20, adjust: str = "none") -> pd.Series:
        df = self._t.data.get_price(symbol, end=self._t.now, fields=[field], adjust=adjust)
        return df[field].dropna().tail(n)

    def get_fundamentals(self, symbols, fields=None):
        return self._t.data.get_fundamentals(symbols, when=self._t.now, fields=fields)

    def can_trade(self, symbol: str) -> bool:
        return self._t.can_trade(symbol)

    def schedule_function(self, func, when: str = "daily") -> None:
        self._t.schedules.append((func, when))

    def log(self, message: str, level: str = "INFO") -> None:
        self._t.log(message, level)


class PaperTrader:
    def __init__(
        self,
        data,
        strategy: Strategy,
        config: SystemConfig = DEFAULT_CONFIG,
        risk_manager=None,
        compliance=None,
        live: bool = False,
        broker=None,
    ) -> None:
        self.data = data
        self.strategy = strategy
        self.config = config
        self.risk = risk_manager
        self.compliance = compliance
        self.live = live

        # 默认用模拟券商（纸上交易）；传入 broker 可对接真实券商（如 QMTBroker）做实盘。
        self.broker = broker if broker is not None else SimulatedBroker(data, config)
        self.oms = OrderManagementSystem(self.broker, on_event=self._on_oms_event)
        self.ems = ExecutionManagementSystem(lot_size=config.rules.lot_size)

        self.now: pd.Timestamp = pd.Timestamp.min
        self.universe: List[str] = data.symbols
        self.schedules: List[tuple] = []
        self.logs: List[str] = []
        self.ctx = _LiveContext(self)
        self.equity_curve: List[tuple] = []
        self._started = False

    # ----------------------------------------------------------- logging
    def log(self, message: str, level: str = "INFO") -> None:
        self.logs.append(f"[{self.now}] {level}: {message}")

    def _on_oms_event(self, event: str, order: Order) -> None:
        if self.compliance is not None:
            if event == "submit":
                self.compliance.on_order(order, self.now, rejected=order.status == OrderStatus.REJECTED)
            elif event == "cancel":
                self.compliance.on_cancel(order, self.now)

    # ----------------------------------------------------------- helpers
    def can_trade(self, symbol: str) -> bool:
        if symbol not in self.data.symbols:
            return False
        if not self.data.is_active(symbol, self.now):
            return False
        return not self.data.is_suspended(symbol, self.now)

    # --------------------------------------------------------- safety API
    def stop_trading(self) -> None:
        """一键停止交易: kill switch + cancel all + read only."""
        self.oms.engage_kill_switch()
        self.oms.set_read_only(True)
        if self.compliance is not None:
            self.compliance.record_manual("stop_trading", {}, when=self.now)
        self.log("一键停止交易已触发", "CRITICAL")

    def cancel_all(self) -> int:
        return self.oms.cancel_all()

    # --------------------------------------------------------- order entry
    def submit_order(self, symbol: str, amount: int, tag: str = "") -> Optional[str]:
        if amount == 0:
            return None
        side = OrderSide.BUY if amount > 0 else OrderSide.SELL
        qty = abs(int(amount))
        lot = self.config.rules.lot_size
        if side == OrderSide.BUY:
            qty = (qty // lot) * lot
        else:
            avail = self.broker.get_portfolio().position(symbol).available
            qty = min(qty, avail)
            if qty < avail:
                qty = (qty // lot) * lot
        if qty <= 0:
            return None

        order = Order(symbol=symbol, side=side, quantity=qty, order_type=OrderType.MARKET,
                      created_at=self.now, tag=tag)

        if self.risk is not None:
            ok, reason = self.risk.check_order(order, self.broker.get_portfolio(), self.data, self.now)
            if not ok:
                order.status = OrderStatus.REJECTED
                order.reason = reason
                if self.compliance is not None:
                    self.compliance.on_order(order, self.now, rejected=True)
                self.log(f"风控拦截 {symbol}: {reason}", "RISK")
                return order.order_id

        self.oms.submit(order)
        if order.status == OrderStatus.FILLED and self.compliance is not None:
            for t in self.broker.query_trades()[-1:]:
                if t.order_id == order.order_id:
                    self.compliance.on_trade(t)
        return order.order_id

    # --------------------------------------------------------------- run
    def _ensure_started(self) -> None:
        if self._started:
            return
        if self.live and self.compliance is not None:
            ok, reason = self.compliance.can_go_live()
            if not ok:
                raise PermissionError(f"实盘启动被拒: {reason}")
        self.broker.connect()
        self.now = self.data.trading_dates()[0]
        self.broker.set_time(self.now)
        self.strategy.initialize(self.ctx)
        self._started = True

    def step(self, dt) -> None:
        """Advance one session/tick. Usable for true live stepping."""
        self._ensure_started()
        self.now = pd.Timestamp(dt)
        self.broker.set_time(self.now)
        self.broker.settle()
        self.strategy.before_trading(self.ctx)
        for func, when in self.schedules:
            if self._should_run(when, self.now):
                func(self.ctx)
        self.strategy.handle_data(self.ctx)
        self.strategy.after_trading(self.ctx)
        self.broker.mark_prices()
        acct = self.broker.query_account()
        self.equity_curve.append((self.now, acct.total_value))
        if self.risk is not None:
            self.risk.monitor(self.broker.get_portfolio(), self.now, self)
            if self.risk.halted and not self.oms.kill_switch:
                self.log("风控触发停机，自动一键停止交易", "CRITICAL")
                self.stop_trading()

    _prev_dt: Optional[pd.Timestamp] = None

    def _should_run(self, when: str, dt: pd.Timestamp) -> bool:
        prev = self._prev_dt
        self._prev_dt = dt
        if when == "daily" or prev is None:
            return True
        if when == "weekly":
            return dt.isocalendar().week != prev.isocalendar().week or dt.year != prev.year
        if when == "monthly":
            return (dt.year, dt.month) != (prev.year, prev.month)
        return True

    def run(self, start=None, end=None):
        # Compute the full session list with the PIT clock cleared, otherwise an
        # already-pinned as_of would clip the range to a single day.
        self.data.set_as_of(None)
        sessions = self.data.trading_dates(start, end)
        self._ensure_started()
        for dt in sessions:
            self.step(dt)
        self.data.set_as_of(None)
        return pd.Series(
            [v for _, v in self.equity_curve],
            index=pd.DatetimeIndex([d for d, _ in self.equity_curve]),
            name="equity",
        )
