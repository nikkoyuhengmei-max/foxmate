"""测试新增功能：行业映射、新策略、选股/回测导出、数据状态、成交记录。"""

import os

import pytest

from aqs import service
from aqs.data.industry import industry_of, fill_missing
from aqs.strategy.templates import TEMPLATES


@pytest.fixture(autouse=True)
def use_sample(tmp_path, monkeypatch):
    # 全部用示例数据，离线、可重复；输出目录指向临时目录
    monkeypatch.setattr(service, "OUTPUTS_DIR", str(tmp_path / "outputs"))
    service.configure_data(source="sample")
    yield
    service._DATA_CACHE.pop("default", None)


def test_industry_map_lookup():
    assert industry_of("000001.SZ") == "银行"
    assert industry_of("600519.SH") == "白酒"
    assert industry_of("999999.SZ") == "未分类"


def test_fill_missing_only_when_empty():
    assert fill_missing("家电", "000001.SZ") == "家电"   # 已有则不覆盖
    assert fill_missing("未分类", "000001.SZ") == "银行"  # 缺失才补


def test_all_new_strategies_registered():
    for key in ["buy_and_hold", "double_ma", "low_volatility", "dividend_value",
                "momentum_20_60", "multi_factor_v2"]:
        assert key in TEMPLATES


@pytest.mark.parametrize("strat", ["buy_and_hold", "low_volatility", "dividend_value",
                                    "momentum_20_60", "multi_factor_v2"])
def test_new_strategies_run(strat):
    res = service.run_backtest(strategy=strat, monte_carlo=False)
    assert "metrics" in res and "total_return" in res["metrics"]


def test_screen_export(tmp_path):
    res = service.screen_stocks(top_n=5, save=True)
    assert res["saved"] and os.path.exists(res["saved"])
    assert res["picks"]
    # 行业列存在
    assert "industry" in res["picks"][0]


def test_backtest_export_html_csv():
    res = service.run_backtest(strategy="multi_factor", save=True, monte_carlo=False)
    saved = res["saved"]
    assert os.path.exists(saved["csv"]) and os.path.exists(saved["html"])
    with open(saved["html"], encoding="utf-8") as fh:
        assert "回测报告" in fh.read()


def test_data_status_keys():
    st = service.data_status()
    for k in ["actual_source", "is_real_data", "data_date", "system_time", "n_symbols"]:
        assert k in st


def test_recent_trades_empty_when_no_records():
    res = service.recent_trades()
    assert res["has_records"] is False
    assert res["message"] == "暂无真实成交记录"


def test_max_position_applied():
    # 单只 5% 上限 -> 多因子(默认权重更高)应被风控拦截，成交减少但仍能运行
    res = service.run_backtest(strategy="multi_factor", max_position=0.05, monte_carlo=False)
    assert "metrics" in res
