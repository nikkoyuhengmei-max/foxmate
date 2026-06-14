"""离线测试数据源适配器（不触网）：代码转换与优雅降级。"""

import importlib.util

import pytest

from aqs.data.market_data import MarketDataManager
from aqs.data.sources.akshare_source import _code, _index_code


def test_symbol_code_conversion():
    assert _code("600519.SH") == "600519"
    assert _code("300750.SZ") == "300750"


def test_index_code_conversion():
    assert _index_code("000300.SH") == "sh000300"
    assert _index_code("399006.SZ") == "sz399006"


def test_session_fallback_without_benchmark():
    """无基准时，交易日历回退为各标的日期并集。"""
    import pandas as pd
    from aqs.data.sample_data import generate_dataset

    ds = generate_dataset(end="2021-06-30")
    ds.benchmark = ds.benchmark.iloc[0:0]  # 清空基准，模拟取数失败
    mgr = MarketDataManager()
    mgr.load_dataset(ds)
    assert len(mgr.trading_dates()) > 0


@pytest.mark.skipif(
    importlib.util.find_spec("akshare") is None, reason="akshare 未安装"
)
def test_akshare_import_ok():
    from aqs.data.sources.akshare_source import AkShareDataSource

    assert AkShareDataSource is not None


@pytest.mark.skipif(
    importlib.util.find_spec("akshare") is not None, reason="akshare 已安装"
)
def test_akshare_graceful_without_install():
    with pytest.raises(ImportError):
        MarketDataManager.from_akshare(["600519.SH"], "2023-01-01", "2023-02-01")
