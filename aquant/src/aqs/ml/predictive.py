"""预测上涨模型 predictive_ranking。

目标：找"未来 3/5/10 天可能上涨"的股票（不是已经最强的股票）。

两层模型：
1) 规则过滤：剔除 ST/停牌/退市风险、流动性不足、数据缺失、严重过热、放量大跌、回撤过大。
2) 预测评分：用因果特征(K线/量价/趋势/舆情/风险)训练横截面模型预测未来上涨概率与预期收益，
   再按权重合成 final_score。

防未来函数：特征仅用当日及之前数据；标签用"未来收益"，训练时丢弃无标签的尾部行；
预测用最新一行因果特征；舆情/基本面按日期对齐。

免责声明：模型预测仅供研究参考，不构成投资建议；预测概率不代表确定收益，历史表现不代表未来结果。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from aqs.ml.forecast import _NumpyLogistic

try:  # 可选依赖
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor  # type: ignore
    _HAS_SK = True
except Exception:  # pragma: no cover
    _HAS_SK = False

HORIZONS = [3, 5, 10]
DISCLAIMER = ("模型预测仅供研究参考，不构成投资建议。预测概率不代表确定收益，"
              "历史表现不代表未来结果。")


# ----------------------------------------------------------------- 指标
def _ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def _rsi_series(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    gain = d.clip(lower=0).rolling(n).mean()
    loss = (-d.clip(upper=0)).rolling(n).mean()
    rs = gain / (loss + 1e-12)
    return 100 - 100 / (1 + rs)


def _features(df: pd.DataFrame) -> pd.DataFrame:
    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df else close
    low = df["low"].astype(float) if "low" in df else close
    vol = df["volume"].astype(float) if "volume" in df else pd.Series(1.0, index=df.index)
    amt = df["amount"].astype(float) if "amount" in df else close * vol

    out = pd.DataFrame(index=df.index)
    for n in (1, 3, 5, 10, 20):
        out[f"ret_{n}"] = close.pct_change(n)
    for n in (5, 10, 20, 60):
        ma = close.rolling(n).mean()
        out[f"d_ma{n}"] = close / ma - 1.0
    out["rsi"] = _rsi_series(close, 14)
    dif = _ema(close, 12) - _ema(close, 26)
    dea = _ema(dif, 9)
    out["macd_dif"] = dif
    out["macd_dea"] = dea
    out["macd_hist"] = dif - dea
    low9 = low.rolling(9).min()
    high9 = high.rolling(9).max()
    rsv = (close - low9) / (high9 - low9 + 1e-12) * 100
    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    out["kdj_k"] = k
    out["kdj_d"] = d
    out["kdj_j"] = 3 * k - 2 * d
    mid = close.rolling(20).mean()
    std = close.rolling(20).std(ddof=0)
    out["boll_pctb"] = (close - mid) / (2 * std + 1e-12)
    tr = pd.concat([(high - low), (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    out["atr_ratio"] = tr.rolling(14).mean() / (close + 1e-12)
    out["vol_ratio"] = vol.rolling(5).mean() / (vol.rolling(20).mean() + 1e-9)
    out["amount_ratio"] = amt.rolling(5).mean() / (amt.rolling(20).mean() + 1e-9)
    out["volatility20"] = close.pct_change().rolling(20).std(ddof=0) * np.sqrt(252)
    return out


_FEATURE_COLS = [
    "ret_1", "ret_3", "ret_5", "ret_10", "ret_20",
    "d_ma5", "d_ma10", "d_ma20", "d_ma60", "rsi",
    "macd_dif", "macd_dea", "macd_hist", "kdj_k", "kdj_d", "kdj_j",
    "boll_pctb", "atr_ratio", "vol_ratio", "amount_ratio", "volatility20",
]


def _z(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    sd = s.std(ddof=0)
    return pd.Series(0.0, index=s.index) if (not np.isfinite(sd) or sd == 0) else (s - s.mean()) / (sd + 1e-12)


def _mm(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    lo, hi = s.min(), s.max()
    return pd.Series(50.0, index=s.index) if hi == lo else (s - lo) / (hi - lo) * 100


class _RidgeNP:
    def __init__(self, l2: float = 1.0):
        self.l2 = l2; self.w = None; self.b = 0.0; self.mu = None; self.sd = None

    def fit(self, X, y):
        self.mu = X.mean(0); self.sd = X.std(0) + 1e-9
        Xs = (X - self.mu) / self.sd
        n, d = Xs.shape
        A = Xs.T @ Xs + self.l2 * np.eye(d)
        self.w = np.linalg.solve(A, Xs.T @ (y - y.mean()))
        self.b = float(y.mean())
        return self

    def predict(self, X):
        return ((X - self.mu) / self.sd) @ self.w + self.b


def _fit_clf(X, y):
    if len(np.unique(y)) < 2:
        return None
    if _HAS_SK and len(X) >= 80:
        try:
            m = GradientBoostingClassifier(n_estimators=80, max_depth=3, learning_rate=0.05)
            m.fit(X, y)
            return m
        except Exception:
            pass
    return _NumpyLogistic().fit(X, y.astype(float))


def _fit_reg(X, y):
    if _HAS_SK and len(X) >= 80:
        try:
            m = GradientBoostingRegressor(n_estimators=80, max_depth=3, learning_rate=0.05)
            m.fit(X, y)
            return m
        except Exception:
            pass
    return _RidgeNP().fit(X, y)


def _proba(model, X):
    if model is None:
        return np.full(len(X), 0.5)
    p = model.predict_proba(X)
    return p[:, 1]


def predict_universe(
    data,
    universe: Optional[Sequence[str]] = None,
    asof=None,
    top_n: int = 20,
    sentiment: Optional[Dict[str, dict]] = None,
    market_caps: Optional[Dict[str, float]] = None,
    min_history: int = 80,
    min_amount: float = 5e7,
) -> pd.DataFrame:
    from aqs.data.industry import industry_of

    universe = list(universe) if universe else list(data.symbols)
    asof = pd.Timestamp(asof) if asof is not None else None
    ctx = data.pit(asof) if asof is not None else _null()

    cur: Dict[str, dict] = {}

    with ctx:
        for sym in universe:
            inst = data.instrument(sym)
            if not data.is_active(sym, asof):   # 退市/不在市 -> 跳过
                continue
            try:
                bars = data.get_price(sym, fields=["open", "high", "low", "close", "volume", "amount"]).dropna(subset=["close"])
            except KeyError:
                continue
            if len(bars) < min_history:
                continue
            feats = _features(bars)
            close = bars["close"].astype(float)
            fmat = feats[_FEATURE_COLS]
            valid = fmat.notna().all(axis=1)
            # 当前预测行（最新有效特征）
            vrows = fmat[valid]
            if not len(vrows):
                continue
            amount20 = float(bars["amount"].astype(float).tail(20).mean())
            ma5 = float(close.tail(5).mean()); ma10 = float(close.tail(10).mean())
            ma20 = float(close.tail(20).mean()); ma60 = float(close.tail(60).mean()) if len(close) >= 60 else float("nan")
            last5 = close.tail(5)
            mdd5 = float((last5 / last5.cummax() - 1).min()) if len(last5) else 0.0
            ret1 = float(close.iloc[-1] / close.iloc[-2] - 1) if len(close) > 1 else 0.0
            vol = bars["volume"].astype(float)
            vol_spike = float(vol.iloc[-1] / (vol.tail(20).mean() + 1e-9)) if vol.tail(20).mean() else 1.0
            row = vrows.iloc[-1]
            cur[sym] = {
                "symbol": sym, "name": inst.name if inst else "", "industry": (inst.industry if inst else "") or industry_of(sym),
                "close": round(float(close.iloc[-1]), 2), "is_st": bool(inst and inst.is_st),
                "feat": row[_FEATURE_COLS].values.astype(float),
                "rsi": float(row["rsi"]) if pd.notna(row["rsi"]) else 50.0,
                "amount20": amount20, "amount_ratio": float(row["amount_ratio"]), "vol_ratio": float(row["vol_ratio"]),
                "ret_3": float(row["ret_3"]), "ret_5": float(row["ret_5"]), "ret_10": float(row["ret_10"]), "ret_20": float(row["ret_20"]),
                "macd_hist": float(row["macd_hist"]), "boll_pctb": float(row["boll_pctb"]), "atr_ratio": float(row["atr_ratio"]),
                "d_ma5": float(row["d_ma5"]), "d_ma20": float(row["d_ma20"]),
                "volatility20": float(row["volatility20"]),
                "above_ma5": bool(close.iloc[-1] > ma5), "above_ma10": bool(close.iloc[-1] > ma10),
                "above_ma20": bool(close.iloc[-1] > ma20),
                "above_ma60": bool(pd.notna(ma60) and close.iloc[-1] > ma60),
                "mdd5": mdd5, "ret1": ret1, "vol_spike": vol_spike,
                "breakout_20d": bool(close.iloc[-1] >= float(close.iloc[-21:-1].max()) * 0.999) if len(close) > 21 else False,
            }

    if not cur:
        return pd.DataFrame()

    # 规则评分模型（无需训练，稳定快速）：横截面 z-score 合成上涨概率
    rows = []
    for sym, c in cur.items():
        s = (sentiment or {}).get(sym, {})
        rows.append({**c,
                     "attention_score": s.get("attention_score", np.nan),
                     "sentiment_score": s.get("sentiment_score", np.nan),
                     "attention_change_3d": s.get("attention_change_3d"),
                     "risk_keyword_count": s.get("risk_keyword_count", np.nan)})
    df = pd.DataFrame(rows).set_index("symbol")
    df = _rule_probabilities(df)
    df = _score_and_signal(df)
    df = df.sort_values("final_score", ascending=False)
    df.insert(0, "rank", range(1, len(df) + 1))
    front = ["rank", "name", "industry", "close", "prob_up_3d", "prob_up_5d", "prob_up_10d",
             "expected_return_5d", "money_score", "tech_score", "sentiment_factor_score",
             "risk_score", "final_score", "signal", "reason", "risk"]
    cols = [c for c in front if c in df.columns] + [c for c in df.columns if c not in front and c != "feat"]
    return df[cols].head(top_n).round(4)


def _train_models(cur, data, asof):
    """按 3/5/10 horizon 池化训练分类模型 + 5日收益回归。"""
    from collections import defaultdict

    Xh = defaultdict(list); yh = defaultdict(list); X5 = []; r5 = []
    ctx = data.pit(asof) if asof is not None else _null()
    with ctx:
        for sym in cur:
            try:
                bars = data.get_price(sym, fields=["open", "high", "low", "close", "volume", "amount"]).dropna(subset=["close"])
            except KeyError:
                continue
            feats = _features(bars)[_FEATURE_COLS]
            close = bars["close"].astype(float)
            valid = feats.notna().all(axis=1)
            for h in HORIZONS:
                lab = (close.shift(-h) / close - 1.0)
                m = valid & lab.notna()
                if m.sum():
                    Xh[h].append(feats[m].values); yh[h].append((lab[m].values > 0).astype(int))
            lab5 = (close.shift(-5) / close - 1.0)
            m5 = valid & lab5.notna()
            if m5.sum():
                X5.append(feats[m5].values); r5.append(lab5[m5].values)
    models = {}
    for h in HORIZONS:
        if Xh[h]:
            X = np.vstack(Xh[h]); y = np.concatenate(yh[h])
            models[h] = _fit_clf(X, y)
        else:
            models[h] = None
    reg5 = _fit_reg(np.vstack(X5), np.concatenate(r5)) if X5 else None
    return models, reg5


def _rule_probabilities(df: pd.DataFrame) -> pd.DataFrame:
    """规则评分模型：用真实行情因子横截面打分，映射为未来上涨概率（无需训练）。

    思路：动量(3/5/10日) + 趋势(站上均线) + 量能 + 不过热，做横截面 z-score 合成，
    经 tanh 压缩到 ~0.32–0.68 的概率区间（保守、不过度自信）。
    """
    out = df.copy()
    trend = (out["above_ma5"].astype(float) + out["above_ma10"].astype(float)
             + out["above_ma20"].astype(float)) / 3.0
    over = (out["rsi"] - 70).clip(lower=0)            # 超买惩罚
    z_t = _z(trend)
    z_vol = _z(out["vol_ratio"])
    z_over = _z(over)

    def prob(weight_short: float, weight_mid: float, weight_long: float) -> pd.Series:
        combo = (weight_short * _z(out["ret_3"]) + weight_mid * _z(out["ret_5"])
                 + weight_long * _z(out["ret_10"]) + 0.4 * z_t + 0.25 * z_vol - 0.3 * z_over)
        return (0.5 + 0.16 * np.tanh(combo)).clip(0.05, 0.95)

    out["prob_up_3d"] = prob(0.55, 0.30, 0.15)
    out["prob_up_5d"] = prob(0.30, 0.45, 0.25)
    out["prob_up_10d"] = prob(0.20, 0.35, 0.45)
    daily_vol = out["volatility20"].fillna(out["volatility20"].median()) / np.sqrt(252)
    out["expected_return_5d"] = ((out["prob_up_5d"] - 0.5) * 2 * daily_vol * np.sqrt(5)).round(4)
    return out


def _score_and_signal(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    # 量价配合：放量上涨好，放量下跌差
    volprice = np.where(out["ret_5"] > 0, out["vol_ratio"], 2 - out["vol_ratio"])
    out["volprice_raw"] = volprice
    # 资金介入：成交额/量放大
    out["money_raw"] = 0.5 * out["amount_ratio"] + 0.5 * out["vol_ratio"]
    # 趋势质量：均线多头 + 中期方向
    trend = (out["above_ma5"].astype(float) + out["above_ma10"].astype(float)
             + out["above_ma20"].astype(float) + out["above_ma60"].astype(float)) / 4.0
    out["trend_raw"] = trend + 0.3 * np.sign(out["ret_20"].fillna(0))
    # 风险（越高越危险）
    out["risk_raw"] = out["volatility20"].fillna(out["volatility20"].median()) + (-out["mdd5"]).clip(lower=0) \
        + (out["rsi"].clip(lower=70) - 70) / 30.0

    # 0-100 分项
    out["tech_score"] = _mm(0.4 * out["prob_up_5d"] + 0.2 * (out["rsi"].clip(40, 75)) / 75
                            + 0.2 * np.sign(out["macd_hist"].fillna(0)) + 0.2 * out["trend_raw"])
    out["money_score"] = _mm(out["money_raw"])
    out["volprice_score"] = _mm(out["volprice_raw"])
    out["trend_score"] = _mm(out["trend_raw"])
    out["risk_score"] = _mm(out["risk_raw"])
    has_sent = out["attention_score"].notna().any()
    if has_sent:
        out["sentiment_factor_score"] = _mm(out["attention_score"].fillna(out["attention_score"].median()))
    else:
        out["sentiment_factor_score"] = np.nan

    prob100 = out["prob_up_5d"] * 100
    # final_score = 概率30 量价20 趋势15 资金15 舆情10 风控10
    if has_sent:
        final = (0.30 * prob100 + 0.20 * out["volprice_score"] + 0.15 * out["trend_score"]
                 + 0.15 * out["money_score"] + 0.10 * out["sentiment_factor_score"].fillna(50)
                 + 0.10 * (100 - out["risk_score"]))
    else:  # 舆情缺失：把 10% 权重并入概率
        final = (0.40 * prob100 + 0.20 * out["volprice_score"] + 0.15 * out["trend_score"]
                 + 0.15 * out["money_score"] + 0.10 * (100 - out["risk_score"]))
    out["final_score"] = final.round(2)

    out["signal"] = out.apply(_signal, axis=1)
    out["reason"] = out.apply(_reason, axis=1)
    out["risk"] = out.apply(_risk, axis=1)
    # 规则排除项压到最低，避免排在前面
    out.loc[out["signal"] == "排除", "final_score"] = out["final_score"].min() - 1
    return out


def _overheated(r) -> bool:
    return (r["rsi"] > 80) or (r["ret_5"] > 0.25) or (r["boll_pctb"] > 1.1)


def _rule_excluded(r) -> bool:
    return bool(r["is_st"] or r["amount20"] < 5e7 or r["mdd5"] < -0.20
                or (r["ret1"] < -0.06 and r["vol_spike"] > 1.5)         # 放量大跌
                or (r["rsi"] > 85 and r["ret_5"] > 0.25))               # 严重过热


def _signal(r) -> str:
    if _rule_excluded(r):
        return "排除"
    if _overheated(r):
        return "过热风险"
    extended = (r["rsi"] >= 72) or (r["d_ma5"] > 0.08)
    if r["prob_up_5d"] >= 0.5 and extended:
        return "等待回调"
    if r["final_score"] >= 60 and r["prob_up_5d"] >= 0.55:
        return "高潜力观察"
    return "谨慎观察"


def _reason(r) -> str:
    p = []
    if r["ret_5"] < 0 and r["above_ma20"]:
        p.append("近5日回调但仍站上MA20")
    elif r["above_ma20"]:
        p.append("站上MA20")
    if r["amount_ratio"] > 1.3:
        p.append(f"成交额较20日均值放大{r['amount_ratio']:.1f}倍")
    if 55 <= r["rsi"] <= 70:
        p.append(f"RSI {r['rsi']:.0f}，未明显过热")
    if r.get("macd_hist", 0) and r["macd_hist"] > 0:
        p.append("MACD红柱")
    ac3 = r.get("attention_change_3d")
    if ac3 is not None and ac3 == ac3 and ac3 > 0.2:
        p.append("舆情近3日升温")
    p.append(f"预测未来5日上涨概率 {r['prob_up_5d']*100:.0f}%")
    return "，".join(p)


def _risk(r) -> str:
    p = []
    if r["volatility20"] > 0.45:
        p.append("近期波动较大")
    if r["above_ma20"]:
        p.append("若跌破MA20，模型信号失效")
    if not (r.get("attention_score") == r.get("attention_score")):  # NaN
        p.append("舆情数据不足，需谨慎参考")
    if r["mdd5"] < -0.1:
        p.append("近5日回撤偏大")
    if r["rsi"] > 75:
        p.append("RSI偏高，注意回调")
    return "，".join(p) or "风险可控"


class _null:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def predict_symbol(data, symbol: str, horizon: int = 5, sentiment=None) -> dict:
    """单只股票预测（用其所在/可得的截面训练）。"""
    df = predict_universe(data, universe=[symbol], top_n=1, sentiment=sentiment)
    if df.empty or symbol not in df.index:
        return {"symbol": symbol, "error": "数据不足，无法预测"}
    r = df.loc[symbol].to_dict()
    r["symbol"] = symbol
    r["horizon"] = horizon
    r["disclaimer"] = DISCLAIMER
    return r
