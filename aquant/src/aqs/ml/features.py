"""Technical feature engineering.

All features are causal: every value at row ``t`` uses only information available
at-or-before ``t`` (no look-ahead). The prediction target is built by *shifting
returns forward*, and any row whose target is unknown is dropped.
"""

from __future__ import annotations

from typing import List

import numpy as np
import pandas as pd


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / (loss + 1e-12)
    return 100 - 100 / (1 + rs)


def make_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build a causal feature matrix from an OHLCV bar frame."""
    out = pd.DataFrame(index=df.index)
    close = df["close"].astype(float)
    ret1 = close.pct_change()

    out["ret_1"] = ret1
    out["ret_5"] = close.pct_change(5)
    out["ret_10"] = close.pct_change(10)
    out["ret_20"] = close.pct_change(20)
    out["ma5_ratio"] = close / close.rolling(5).mean() - 1
    out["ma10_ratio"] = close / close.rolling(10).mean() - 1
    out["ma20_ratio"] = close / close.rolling(20).mean() - 1
    out["vol_10"] = ret1.rolling(10).std()
    out["vol_20"] = ret1.rolling(20).std()
    out["rsi_14"] = _rsi(close, 14) / 100.0
    out["mom_20"] = close / close.shift(20) - 1
    out["hl_range"] = (df["high"] - df["low"]) / close
    if "volume" in df:
        vol = df["volume"].astype(float)
        out["vol_chg_5"] = vol / vol.rolling(5).mean() - 1
    return out


def make_target(df: pd.DataFrame, horizon: int = 5, kind: str = "classification") -> pd.Series:
    """Forward return target (shifted backward so each row predicts the future).

    ``classification`` -> 1 if future ``horizon``-day return > 0 else 0.
    ``regression``     -> the future ``horizon``-day return itself.
    """
    close = df["close"].astype(float)
    fwd = close.shift(-horizon) / close - 1.0
    if kind == "classification":
        return (fwd > 0).astype(int)
    return fwd


def build_dataset(df: pd.DataFrame, horizon: int = 5, kind: str = "classification"):
    X = make_features(df)
    y = make_target(df, horizon, kind)
    data = X.copy()
    data["__target__"] = y
    data = data.dropna()
    feat_cols: List[str] = [c for c in data.columns if c != "__target__"]
    return data[feat_cols], data["__target__"]
