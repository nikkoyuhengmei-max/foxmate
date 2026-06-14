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


def test_strategies_catalog_not_empty(client):
    cat = client.get("/api/strategies/catalog").json()
    assert [e["key"] for e in cat["core"]] == ["short_strength", "trend_quality", "quality_value"]
    assert cat["core"][0]["name"] == "短线强势股"
