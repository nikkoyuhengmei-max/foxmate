"""测试舆情/关注度因子（含 mock 仅演示模式、不泄露到真实模式）。"""

import pytest

from aqs import service
from aqs.sentiment.keywords import analyze_text
from aqs.sentiment.provider import get_provider, MockProvider, NullProvider
from aqs.sentiment.engine import SentimentEngine


@pytest.fixture(autouse=True)
def sample_tmp(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)          # 舆情缓存写入临时目录
    service.configure_data(source="sample", demo_mode=False)
    service._DATA_CACHE.pop("default", None)
    yield
    service.configure_data(demo_mode=False)


def test_analyze_text_keywords():
    r = analyze_text(["公司获大额订单中标，业绩增长", "收到交易所问询函，涉嫌违规"])
    assert "中标" in r["positive_keywords"]
    assert "问询函" in r["risk_keywords"]
    assert -1 <= r["sentiment_score"] <= 1


def test_mock_only_in_demo():
    assert isinstance(get_provider("auto", demo_mode=False), NullProvider)
    assert isinstance(get_provider("auto", demo_mode=True), MockProvider)
    assert isinstance(get_provider("mock", demo_mode=False), NullProvider)   # mock 不在非演示模式启用


def test_engine_demo_has_data_real_na():
    demo = SentimentEngine(source="auto", demo_mode=True)
    recs, meta = demo.get_sentiment(["600519.SH", "000001.SZ"], names={"600519.SH": "贵州茅台"})
    assert meta["is_mock"] is True and meta["available"] is True
    assert "attention_score" in recs["600519.SH"]

    real = SentimentEngine(source="auto", demo_mode=False)
    recs2, meta2 = real.get_sentiment(["600519.SH"])
    assert meta2["available"] is False and recs2 == {}


def test_screen_use_sentiment_demo_labeled_mock():
    service.configure_data(demo_mode=True)
    service._DATA_CACHE.pop("default", None)
    res = service.screen_stocks(strategy="short_strength", top_n=5, use_sentiment=True)
    assert res["use_sentiment"] is True
    assert res["sentiment_meta"]["is_mock"] is True
    assert any("sent_signal" in p for p in res["picks"])


def test_mock_sentiment_not_leak_to_real():
    # 先在演示模式产生 mock 缓存
    service.configure_data(demo_mode=True)
    service._DATA_CACHE.pop("default", None)
    service.screen_stocks(strategy="short_strength", top_n=3, use_sentiment=True)
    # 切回真实模式：不得读到 mock 舆情
    service.configure_data(demo_mode=False)
    service._DATA_CACHE.pop("default", None)
    sf = service.sentiment_for("600519.SH")
    assert sf["available"] is False
