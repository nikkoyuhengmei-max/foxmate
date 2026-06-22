"""Unified strategy API.

A strategy subclasses :class:`Strategy` and implements lifecycle hooks. During a
run (backtest, paper or live) the engine passes a :class:`Context` object that
exposes a consistent ordering / data API:

    ctx.order_target_percent("600000.SH", 0.1)
    ctx.get_price("600000.SH", fields=["close"])
    ctx.get_fundamentals(ctx.universe, fields=["pe", "roe"])
    ctx.history("600000.SH", "close", 20)
    pos = ctx.get_position("600000.SH")
    acct = ctx.get_account()
    ctx.schedule_function(self.rebalance, "weekly")

The same Context contract is implemented by the backtest engine and the
paper/live runner, so a strategy moves from backtest to live unchanged.
"""

from __future__ import annotations

import abc
from typing import Iterable, List, Optional, Sequence

import pandas as pd

from aqs.core.objects import Position


class Context(abc.ABC):
    """Abstract trading context handed to strategies by any run engine."""

    # ------------------------------------------------------------- clock/env
    @property
    @abc.abstractmethod
    def now(self) -> pd.Timestamp: ...

    @property
    @abc.abstractmethod
    def universe(self) -> List[str]: ...

    @property
    def data(self):
        """底层数据管理器（供选股/因子计算使用）。引擎实现会重写。"""
        raise NotImplementedError

    def set_universe(self, symbols: Iterable[str]) -> None:  # optional override
        raise NotImplementedError

    # ------------------------------------------------------------- ordering
    @abc.abstractmethod
    def order(self, symbol: str, amount: int, tag: str = "") -> Optional[str]:
        """Order ``amount`` shares (negative = sell). Returns order id."""

    @abc.abstractmethod
    def order_target_shares(self, symbol: str, target: int, tag: str = "") -> Optional[str]:
        """Adjust holding so total shares == ``target``."""

    @abc.abstractmethod
    def order_value(self, symbol: str, value: float, tag: str = "") -> Optional[str]:
        """Buy/sell approximately ``value`` worth (rounded to lots)."""

    @abc.abstractmethod
    def order_target_value(self, symbol: str, value: float, tag: str = "") -> Optional[str]:
        """Adjust holding so its market value == ``value``."""

    @abc.abstractmethod
    def order_target_percent(self, symbol: str, pct: float, tag: str = "") -> Optional[str]:
        """Adjust holding to ``pct`` of total portfolio value (0..1)."""

    # --------------------------------------------------------------- account
    @abc.abstractmethod
    def get_position(self, symbol: str) -> Position: ...

    @abc.abstractmethod
    def get_account(self) -> dict: ...

    # ------------------------------------------------------------------ data
    @abc.abstractmethod
    def get_price(self, symbol: str, start=None, end=None, fields=None, adjust: str = "none") -> pd.DataFrame: ...

    @abc.abstractmethod
    def current(self, symbol: str, field: str = "close") -> Optional[float]: ...

    @abc.abstractmethod
    def history(self, symbol: str, field: str = "close", n: int = 20, adjust: str = "none") -> pd.Series: ...

    @abc.abstractmethod
    def get_fundamentals(self, symbols, fields: Optional[Sequence[str]] = None) -> pd.DataFrame: ...

    @abc.abstractmethod
    def can_trade(self, symbol: str) -> bool: ...

    # ------------------------------------------------------------- utilities
    @abc.abstractmethod
    def schedule_function(self, func, when: str = "daily") -> None:
        """Register a callback. ``when`` in {daily, weekly, monthly}."""

    @abc.abstractmethod
    def log(self, message: str, level: str = "INFO") -> None: ...


class Strategy(abc.ABC):
    """Base class for all strategies.

    Override the hooks you need. ``initialize`` runs once; ``handle_data`` runs
    every bar; the ``*_trading`` hooks run at session boundaries.
    """

    #: human-readable name used in logs / reports
    name: str = "BaseStrategy"

    def initialize(self, ctx: Context) -> None:
        """Set parameters, universe and schedules. Runs once at start."""

    def before_trading(self, ctx: Context) -> None:
        """Runs at the start of each trading session, before matching."""

    def handle_data(self, ctx: Context) -> None:
        """Runs every bar. Default no-op so schedule-only strategies work."""

    def after_trading(self, ctx: Context) -> None:
        """Runs at the end of each trading session."""

    def on_order(self, ctx: Context, order) -> None:
        """Optional order-status callback."""
