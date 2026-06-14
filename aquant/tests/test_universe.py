"""测试股票池加载：默认池足够大、来源追踪、<50 异常报错、不回退小样本池。"""

import pytest

from aqs import service


@pytest.fixture(autouse=True)
def use_sample():
    service.configure_data(source="sample", demo_mode=False)
    service._DATA_CACHE.pop("default", None)
    yield


def test_default_pool_is_large():
    assert len(service.DATA_CFG["symbols"]) >= 50


def test_load_universe_default_and_custom():
    d = service.load_universe("default")
    assert d["source"] == "default" and d["size"] >= 50
    c = service.load_universe(["600519.SH", "000001.SZ"])
    assert c["source"] == "custom" and c["size"] == 2


def test_load_universe_meta_fields():
    info = service.load_universe("watchlist")
    for k in ["name", "source", "size", "symbols", "cache_file", "updated_at", "error"]:
        assert k in info


def test_index_universe_below_50_errors(monkeypatch):
    # 模拟成分获取失败/数量异常：load_universe 返回 <50
    def fake_load(name, source=None, use_cache=True):
        if str(name).lower() == "hs300":
            return {"name": "hs300", "source": "none", "symbols": ["600519.SH"], "size": 1,
                    "cache_file": None, "updated_at": None, "error": None}
        return {"name": "default", "source": "default", "symbols": list(service.DATA_CFG["symbols"]),
                "size": len(service.DATA_CFG["symbols"]), "cache_file": None, "updated_at": None, "error": None}

    monkeypatch.setattr(service, "load_universe", fake_load)
    res = service.screen_stocks(strategy="short_strength", top_n=5, universe="hs300")
    assert res.get("error") and "数量异常" in res["error"]
    assert res["picks"] == []


def test_index_universe_hard_error_no_fallback(monkeypatch):
    def fake_load(name, source=None, use_cache=True):
        return {"name": "hs300", "source": "none", "symbols": [], "size": 0,
                "cache_file": None, "updated_at": None, "error": "获取 hs300 成分失败（数据源不可用）"}

    monkeypatch.setattr(service, "load_universe", fake_load)
    res = service.screen_stocks(strategy="short_strength", top_n=5, universe="hs300")
    assert res.get("error") and "失败" in res["error"]
    assert res["picks"] == []
