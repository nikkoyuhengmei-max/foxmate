"""选股器 Screener：多周期历史 + 量化指标 + 可选集合竞价，快速筛选 Top N 候选股。

打分逻辑（全部在 PIT 时点下计算，避免未来函数）：

* 多周期动量：1/3/5/20/120(半年)/250(一年) 日收益率
* 趋势排列：收盘 > MA20、MA20 > MA60
* RSI(14)：偏好不超买不超卖区间
* 量比：近 5 日均量 / 近 20 日均量（资金关注度）
* 波动率惩罚：近 20 日年化波动过高扣分
* 集合竞价（可选，需 iFinD 等提供）：开盘竞价相对昨收的跳空、竞价量比

各因子先做横截面 z-score，再按可配置权重加权求和，输出排序后的 Top N。

> 提示：选股结果仅为量化参考，不构成投资建议；务必结合风控与人工复核。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


@dataclass
class ScreenConfig:
    # 各周期（交易日）
    horizons: Dict[str, int] = field(default_factory=lambda: {
        "ret_1d": 1, "ret_3d": 3, "ret_5d": 5, "ret_20d": 20, "ret_120d": 120, "ret_250d": 250,
    })
    # 因子权重（可调）。正数=越大越好，负数=越大越差
    weights: Dict[str, float] = field(default_factory=lambda: {
        "ret_5d": 0.8, "ret_20d": 1.0, "ret_120d": 1.0, "ret_250d": 0.6,
        "trend": 1.0, "vol_ratio": 0.5, "volatility": -0.6, "rsi_score": 0.5,
        "auction_gap": 0.6, "auction_vol_ratio": 0.4,
    })
    min_history: int = 60          # 至少多少根日线才纳入
    exclude_st: bool = True        # 剔除 ST/风险警示
    exclude_suspended: bool = True # 剔除停牌
    rsi_low: float = 30.0
    rsi_high: float = 75.0


def _z(s: pd.Series) -> pd.Series:
    s = s.astype(float)
    std = s.std(ddof=0)
    if not np.isfinite(std) or std == 0:
        return pd.Series(0.0, index=s.index)
    return (s - s.mean()) / (std + 1e-12)


def _rsi(close: pd.Series, window: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window).mean()
    loss = (-delta.clip(upper=0)).rolling(window).mean()
    rs = gain / (loss + 1e-12)
    val = (100 - 100 / (1 + rs)).iloc[-1]
    return float(val) if pd.notna(val) else 50.0


class Screener:
    def __init__(self, config: Optional[ScreenConfig] = None) -> None:
        self.cfg = config or ScreenConfig()

    def screen(
        self,
        data,
        universe: Optional[Sequence[str]] = None,
        asof=None,
        top_n: int = 8,
        auction: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> pd.DataFrame:
        """返回按综合分排序的候选股（前 ``top_n`` 行）。

        ``auction``: 可选的集合竞价快照 {symbol: {"gap": 跳空比例, "auction_vol_ratio": 竞价量比}}，
        接入 iFinD/Wind 实时或竞价数据后传入即可生效；不传则忽略竞价因子。
        """
        universe = list(universe) if universe else list(data.symbols)
        asof = pd.Timestamp(asof) if asof is not None else None

        with data.pit(asof) if asof is not None else _nullctx():
            rows = []
            for sym in universe:
                row = self._features(data, sym, auction)
                if row is not None:
                    rows.append(row)

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).set_index("symbol")

        # 横截面 z-score 后加权
        score = pd.Series(0.0, index=df.index)
        used = []
        for factor, w in self.cfg.weights.items():
            if factor in df.columns and df[factor].notna().any():
                score = score + w * _z(df[factor].fillna(df[factor].median()))
                used.append(factor)
        df["score"] = score
        df = df.sort_values("score", ascending=False)

        # 友好展示列顺序
        front = ["score", "name", "industry", "close"] + list(self.cfg.horizons.keys())
        cols = [c for c in front if c in df.columns] + [c for c in df.columns if c not in front]
        return df[cols].head(top_n).round(4)

    # --------------------------------------------------------------- 因子
    def _features(self, data, sym: str, auction: Optional[Dict[str, Dict[str, float]]]):
        inst = data.instrument(sym)
        if self.cfg.exclude_st and inst is not None and inst.is_st:
            return None
        try:
            bars = data.get_price(sym, fields=["close", "volume"])
        except KeyError:
            return None
        bars = bars.dropna(subset=["close"])
        if len(bars) < self.cfg.min_history:
            return None

        # 当前时点（最近一根）若停牌则按需要剔除
        last_ts = bars.index[-1]
        if self.cfg.exclude_suspended and data.is_suspended(sym, last_ts):
            return None

        close = bars["close"].astype(float)
        vol = bars["volume"].astype(float)
        last = float(close.iloc[-1])

        row: Dict[str, object] = {
            "symbol": sym,
            "name": inst.name if inst else "",
            "industry": inst.industry if inst else "",
            "close": round(last, 2),
        }

        for name, n in self.cfg.horizons.items():
            if len(close) > n:
                row[name] = float(close.iloc[-1] / close.iloc[-1 - n] - 1.0)
            else:
                row[name] = np.nan

        ma20 = close.tail(20).mean()
        ma60 = close.tail(60).mean() if len(close) >= 60 else np.nan
        trend = 0.0
        trend += 1.0 if last > ma20 else 0.0
        trend += 1.0 if (pd.notna(ma60) and ma20 > ma60) else 0.0
        row["trend"] = trend  # 0,1,2
        row["above_ma20"] = bool(last > ma20)
        row["above_ma60"] = bool(pd.notna(ma60) and last > ma60)

        ret1 = close.pct_change()
        row["volatility"] = float(ret1.tail(20).std(ddof=0) * np.sqrt(252))
        v5 = vol.tail(5).mean()
        v20 = vol.tail(20).mean()
        row["vol_ratio"] = float(v5 / (v20 + 1e-9)) if v20 else 1.0

        rsi = _rsi(close, 14)
        row["rsi"] = round(rsi, 1)
        # 偏好区间内得分高，超买/超卖扣分
        over = max(rsi - self.cfg.rsi_high, 0.0) + max(self.cfg.rsi_low - rsi, 0.0)
        row["rsi_score"] = float(-over)

        # 集合竞价（可选）
        if auction and sym in auction:
            a = auction[sym]
            row["auction_gap"] = float(a.get("gap", np.nan))
            row["auction_vol_ratio"] = float(a.get("auction_vol_ratio", np.nan))

        return row


class _nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
