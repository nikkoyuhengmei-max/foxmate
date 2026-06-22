"""Trend forecasting models.

Provides :class:`TrendForecaster`, which estimates the probability that a symbol
rises over the next ``horizon`` days. It uses scikit-learn's gradient boosting
when available and otherwise falls back to a self-contained numpy logistic
regression, so the module works with or without the optional ``ml`` extra.

To avoid data leakage the train/test split is strictly chronological and all
features are causal (see :mod:`aqs.ml.features`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from aqs.ml.features import build_dataset, make_features

try:  # optional dependency
    from sklearn.ensemble import GradientBoostingClassifier  # type: ignore
    _HAS_SKLEARN = True
except Exception:  # pragma: no cover
    _HAS_SKLEARN = False


class _NumpyLogistic:
    """Tiny standardised logistic-regression (gradient descent)."""

    def __init__(self, lr: float = 0.1, epochs: int = 400, l2: float = 1e-3) -> None:
        self.lr, self.epochs, self.l2 = lr, epochs, l2
        self.w: Optional[np.ndarray] = None
        self.b = 0.0
        self.mu: Optional[np.ndarray] = None
        self.sigma: Optional[np.ndarray] = None

    def _standardize(self, X: np.ndarray) -> np.ndarray:
        return (X - self.mu) / self.sigma

    def fit(self, X: np.ndarray, y: np.ndarray) -> "_NumpyLogistic":
        self.mu = X.mean(axis=0)
        self.sigma = X.std(axis=0) + 1e-9
        Xs = self._standardize(X)
        n, d = Xs.shape
        self.w = np.zeros(d)
        self.b = 0.0
        for _ in range(self.epochs):
            z = Xs @ self.w + self.b
            p = 1 / (1 + np.exp(-z))
            grad_w = Xs.T @ (p - y) / n + self.l2 * self.w
            grad_b = float(np.mean(p - y))
            self.w -= self.lr * grad_w
            self.b -= self.lr * grad_b
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        z = self._standardize(X) @ self.w + self.b
        p = 1 / (1 + np.exp(-z))
        return np.column_stack([1 - p, p])


@dataclass
class ForecastResult:
    symbol: str
    horizon: int
    prob_up: float
    direction: str
    train_accuracy: float
    test_accuracy: float
    n_train: int
    n_test: int
    model: str
    feature_importance: Dict[str, float] = field(default_factory=dict)
    disclaimer: str = (
        "模型预测仅供研究参考，不构成投资建议。股价高度随机，任何模型都无法可靠预测"
        "未来价格；请结合风控使用。Past performance does not indicate future results."
    )

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "horizon": self.horizon,
            "prob_up": round(self.prob_up, 4),
            "direction": self.direction,
            "train_accuracy": round(self.train_accuracy, 4),
            "test_accuracy": round(self.test_accuracy, 4),
            "n_train": self.n_train,
            "n_test": self.n_test,
            "model": self.model,
            "disclaimer": self.disclaimer,
        }


class TrendForecaster:
    def __init__(self, horizon: int = 5, test_size: float = 0.3) -> None:
        self.horizon = horizon
        self.test_size = test_size
        self.model = None
        self.feature_names: List[str] = []
        self.model_name = "gbdt" if _HAS_SKLEARN else "logistic"

    def _new_model(self):
        if _HAS_SKLEARN:
            return GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.05)
        return _NumpyLogistic()

    def fit_predict(self, df: pd.DataFrame, symbol: str = "") -> ForecastResult:
        X, y = build_dataset(df, horizon=self.horizon, kind="classification")
        self.feature_names = list(X.columns)
        n = len(X)
        if n < 60:
            raise ValueError("not enough history to train a forecaster (need >= 60 rows)")

        split = int(n * (1 - self.test_size))
        Xtr, Xte = X.iloc[:split].values, X.iloc[split:].values
        ytr, yte = y.iloc[:split].values, y.iloc[split:].values

        self.model = self._new_model()
        self.model.fit(Xtr, ytr.astype(float) if not _HAS_SKLEARN else ytr)

        train_acc = self._accuracy(Xtr, ytr)
        test_acc = self._accuracy(Xte, yte)

        # Predict from the most recent fully-formed feature row.
        latest = make_features(df).dropna()
        prob_up = 0.5
        if len(latest):
            x_last = latest.iloc[[-1]][self.feature_names].values
            prob_up = float(self.model.predict_proba(x_last)[0, 1])

        importance = self._feature_importance()
        direction = "看涨(up)" if prob_up > 0.55 else "看跌(down)" if prob_up < 0.45 else "中性(neutral)"

        return ForecastResult(
            symbol=symbol,
            horizon=self.horizon,
            prob_up=prob_up,
            direction=direction,
            train_accuracy=train_acc,
            test_accuracy=test_acc,
            n_train=split,
            n_test=n - split,
            model=self.model_name,
            feature_importance=importance,
        )

    def _accuracy(self, X: np.ndarray, y: np.ndarray) -> float:
        if len(X) == 0:
            return float("nan")
        pred = (self.model.predict_proba(X)[:, 1] > 0.5).astype(int)
        return float((pred == y).mean())

    def _feature_importance(self) -> Dict[str, float]:
        if _HAS_SKLEARN and hasattr(self.model, "feature_importances_"):
            vals = self.model.feature_importances_
        elif hasattr(self.model, "w") and self.model.w is not None:
            vals = np.abs(self.model.w)
            vals = vals / (vals.sum() + 1e-12)
        else:
            return {}
        order = np.argsort(vals)[::-1]
        return {self.feature_names[i]: round(float(vals[i]), 4) for i in order[:8]}


def analyze_and_forecast(mdm, symbol: str, horizon: int = 5, lookback: int = 250) -> dict:
    """Analyze a symbol's recent price action and produce a trend forecast.

    Combines descriptive statistics (trend, volatility, drawdown, RSI) with a
    trained probability-of-up estimate. Returns a JSON-friendly dict including a
    risk disclaimer.
    """
    df = mdm.get_price(symbol)
    df = df.dropna(subset=["close"])
    if len(df) < 80:
        return {"symbol": symbol, "error": "历史数据不足，无法分析"}

    recent = df.tail(lookback)
    close = recent["close"].astype(float)
    ret = close.pct_change().dropna()
    cum_ret = float(close.iloc[-1] / close.iloc[0] - 1)
    ma20 = float(close.tail(20).mean())
    ma60 = float(close.tail(60).mean()) if len(close) >= 60 else float("nan")
    last = float(close.iloc[-1])
    dd = float((close / close.cummax() - 1).min())

    stats = {
        "last_price": round(last, 2),
        "lookback_return": round(cum_ret, 4),
        "annual_volatility": round(float(ret.std() * np.sqrt(252)), 4),
        "max_drawdown": round(dd, 4),
        "above_ma20": bool(last > ma20),
        "above_ma60": bool(last > ma60) if ma60 == ma60 else None,
        "trend": "上升" if last > ma20 > ma60 else "下降" if last < ma20 < ma60 else "震荡",
    }

    forecast: dict
    try:
        fr = TrendForecaster(horizon=horizon).fit_predict(df, symbol=symbol)
        forecast = fr.to_dict()
        forecast["feature_importance"] = fr.feature_importance
    except Exception as exc:  # pragma: no cover
        forecast = {"error": str(exc)}

    return {"symbol": symbol, "stats": stats, "forecast": forecast}
