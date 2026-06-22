"""Multi-layer risk management: pre-trade, real-time and post-trade.

* **Pre-trade** (``check_order``): blocks orders that would breach position,
  concentration, order-size, holdings-count, liquidity or ST rules.
* **Real-time** (``monitor``): tracks drawdown and daily loss; can trigger a
  trading halt ("策略失控自动停机").
* **Post-trade** (``review``): execution-quality / slippage / turnover summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from aqs.config import RiskConfig, DEFAULT_CONFIG
from aqs.core.objects import Order, OrderSide, Portfolio, Trade


@dataclass
class RiskEvent:
    timestamp: pd.Timestamp
    kind: str
    message: str
    severity: str = "WARN"  # INFO / WARN / CRITICAL


class RiskManager:
    def __init__(self, config: RiskConfig = None, blacklist: Optional[List[str]] = None) -> None:
        self.cfg = config or DEFAULT_CONFIG.risk
        self.blacklist = set(blacklist or [])
        self.events: List[RiskEvent] = []
        self.halted = False
        self._peak_equity: float = 0.0
        self._day_start_equity: Optional[float] = None
        self._last_day: Optional[pd.Timestamp] = None

    # ----------------------------------------------------------- pre-trade
    def check_order(
        self, order: Order, portfolio: Portfolio, data, now: pd.Timestamp
    ) -> Tuple[bool, str]:
        if self.halted:
            return False, "风控已触发全局停机"

        sym = order.symbol
        if sym in self.blacklist:
            return False, "黑名单股票，禁止交易"

        if order.side == OrderSide.BUY:
            if self.cfg.forbid_st and data.is_st(sym):
                return False, "禁止买入 ST/风险警示 股票"

            px = data.current_price(sym, now, "close")
            if px is None:
                return False, "无可用行情，禁止下单"
            order_value = px * order.quantity
            total = portfolio.total_value or 1.0

            if order_value > self.cfg.max_order_value:
                return False, f"单笔下单金额 {order_value:,.0f} 超限"

            # resulting single-stock weight
            pos = portfolio.position(sym)
            new_weight = (pos.market_value + order_value) / total
            if new_weight > self.cfg.max_position_per_stock + 1e-9:
                return False, f"单票仓位 {new_weight:.0%} 超过上限 {self.cfg.max_position_per_stock:.0%}"

            # total position cap
            new_total_pos = (portfolio.positions_value + order_value) / total
            if new_total_pos > self.cfg.max_total_position + 1e-9:
                return False, f"总仓位 {new_total_pos:.0%} 超过上限 {self.cfg.max_total_position:.0%}"

            # holdings count
            n_pos = sum(1 for p in portfolio.positions.values() if p.quantity > 0)
            if pos.quantity == 0 and n_pos >= self.cfg.max_holdings:
                return False, f"持仓数量达到上限 {self.cfg.max_holdings}"

            # liquidity: order must be a small fraction of recent ADV
            adv = self._recent_adv(data, sym, now)
            if adv is not None and adv > 0 and order_value > self.cfg.min_adv_ratio * adv:
                return False, "流动性不足：下单金额超过近期日均成交额限制"

        return True, ""

    def _recent_adv(self, data, sym: str, now: pd.Timestamp, window: int = 20) -> Optional[float]:
        try:
            df = data.get_price(sym, end=now, fields=["amount"])
        except KeyError:
            return None
        amt = df["amount"].dropna().tail(window)
        if not len(amt):
            return None
        return float(amt.mean())

    # ----------------------------------------------------------- real-time
    def monitor(self, portfolio: Portfolio, now: pd.Timestamp, engine=None) -> None:
        equity = portfolio.total_value
        self._peak_equity = max(self._peak_equity, equity)

        day = now.normalize()
        if self._last_day != day:
            self._day_start_equity = equity
            self._last_day = day

        # max drawdown stop
        if self._peak_equity > 0:
            dd = 1 - equity / self._peak_equity
            if dd >= self.cfg.max_drawdown_stop and not self.halted:
                self.halted = True
                self._emit(now, "max_drawdown", f"回撤 {dd:.1%} 触发停机阈值 {self.cfg.max_drawdown_stop:.0%}", "CRITICAL")

        # intraday loss stop
        if self._day_start_equity:
            day_ret = equity / self._day_start_equity - 1
            if day_ret <= -self.cfg.max_daily_loss and not self.halted:
                self.halted = True
                self._emit(now, "daily_loss", f"当日亏损 {day_ret:.1%} 触发停机阈值 -{self.cfg.max_daily_loss:.0%}", "CRITICAL")

    def _emit(self, now: pd.Timestamp, kind: str, msg: str, severity: str) -> None:
        self.events.append(RiskEvent(timestamp=now, kind=kind, message=msg, severity=severity))

    # ----------------------------------------------------------- post-trade
    def review(self, trades: List[Trade], equity_curve: pd.Series) -> dict:
        if not trades:
            return {"n_trades": 0}
        buy_notional = sum(t.gross_value for t in trades if t.side == OrderSide.BUY)
        sell_notional = sum(t.gross_value for t in trades if t.side == OrderSide.SELL)
        total_cost = sum(t.total_cost for t in trades)
        avg_equity = float(equity_curve.mean()) if len(equity_curve) else 0.0
        turnover = (buy_notional + sell_notional) / (2 * avg_equity) if avg_equity else 0.0
        return {
            "n_trades": len(trades),
            "buy_notional": round(buy_notional, 2),
            "sell_notional": round(sell_notional, 2),
            "total_cost": round(total_cost, 2),
            "cost_ratio": round(total_cost / (buy_notional + sell_notional + 1e-9), 6),
            "turnover": round(turnover, 4),
            "n_risk_events": len(self.events),
            "halted": self.halted,
        }

    def events_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [{"timestamp": e.timestamp, "kind": e.kind, "severity": e.severity, "message": e.message} for e in self.events]
        )
