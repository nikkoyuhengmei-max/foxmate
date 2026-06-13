import pandas as pd
import pytest

from aqs.core.objects import Order, OrderSide, OrderStatus
from aqs.data.market_data import MarketDataManager
from aqs.strategy.templates import DoubleMA
from aqs.trading.broker import SimulatedBroker
from aqs.trading.ems import ExecutionManagementSystem
from aqs.trading.oms import OrderManagementSystem
from aqs.trading.trader import PaperTrader
from aqs.compliance.monitor import ComplianceMonitor
from aqs.compliance.filing import ProgramTradingFiling
from aqs.risk.manager import RiskManager


@pytest.fixture
def mdm():
    # function-scoped: SimulatedBroker.set_time pins the PIT clock, so each test
    # gets a fresh manager to avoid cross-test state leakage.
    return MarketDataManager.from_sample(end="2022-06-30")


def test_oms_duplicate_protection(mdm):
    t = mdm.trading_dates()[30]
    broker = SimulatedBroker(mdm); broker.connect(); broker.set_time(t)
    oms = OrderManagementSystem(broker, dedup_window_seconds=2)
    o1 = Order("600000.SH", OrderSide.BUY, 100, created_at=t)
    o2 = Order("600000.SH", OrderSide.BUY, 100, created_at=t)
    oms.submit(o1); oms.submit(o2)
    assert o2.status == OrderStatus.REJECTED and "重复" in o2.reason


def test_oms_kill_switch(mdm):
    dates = mdm.trading_dates()
    broker = SimulatedBroker(mdm); broker.connect(); broker.set_time(dates[30])
    oms = OrderManagementSystem(broker)
    oms.engage_kill_switch()
    o = Order("600000.SH", OrderSide.BUY, 100, created_at=dates[31])
    oms.submit(o)
    assert o.status == OrderStatus.REJECTED


def test_ems_twap_conserves_total():
    ems = ExecutionManagementSystem(lot_size=100)
    children = ems.twap("600000.SH", OrderSide.BUY, 1000, slices=4)
    assert sum(o.quantity for o in children) == 1000


def test_ems_iceberg_display_cap():
    ems = ExecutionManagementSystem(lot_size=100)
    children = ems.iceberg("600000.SH", OrderSide.BUY, 1000, display_qty=300)
    assert all(o.quantity <= 400 for o in children)
    assert sum(o.quantity for o in children) == 1000


def test_paper_trader_runs(mdm):
    pt = PaperTrader(mdm, DoubleMA(fast=5, slow=20), risk_manager=RiskManager(),
                     compliance=ComplianceMonitor())
    eq = pt.run()
    assert len(eq) > 0 and eq.iloc[-1] > 0


def test_live_blocked_without_filing(mdm):
    pt = PaperTrader(mdm, DoubleMA(), compliance=ComplianceMonitor(filing=ProgramTradingFiling()), live=True)
    with pytest.raises(PermissionError):
        pt.run()
