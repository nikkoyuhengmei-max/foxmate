import pandas as pd
import pytest

from aqs.config import RiskConfig, ComplianceConfig
from aqs.core.objects import Order, OrderSide, OrderStatus, Trade
from aqs.compliance.audit import AuditLog
from aqs.compliance.filing import ProgramTradingFiling
from aqs.compliance.monitor import ComplianceMonitor
from aqs.risk.manager import RiskManager
from aqs.data.market_data import MarketDataManager


@pytest.fixture(scope="module")
def mdm():
    return MarketDataManager.from_sample(end="2022-06-30")


def test_risk_blocks_st_buy(mdm):
    from aqs.core.objects import Portfolio
    rm = RiskManager(RiskConfig(forbid_st=True))
    # 000002.SZ is flagged ST in the sample dataset
    when = mdm.trading_dates()[30]
    order = Order("000002.SZ", OrderSide.BUY, 100, created_at=when)
    ok, reason = rm.check_order(order, Portfolio(1e6), mdm, when)
    assert not ok and "ST" in reason


def test_risk_blocks_oversized_order(mdm):
    from aqs.core.objects import Portfolio
    rm = RiskManager(RiskConfig(max_order_value=1000))
    when = mdm.trading_dates()[30]
    order = Order("600000.SH", OrderSide.BUY, 100000, created_at=when)
    ok, reason = rm.check_order(order, Portfolio(1e9), mdm, when)
    assert not ok


def test_risk_drawdown_halt():
    from aqs.core.objects import Portfolio
    rm = RiskManager(RiskConfig(max_drawdown_stop=0.10))
    p = Portfolio(100000)
    rm.monitor(p, pd.Timestamp("2021-01-04"))
    p.cash = 80000  # -20% drawdown
    rm.monitor(p, pd.Timestamp("2021-01-05"))
    assert rm.halted
    assert any(e.kind == "max_drawdown" for e in rm.events)


def test_audit_log_hash_chain_detects_tampering():
    log = AuditLog()
    log.record("order", "submit", {"symbol": "600000.SH"})
    log.record("trade", "fill", {"symbol": "600000.SH", "qty": 100})
    assert log.verify()
    log._events[0].details["qty"] = 999  # tamper
    assert not log.verify()


def test_hft_threshold_flagging():
    cfg = ComplianceConfig(hft_orders_per_day=5, hft_orders_per_second=3)
    mon = ComplianceMonitor(cfg)
    when = pd.Timestamp("2025-07-07T09:30:00")
    for i in range(6):
        o = Order("600000.SH", OrderSide.BUY, 100, created_at=when)
        mon.on_order(o, when)
    s = mon.summary()
    assert s["hft_flagged"]
    assert any("高频" in a.message for a in mon.alerts)


def test_filing_required_before_live():
    mon = ComplianceMonitor(filing=ProgramTradingFiling())
    ok, reason = mon.can_go_live()
    assert not ok

    filing = ProgramTradingFiling(
        account_id="A1", account_name="张三", broker="X", capital_scale=1e6,
        products=["stock"], strategy_types=["trend"], software_version="0.1", filed=True,
    )
    mon2 = ComplianceMonitor(filing=filing)
    ok2, _ = mon2.can_go_live()
    assert ok2


def test_cancel_ratio_alert():
    mon = ComplianceMonitor(ComplianceConfig(high_cancel_ratio=0.5))
    when = pd.Timestamp("2025-07-07T09:30:00")
    for _ in range(30):
        o = Order("600000.SH", OrderSide.BUY, 100, created_at=when)
        mon.on_order(o, when)
        mon.on_cancel(o, when)
    mon.check_cancel_ratio(when)
    assert any(a.kind == "high_cancel_ratio" for a in mon.alerts)
