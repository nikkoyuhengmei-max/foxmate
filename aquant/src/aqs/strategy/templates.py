"""Ready-to-run strategy templates.

These are intentionally simple, well-commented reference implementations that use
only the unified :class:`~aqs.strategy.api.Context` API, so they run identically
in backtest, paper and live mode.
"""

from __future__ import annotations

from typing import List, Optional

import numpy as np
import pandas as pd

from aqs.strategy.api import Context, Strategy


class DoubleMA(Strategy):
    """双均线策略: golden cross buys, death cross sells.

    Goes long a single symbol (or each symbol in the universe) when the fast MA
    crosses above the slow MA, flat when it crosses below.
    """

    name = "双均线策略"

    def __init__(self, fast: int = 5, slow: int = 20, symbols: Optional[List[str]] = None) -> None:
        self.fast = fast
        self.slow = slow
        self._symbols = symbols

    def initialize(self, ctx: Context) -> None:
        if self._symbols:
            ctx.set_universe(self._symbols)

    def handle_data(self, ctx: Context) -> None:
        targets = self._symbols or ctx.universe
        weight = 1.0 / max(len(targets), 1)
        for sym in targets:
            if not ctx.can_trade(sym):
                continue
            closes = ctx.history(sym, "close", self.slow + 1)
            if len(closes) < self.slow:
                continue
            fast_ma = closes.tail(self.fast).mean()
            slow_ma = closes.tail(self.slow).mean()
            pos = ctx.get_position(sym)
            if fast_ma > slow_ma and pos.quantity == 0:
                ctx.order_target_percent(sym, weight, tag="golden_cross")
            elif fast_ma < slow_ma and pos.quantity > 0:
                ctx.order_target_percent(sym, 0.0, tag="death_cross")


class Momentum(Strategy):
    """动量策略: hold the top-N strongest stocks by trailing return."""

    name = "动量策略"

    def __init__(self, lookback: int = 60, top_n: int = 4, rebalance: str = "weekly") -> None:
        self.lookback = lookback
        self.top_n = top_n
        self.rebalance = rebalance

    def initialize(self, ctx: Context) -> None:
        ctx.schedule_function(self.rebalance_portfolio, self.rebalance)

    def rebalance_portfolio(self, ctx: Context) -> None:
        scores = {}
        for sym in ctx.universe:
            if not ctx.can_trade(sym):
                continue
            closes = ctx.history(sym, "close", self.lookback + 1)
            if len(closes) < self.lookback:
                continue
            ret = closes.iloc[-1] / closes.iloc[0] - 1.0
            scores[sym] = ret
        if not scores:
            return
        ranked = sorted(scores, key=scores.get, reverse=True)
        winners = [s for s in ranked if scores[s] > 0][: self.top_n]

        for sym in list(ctx.get_account()["positions"]):
            if sym not in winners and ctx.can_trade(sym):
                ctx.order_target_percent(sym, 0.0, tag="momentum_exit")

        weight = (1.0 / len(winners)) * 0.98 if winners else 0.0
        for sym in winners:
            ctx.order_target_percent(sym, weight, tag="momentum_enter")


class Reversal(Strategy):
    """反转策略: buy the biggest recent losers (mean reversion)."""

    name = "反转策略"

    def __init__(self, lookback: int = 20, top_n: int = 4, rebalance: str = "weekly") -> None:
        self.lookback = lookback
        self.top_n = top_n
        self.rebalance = rebalance

    def initialize(self, ctx: Context) -> None:
        ctx.schedule_function(self.rebalance_portfolio, self.rebalance)

    def rebalance_portfolio(self, ctx: Context) -> None:
        scores = {}
        for sym in ctx.universe:
            if not ctx.can_trade(sym):
                continue
            closes = ctx.history(sym, "close", self.lookback + 1)
            if len(closes) < self.lookback:
                continue
            scores[sym] = closes.iloc[-1] / closes.iloc[0] - 1.0
        if not scores:
            return
        losers = sorted(scores, key=scores.get)[: self.top_n]
        for sym in list(ctx.get_account()["positions"]):
            if sym not in losers and ctx.can_trade(sym):
                ctx.order_target_percent(sym, 0.0, tag="reversal_exit")
        weight = (1.0 / len(losers)) * 0.98 if losers else 0.0
        for sym in losers:
            ctx.order_target_percent(sym, weight, tag="reversal_enter")


class MultiFactor(Strategy):
    """多因子选股: rank by a blend of value (low PE/PB), quality (ROE) and
    momentum, then hold the top quantile equally weighted."""

    name = "多因子选股"

    def __init__(self, top_n: int = 4, lookback: int = 60, rebalance: str = "monthly") -> None:
        self.top_n = top_n
        self.lookback = lookback
        self.rebalance = rebalance

    def initialize(self, ctx: Context) -> None:
        ctx.schedule_function(self.rebalance_portfolio, self.rebalance)

    def _zscore(self, s: pd.Series) -> pd.Series:
        if s.std(ddof=0) == 0 or s.isna().all():
            return pd.Series(0.0, index=s.index)
        return (s - s.mean()) / (s.std(ddof=0) + 1e-9)

    def rebalance_portfolio(self, ctx: Context) -> None:
        tradable = [s for s in ctx.universe if ctx.can_trade(s)]
        if not tradable:
            return
        fund = ctx.get_fundamentals(tradable, fields=["pe", "pb", "roe"])
        mom = {}
        for sym in tradable:
            closes = ctx.history(sym, "close", self.lookback + 1)
            if len(closes) >= self.lookback:
                mom[sym] = closes.iloc[-1] / closes.iloc[0] - 1.0
        if fund.empty or not mom:
            return
        df = fund.reindex(tradable)
        df["mom"] = pd.Series(mom)
        df = df.dropna(subset=["pe", "pb", "roe", "mom"], how="all")
        # value: lower PE/PB better -> negate; quality & momentum: higher better
        score = (
            -self._zscore(df["pe"].astype(float))
            - self._zscore(df["pb"].astype(float))
            + self._zscore(df["roe"].astype(float))
            + self._zscore(df["mom"].astype(float))
        )
        winners = list(score.sort_values(ascending=False).head(self.top_n).index)
        for sym in list(ctx.get_account()["positions"]):
            if sym not in winners and ctx.can_trade(sym):
                ctx.order_target_percent(sym, 0.0, tag="factor_exit")
        weight = (1.0 / len(winners)) * 0.95 if winners else 0.0
        for sym in winners:
            ctx.order_target_percent(sym, weight, tag="factor_enter")


class GridTrading(Strategy):
    """网格交易: buy on dips and sell on rallies around a moving anchor."""

    name = "网格交易"

    def __init__(self, symbol: Optional[str] = None, grid_pct: float = 0.03, step_weight: float = 0.1) -> None:
        self.symbol = symbol
        self.grid_pct = grid_pct
        self.step_weight = step_weight
        self._anchor: Optional[float] = None

    def initialize(self, ctx: Context) -> None:
        if self.symbol is None:
            self.symbol = ctx.universe[0]
        ctx.set_universe([self.symbol])

    def handle_data(self, ctx: Context) -> None:
        if not ctx.can_trade(self.symbol):
            return
        px = ctx.current(self.symbol, "close")
        if px is None:
            return
        if self._anchor is None:
            self._anchor = px
            ctx.order_target_percent(self.symbol, 0.5, tag="grid_init")
            return
        change = px / self._anchor - 1.0
        pos = ctx.get_position(self.symbol)
        total = ctx.get_account()["total_value"]
        cur_w = pos.market_value / total if total else 0.0
        if change <= -self.grid_pct:
            ctx.order_target_percent(self.symbol, min(cur_w + self.step_weight, 0.95), tag="grid_buy")
            self._anchor = px
        elif change >= self.grid_pct:
            ctx.order_target_percent(self.symbol, max(cur_w - self.step_weight, 0.0), tag="grid_sell")
            self._anchor = px


class ETFRotation(Strategy):
    """ETF/行业轮动: rotate into the strongest momentum ETF/symbol."""

    name = "ETF轮动"

    def __init__(self, lookback: int = 20, rebalance: str = "weekly") -> None:
        self.lookback = lookback
        self.rebalance = rebalance

    def initialize(self, ctx: Context) -> None:
        ctx.schedule_function(self.rebalance_portfolio, self.rebalance)

    def rebalance_portfolio(self, ctx: Context) -> None:
        best, best_score = None, -np.inf
        for sym in ctx.universe:
            if not ctx.can_trade(sym):
                continue
            closes = ctx.history(sym, "close", self.lookback + 1)
            if len(closes) < self.lookback:
                continue
            score = closes.iloc[-1] / closes.iloc[0] - 1.0
            if score > best_score:
                best, best_score = sym, score
        for sym in list(ctx.get_account()["positions"]):
            if sym != best and ctx.can_trade(sym):
                ctx.order_target_percent(sym, 0.0, tag="rotation_exit")
        if best is not None and best_score > 0:
            ctx.order_target_percent(best, 0.95, tag="rotation_enter")


TEMPLATES = {
    "double_ma": DoubleMA,
    "momentum": Momentum,
    "reversal": Reversal,
    "multi_factor": MultiFactor,
    "grid": GridTrading,
    "etf_rotation": ETFRotation,
}
