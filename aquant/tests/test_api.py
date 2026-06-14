"""测试 Web API 关键路由（含选股运行接口与健康检查）。"""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from aqs import service
from aqs.api.server import create_app


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(service, "OUTPUTS_DIR", str(tmp_path / "outputs"))
    service.configure_data(source="sample")
    service._DATA_CACHE.pop("default", None)
    return TestClient(create_app())


def test_health_lists_routes(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert "/api/screen/run" in h["available_routes"]
    assert "data_source" in h


def test_screen_run_success(client):
    r = client.post("/api/screen/run", json={"strategy": "short_strength", "top": 5,
                                             "exclude_large_cap": True, "use_cache": True}).json()
    assert r["success"] is True
    assert r["strategy"] == "short_strength"
    assert "asof_date" in r and "data_source" in r and "elapsed_seconds" in r
    assert isinstance(r["results"], list)


def test_screen_run_unknown_strategy(client):
    r = client.post("/api/screen/run", json={"strategy": "does_not_exist"}).json()
    assert r["success"] is False
    assert "未实现" in r["error"]


def test_forecast_run_success_for_known(client):
    r = client.post("/api/forecast/run", json={"symbol": "600519"}).json()
    assert r["success"] is True
    assert r["symbol"] == "600519.SH"      # 自动补全交易所
    assert r.get("name")
    assert "forecast" in r


def test_forecast_run_unknown_no_500(client):
    resp = client.post("/api/forecast/run", json={"symbol": "不存在xyz"})
    assert resp.status_code == 200          # 失败也不返回 500
    body = resp.json()
    assert body["success"] is False
    assert body["error"] == "未找到该股票代码或名称。"


def test_normalize_symbol():
    from aqs import service
    assert service.normalize_symbol("600519") == "600519.SH"
    assert service.normalize_symbol("300167") == "300167.SZ"
    assert service.normalize_symbol("000001") == "000001.SZ"


def test_strategies_catalog_not_empty(client):
    cat = client.get("/api/strategies/catalog").json()
    assert [e["key"] for e in cat["core"]] == ["short_strength", "trend_quality", "quality_value"]
    assert cat["core"][0]["name"] == "短线强势股"


def test_no_mock_fallback_on_real_source_failure(monkeypatch):
    """真实数据源失败时不得回退到示例数据，应抛 DataSourceError。"""
    from aqs.data.market_data import MarketDataManager

    service.configure_data(source="baostock", demo_mode=False)
    service._DATA_CACHE.pop("default", None)

    def boom(*a, **k):
        raise RuntimeError("登录失败/网络不可用")

    monkeypatch.setattr(MarketDataManager, "from_baostock", classmethod(lambda cls, *a, **k: boom()))
    with pytest.raises(service.DataSourceError):
        service.get_data_manager(refresh=True)
    # 状态接口应报告错误而非伪装成功
    st = service.data_status()
    assert st["is_real_data"] is False and st["using_mock"] is False and st["error"]
    service.configure_data(source="sample", demo_mode=False)
    service._DATA_CACHE.pop("default", None)


def test_demo_mode_allows_mock(monkeypatch):
    service.configure_data(source="baostock", demo_mode=True)
    service._DATA_CACHE.pop("default", None)
    mgr = service.get_data_manager(refresh=True)
    assert mgr.symbols  # 演示模式下允许示例数据
    assert service._ACTUAL["using_mock"] is True
    service.configure_data(source="sample", demo_mode=False)
    service._DATA_CACHE.pop("default", None)


def test_data_check_structure(client):
    d = client.get("/api/data/check").json()
    for k in ["baostock_import", "baostock_login", "baostock_sample_ok",
              "akshare_import", "akshare_sample_ok", "using_mock", "error"]:
        assert k in d
