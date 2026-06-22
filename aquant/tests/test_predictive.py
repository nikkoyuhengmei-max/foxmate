"""测试预测上涨模型 predictive_ranking。"""

import pytest

from aqs import service
from aqs.data.market_data import MarketDataManager
from aqs.ml.predictive import predict_universe, HORIZONS
from aqs.strategy.templates import CORE_STRATEGIES, DEFAULT_STRATEGY


@pytest.fixture(autouse=True)
def use_sample():
    service.configure_data(source="sample", demo_mode=False)
    service._DATA_CACHE.pop("default", None)
    yield


def test_default_is_predictive():
    assert DEFAULT_STRATEGY == "predictive_ranking"
    assert CORE_STRATEGIES[0] == "predictive_ranking"


def test_predict_universe_columns_and_ranges():
    mdm = MarketDataManager.from_sample(end="2023-12-31")
    df = predict_universe(mdm, top_n=8)
    assert not df.empty
    for col in ["prob_up_3d", "prob_up_5d", "prob_up_10d", "expected_return_5d",
                "final_score", "signal", "reason", "risk", "money_score", "tech_score", "risk_score"]:
        assert col in df.columns
    for c in ["prob_up_3d", "prob_up_5d", "prob_up_10d"]:
        assert df[c].between(0, 1).all()
    assert df["signal"].isin(["高潜力观察", "谨慎观察", "等待回调", "过热风险", "排除"]).all()


def test_predict_excludes_delisted():
    mdm = MarketDataManager.from_sample(end="2023-12-31")
    df = predict_universe(mdm, top_n=30)
    assert "000003.SZ" not in df.index   # 退市股不应出现


def test_screen_predictive_via_service():
    res = service.screen_stocks(strategy="predictive_ranking", top_n=5)
    assert res["strategy"] == "predictive_ranking"
    assert res["strategy_name"] == "预测上涨模型"
    assert res["picks"]
    assert "prob_up_5d" in res["picks"][0]


def test_predict_symbol_service():
    r = service.predict_symbol("600519.SH")
    assert r["success"] is True
    assert r["symbol"] == "600519.SH"
    assert "prob_up_5d" in r["prediction"]


def test_predict_symbol_unknown():
    r = service.predict_symbol("不存在xyz")
    assert r["success"] is False
    assert "未找到" in r["error"]
