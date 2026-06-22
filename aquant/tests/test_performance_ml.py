import numpy as np
import pandas as pd

from aqs.data.market_data import MarketDataManager
from aqs.performance.metrics import analyze, max_drawdown
from aqs.performance.robustness import walk_forward_windows, monte_carlo_drawdown
from aqs.ml.features import build_dataset, make_features
from aqs.ml.forecast import TrendForecaster, analyze_and_forecast


def test_max_drawdown_simple():
    eq = pd.Series([100, 120, 90, 110], index=pd.date_range("2021-01-01", periods=4))
    mdd, _, _ = max_drawdown(eq)
    assert abs(mdd - (-0.25)) < 1e-9


def test_analyze_metrics_keys():
    idx = pd.date_range("2021-01-01", periods=250, freq="B")
    rng = np.random.default_rng(0)
    eq = pd.Series(100000 * np.cumprod(1 + rng.normal(0.0005, 0.01, 250)), index=idx)
    bench = pd.Series(100000 * np.cumprod(1 + rng.normal(0.0003, 0.009, 250)), index=idx)
    rep = analyze(eq, bench)
    for k in ["total_return", "annual_return", "sharpe", "max_drawdown", "alpha", "beta", "information_ratio"]:
        assert k in rep.metrics


def test_walk_forward_windows():
    sessions = pd.date_range("2020-01-01", periods=600, freq="B")
    w = walk_forward_windows(sessions, train=252, test=63, step=63)
    assert len(w) >= 1
    assert w[0]["train_end"] < w[0]["test_start"]


def test_monte_carlo_keys():
    rng = np.random.default_rng(0)
    rets = pd.Series(rng.normal(0.0005, 0.01, 300))
    mc = monte_carlo_drawdown(rets, n_paths=200)
    assert "mc_prob_loss" in mc and 0 <= mc["mc_prob_loss"] <= 1


def test_ml_no_leakage_and_predicts():
    data = MarketDataManager.from_sample(end="2022-12-31")
    df = data.get_price("600519.SH").dropna(subset=["close"])
    X, y = build_dataset(df, horizon=5)
    assert len(X) == len(y) and not X.isna().any().any()
    fr = TrendForecaster(horizon=5).fit_predict(df, "600519.SH")
    assert 0.0 <= fr.prob_up <= 1.0
    assert fr.n_train > fr.n_test  # chronological split


def test_analyze_and_forecast_has_disclaimer():
    data = MarketDataManager.from_sample(end="2022-12-31")
    res = analyze_and_forecast(data, "600519.SH")
    assert "stats" in res
    assert "disclaimer" in res["forecast"]
