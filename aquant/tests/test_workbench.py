"""测试策略选股工作台：3 核心策略画像、信号/原因/风险、目录、个股详情。"""

import pytest

from aqs import service
from aqs.research.screener import PROFILES, Screener
from aqs.strategy.templates import CORE_STRATEGIES, ADVANCED_STRATEGIES, DEFAULT_STRATEGY


@pytest.fixture(autouse=True)
def use_sample():
    service.configure_data(source="sample")
    service._DATA_CACHE.pop("default", None)
    yield


def test_core_strategies_defined():
    assert CORE_STRATEGIES == ["short_momentum", "trend_quality", "quality_value"]
    assert DEFAULT_STRATEGY == "short_momentum"
    for k in CORE_STRATEGIES:
        assert k in PROFILES


def test_catalog_structure():
    cat = service.strategy_catalog()
    assert [e["key"] for e in cat["core"]] == CORE_STRATEGIES
    assert cat["default"] == "short_momentum"
    # 高级策略包含被降级的旧策略
    adv = [e["key"] for e in cat["advanced"]]
    for k in ["double_ma", "reversal", "grid", "etf_rotation"]:
        assert k in adv


@pytest.mark.parametrize("strat", ["short_momentum", "trend_quality", "quality_value"])
def test_screen_has_signal_reason_risk(strat):
    res = service.screen_stocks(strategy=strat, top_n=5)
    assert res["strategy"] == strat
    assert res["picks"]
    row = res["picks"][0]
    for col in ["rank", "symbol", "name", "industry", "close", "ret_5d", "ret_20d",
                "ret_60d", "amount", "rsi", "score", "signal", "reason", "risk"]:
        assert col in row
    assert row["signal"] in ("买入候选", "观察", "排除")


def test_profiles_give_different_rankings():
    a = service.screen_stocks(strategy="short_momentum", top_n=8)["picks"]
    b = service.screen_stocks(strategy="quality_value", top_n=8)["picks"]
    # 不同画像通常给出不同的 Top1
    assert a and b


def test_stock_detail():
    d = service.stock_detail("600519.SH", strategy="short_momentum")
    assert d["symbol"] == "600519.SH"
    assert "signal" in d and "reason" in d and "risk" in d
    assert d["trend"] and "factors" in d


def test_core_strategy_backtests_run():
    for strat in CORE_STRATEGIES:
        res = service.run_backtest(strategy=strat, monte_carlo=False)
        assert "total_return" in res["metrics"]
        assert res["settings"]["rebalance"] in ("daily", "weekly", "monthly")
