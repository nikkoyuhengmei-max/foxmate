"""测试全市场目录、搜索、代码解析、自选股、任意股票预测。"""

import os

import pytest

from aqs import service
from aqs.data import directory as dr


@pytest.fixture(autouse=True)
def sample_and_tmpcwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)          # data/watchlist.csv 写入临时目录
    dr._DIR_CACHE = None
    service.configure_data(source="sample")
    service._DATA_CACHE.pop("default", None)
    yield
    dr._DIR_CACHE = None


def test_normalize_code():
    assert dr.normalize_code("600519") == "600519.SH"
    assert dr.normalize_code("600519.SH") == "600519.SH"
    assert dr.normalize_code("sh.600519") == "600519.SH"
    assert dr.normalize_code("000001") == "000001.SZ"
    assert dr.normalize_code("贵州茅台") is None


def test_search_by_code():
    res = service.search_stocks("600519", limit=5)
    assert any(r["symbol"] == "600519.SH" for r in res)


def test_resolve_code():
    assert dr.resolve("600519") == "600519.SH"
    assert dr.resolve("600519.SH") == "600519.SH"


def test_watchlist_add_remove():
    assert service.add_to_watchlist("600519.SH")["ok"]
    assert any(r["symbol"] == "600519.SH" for r in service.watchlist())
    service.remove_from_watchlist("600519.SH")
    assert not any(r["symbol"] == "600519.SH" for r in service.watchlist())


def test_watchlist_unknown_rejected():
    r = service.add_to_watchlist("这不是股票xyz")
    assert r["ok"] is False
    assert r["message"] == "未找到该股票代码或名称"


def test_forecast_unknown_returns_error():
    r = service.forecast_symbol("不存在的股票xyz")
    assert r.get("error") == "未找到该股票代码或名称"


def test_forecast_by_code_sample():
    r = service.forecast_symbol("600519.SH")
    assert "error" not in r or r.get("error") is None
    assert r.get("name")
