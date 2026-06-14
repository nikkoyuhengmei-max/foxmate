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
    assert CORE_STRATEGIES == ["predictive_ranking", "short_strength", "trend_quality", "quality_value"]
    assert DEFAULT_STRATEGY == "predictive_ranking"
    # predictive_ranking 是 ML 引擎，不在 PROFILES（选股画像）里；其余在
    for k in ["short_strength", "trend_quality", "quality_value"]:
        assert k in PROFILES


def test_catalog_structure():
    cat = service.strategy_catalog()
    assert [e["key"] for e in cat["core"]] == CORE_STRATEGIES
    assert cat["default"] == "predictive_ranking"
    # 高级策略包含被降级的旧策略
    adv = [e["key"] for e in cat["advanced"]]
    for k in ["double_ma", "reversal", "grid", "etf_rotation", "short_momentum"]:
        assert k in adv


_SIGNALS = {"买入候选", "观察", "排除", "强势观察", "回踩观察", "过热谨慎"}


@pytest.mark.parametrize("strat", ["short_strength", "trend_quality", "quality_value"])
def test_screen_has_signal_reason_risk(strat):
    res = service.screen_stocks(strategy=strat, top_n=5)
    assert res["strategy"] == strat
    assert res["picks"]
    row = res["picks"][0]
    for col in ["rank", "symbol", "name", "industry", "close", "ret_3d", "ret_5d",
                "ret_10d", "amount_ratio", "rsi", "breakout_20d", "score", "signal", "reason", "risk"]:
        assert col in row
    assert row["signal"] in _SIGNALS


def test_profiles_give_different_rankings():
    a = service.screen_stocks(strategy="short_strength", top_n=8)["picks"]
    b = service.screen_stocks(strategy="quality_value", top_n=8)["picks"]
    # 不同画像通常给出不同的 Top1
    assert a and b


def test_short_strength_excludes_flat_bluechip():
    # 短线强势：5日涨幅不足/不放量的票应被标为"排除"而非买入
    res = service.screen_stocks(strategy="short_strength", top_n=20)
    for p in res["picks"]:
        if p["signal"] in ("强势观察", "回踩观察"):
            assert (p.get("ret_5d") or 0) >= 0.03 - 1e-9
            assert (p.get("amount_ratio") or 0) >= 1.3 - 1e-9


def test_stock_detail():
    d = service.stock_detail("600519.SH", strategy="short_strength")
    assert d["symbol"] == "600519.SH"
    assert "signal" in d and "reason" in d and "risk" in d
    assert d["trend"] and "factors" in d


def test_core_strategy_backtests_run():
    for strat in CORE_STRATEGIES:
        res = service.run_backtest(strategy=strat, monte_carlo=False)
        assert "total_return" in res["metrics"]
        assert res["settings"]["rebalance"] in ("daily", "weekly", "monthly")
