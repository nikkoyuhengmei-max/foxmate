import pandas as pd
import pytest

from aqs.config import SystemConfig
from aqs.core.objects import OrderSide, Portfolio, Trade
from aqs.backtest.costs import CostModel
from aqs.backtest.engine import BacktestEngine
from aqs.data.market_data import MarketDataManager
from aqs.strategy.api import Strategy
from aqs.strategy.templates import DoubleMA


def test_cost_model_stamp_duty_on_sell_only():
    cm = CostModel(SystemConfig().cost)
    buy = cm.fees(OrderSide.BUY, 10.0, 1000)
    sell = cm.fees(OrderSide.SELL, 10.0, 1000)
    assert buy.stamp_duty == 0
    assert sell.stamp_duty > 0


def test_min_commission_applies():
    cm = CostModel(SystemConfig().cost)
    fees = cm.fees(OrderSide.BUY, 1.0, 100)  # tiny notional
    assert fees.commission == SystemConfig().cost.min_commission


def test_portfolio_t1_settlement():
    p = Portfolio(100000)
    t = Trade("O1", "600000.SH", OrderSide.BUY, 1000, 10.0, 5, 0, 0.1, pd.Timestamp("2021-01-04"))
    p.apply_trade(t)
    pos = p.position("600000.SH")
    assert pos.quantity == 1000
    assert pos.available == 0          # bought today -> not sellable
    p.settle()
    assert p.position("600000.SH").available == 1000


def test_backtest_runs_and_conserves_value():
    data = MarketDataManager.from_sample(end="2022-06-30")
    engine = BacktestEngine(data, DoubleMA(fast=5, slow=20), fill_mode="next_open")
    res = engine.run()
    assert len(res.equity_curve) > 0
    # no negative cash, equity finite and positive
    assert res.portfolio.cash >= -1e-6
    assert res.equity_curve.iloc[-1] > 0


def test_lot_size_enforced():
    data = MarketDataManager.from_sample(end="2022-06-30")

    class BuyOddLots(Strategy):
        name = "odd"
        def handle_data(self, ctx):
            sym = ctx.universe[0]
            if ctx.can_trade(sym) and ctx.get_position(sym).quantity == 0:
                ctx.order(sym, 137)  # not a multiple of 100

    engine = BacktestEngine(data, BuyOddLots(), fill_mode="close")
    res = engine.run()
    for t in res.trades:
        assert t.quantity % 100 == 0


def test_fill_modes_both_work():
    data = MarketDataManager.from_sample(end="2022-06-30")
    for mode in ("next_open", "close"):
        eng = BacktestEngine(data, DoubleMA(), fill_mode=mode)
        res = eng.run()
        assert res.equity_curve.iloc[-1] > 0
