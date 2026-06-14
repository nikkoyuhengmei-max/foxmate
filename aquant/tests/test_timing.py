"""测试短线选股时间模式（研究/模拟，无真实下单）。"""

import pytest

from aqs import service


@pytest.fixture(autouse=True)
def use_sample(tmp_path, monkeypatch):
    monkeypatch.setattr(service, "OUTPUTS_DIR", str(tmp_path / "outputs"))
    service.configure_data(source="sample")
    service._DATA_CACHE.pop("default", None)
    yield


def test_current_mode_structure():
    cm = service.current_mode()
    for k in ["suggested", "advice", "system_time", "modes", "disclaimer", "is_trading_day"]:
        assert k in cm
    keys = [m["key"] for m in cm["modes"]]
    assert keys == ["after_close", "auction_confirm", "open_confirm", "close_review"]
    assert "不构成投资建议" in cm["disclaimer"]


def test_after_close_builds_watch_pool():
    res = service.run_mode("after_close", top_n=5)
    assert res["mode"] == "after_close"
    assert "明日观察池" in res["title"]
    assert res["picks"]
    pool = service.load_watch_pool()
    assert pool["kind"] == "明日观察池"
    assert pool["symbols"]


def test_close_review_intraday_strength():
    res = service.run_mode("close_review", top_n=5)
    assert res["mode"] == "close_review"
    for p in res["picks"]:
        assert p.get("intraday_strength") is not None and p["intraday_strength"] >= 0.5


def test_auction_confirm_unsupported_without_realtime():
    service.run_mode("after_close", top_n=5)  # 先建池
    res = service.run_mode("auction_confirm")
    # 示例数据源无竞价数据 -> 明确不支持
    assert res["supported"] is False
    assert "不支持竞价确认" in res["message"]


def test_open_confirm_no_realtime_advice_only():
    service.run_mode("after_close", top_n=5)
    res = service.run_mode("open_confirm")
    assert res["realtime"] is False
    assert "advice" in res  # 只给操作建议，不生成买入信号


def test_auction_without_pool_message():
    res = service.run_mode("auction_confirm")
    assert "观察池" in res["message"]
