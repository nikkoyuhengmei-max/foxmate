"""Abnormal-trading & program-trading frequency monitor.

Counts declarations (orders) and cancellations per second and per day and warns /
flags when approaching the exchange HFT identification thresholds (configurable;
defaults follow the publicly disclosed standard: peak >= 300 orders+cancels per
second, or >= 20000 per day for a single account). Also watches cancel ratio and
records everything to the audit log.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from aqs.config import ComplianceConfig, DEFAULT_CONFIG
from aqs.compliance.audit import AuditLog
from aqs.compliance.filing import ProgramTradingFiling
from aqs.core.objects import Order, Trade


@dataclass
class ComplianceAlert:
    timestamp: str
    kind: str
    message: str
    severity: str = "WARN"


class ComplianceMonitor:
    def __init__(
        self,
        config: ComplianceConfig = None,
        audit: Optional[AuditLog] = None,
        filing: Optional[ProgramTradingFiling] = None,
    ) -> None:
        self.cfg = config or DEFAULT_CONFIG.compliance
        self.audit = audit or AuditLog()
        self.filing = filing
        self.alerts: List[ComplianceAlert] = []

        self._per_second: Dict[str, int] = defaultdict(int)   # 'YYYY-mm-ddTHH:MM:SS' -> count
        self._per_day: Dict[str, int] = defaultdict(int)      # 'YYYY-mm-dd' -> count
        self.orders_count = 0
        self.cancels_count = 0
        self.trades_count = 0

    # -------------------------------------------------------- live gating
    def can_go_live(self) -> tuple[bool, str]:
        """Enforce 先报告、后交易 before any live trading begins."""
        if not self.cfg.require_filing_before_live:
            return True, ""
        if self.filing is None or not self.filing.filed:
            return False, "实盘前必须完成程序化交易报备（先报告、后交易）"
        missing = self.filing.missing_fields()
        if missing:
            return False, f"报备信息不完整，缺少字段: {', '.join(missing)}"
        return True, ""

    # --------------------------------------------------------------- hooks
    def _bump(self, when, weight: int = 1) -> None:
        ts = pd.Timestamp(when)
        sec = ts.strftime("%Y-%m-%dT%H:%M:%S")
        day = ts.strftime("%Y-%m-%d")
        self._per_second[sec] += weight
        self._per_day[day] += weight
        self._check_thresholds(ts, sec, day)

    def on_order(self, order: Order, when, rejected: bool = False) -> None:
        self.orders_count += 1
        self.audit.record(
            "order",
            "submit" if not rejected else "reject",
            {"order_id": order.order_id, "symbol": order.symbol, "side": order.side.value,
             "qty": order.quantity, "tag": order.tag, "reason": order.reason},
            timestamp=when,
        )
        # rejected orders are not sent to the exchange; don't count toward freq
        if not rejected:
            self._bump(when, 1)

    def on_cancel(self, order: Order, when) -> None:
        self.cancels_count += 1
        self.audit.record(
            "order", "cancel",
            {"order_id": order.order_id, "symbol": order.symbol, "reason": order.reason},
            timestamp=when,
        )
        self._bump(when, 1)

    def on_trade(self, trade: Trade) -> None:
        self.trades_count += 1
        self.audit.record(
            "trade", "fill",
            {"order_id": trade.order_id, "symbol": trade.symbol, "side": trade.side.value,
             "qty": trade.quantity, "price": trade.price, "cost": trade.total_cost, "tag": trade.tag},
            timestamp=trade.timestamp,
        )

    def record_manual(self, action: str, details: dict, when=None) -> None:
        self.audit.record("manual", action, details, timestamp=when)

    # ---------------------------------------------------------- thresholds
    def _check_thresholds(self, ts: pd.Timestamp, sec: str, day: str) -> None:
        warn_at = self.cfg.warn_at_pct_of_threshold
        ps = self._per_second[sec]
        pd_ = self._per_day[day]

        if ps >= self.cfg.hft_orders_per_second:
            self._alert(ts, "hft_per_second", f"每秒申报+撤单 {ps} 达到高频认定阈值 {self.cfg.hft_orders_per_second}", "CRITICAL")
        elif ps >= warn_at * self.cfg.hft_orders_per_second:
            self._alert(ts, "hft_per_second_warn", f"每秒申报+撤单 {ps} 接近高频阈值", "WARN")

        if pd_ >= self.cfg.hft_orders_per_day:
            self._alert(ts, "hft_per_day", f"全日申报+撤单 {pd_} 达到高频认定阈值 {self.cfg.hft_orders_per_day}", "CRITICAL")
        elif pd_ >= warn_at * self.cfg.hft_orders_per_day:
            self._alert(ts, "hft_per_day_warn", f"全日申报+撤单 {pd_} 接近高频阈值", "WARN")

    @property
    def cancel_ratio(self) -> float:
        denom = self.orders_count
        return self.cancels_count / denom if denom else 0.0

    def check_cancel_ratio(self, when=None) -> None:
        if self.cancel_ratio >= self.cfg.high_cancel_ratio and self.orders_count >= 20:
            self._alert(pd.Timestamp(when) if when else pd.Timestamp.utcnow(),
                        "high_cancel_ratio",
                        f"撤单比例 {self.cancel_ratio:.0%} 超过预警阈值 {self.cfg.high_cancel_ratio:.0%}",
                        "WARN")

    def _alert(self, ts: pd.Timestamp, kind: str, message: str, severity: str) -> None:
        # de-duplicate identical consecutive alerts of same kind within same second
        alert = ComplianceAlert(timestamp=str(ts), kind=kind, message=message, severity=severity)
        if self.alerts and self.alerts[-1].kind == kind and self.alerts[-1].timestamp == alert.timestamp:
            return
        self.alerts.append(alert)
        self.audit.record("compliance", kind, {"message": message, "severity": severity}, timestamp=ts)

    # ------------------------------------------------------------ reporting
    def summary(self) -> dict:
        peak_second = max(self._per_second.values()) if self._per_second else 0
        peak_day = max(self._per_day.values()) if self._per_day else 0
        return {
            "orders": self.orders_count,
            "cancels": self.cancels_count,
            "trades": self.trades_count,
            "cancel_ratio": round(self.cancel_ratio, 4),
            "peak_orders_per_second": peak_second,
            "peak_orders_per_day": peak_day,
            "hft_flagged": peak_second >= self.cfg.hft_orders_per_second or peak_day >= self.cfg.hft_orders_per_day,
            "n_alerts": len(self.alerts),
            "audit_events": len(self.audit),
            "audit_valid": self.audit.verify(),
        }

    def alerts_frame(self) -> pd.DataFrame:
        return pd.DataFrame([{"timestamp": a.timestamp, "kind": a.kind, "severity": a.severity, "message": a.message} for a in self.alerts])
