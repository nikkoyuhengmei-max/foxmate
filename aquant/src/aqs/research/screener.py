"""选股器 Screener：策略感知的选股引擎。

为每只股票计算丰富特征（多周期收益、成交额、量比、均线、波动率、回撤、RSI、
基本面 PE/PB/ROE 等），再由"选股策略画像"(ScreenProfile) 给出：
综合评分 score、信号 signal(买入候选/观察/排除)、选中原因 reason、风险提示 risk。

内置三个核心策略画像：
- short_momentum 短线强势选股（1-10 天）
- trend_quality  稳健趋势选股（1-8 周）
- quality_value  质量价值选股（1-6 个月）

所有计算均在 PIT 时点下进行，避免未来函数；结果仅为量化参考，不构成投资建议。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd


# ============================================================ 工具
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


@dataclass
class ScreenConfig:
    min_history: int = 60
    exclude_st: bool = True
    exclude_suspended: bool = True
    min_amount: float = 0.0          # 最小近 20 日日均成交额（元）
    rsi_overbought: float = 75.0


# ============================================================ 策略画像
class ScreenProfile:
    key = "base"
    name = "基础"
    horizon = ""

    def evaluate(self, df: pd.DataFrame) -> pd.DataFrame:
        """输入特征表，返回带 score/signal/reason/risk 的表。子类实现。"""
        raise NotImplementedError

    # 通用：按分数分档给信号
    @staticmethod
    def _signal_by_rank(score: pd.Series, buy_q: float = 0.7, observe_q: float = 0.4) -> pd.Series:
        if len(score) == 0:
            return pd.Series([], dtype=object)
        buy = score.quantile(buy_q)
        obs = score.quantile(observe_q)
        def lab(v):
            if v >= buy:
                return "买入候选"
            if v >= obs:
                return "观察"
            return "排除"
        return score.apply(lab)


class ShortMomentumProfile(ScreenProfile):
    key = "short_momentum"
    name = "短线强势选股"
    horizon = "1-10 天短线"

    def evaluate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        score = (
            1.0 * _z(out["ret_5d"]) + 0.6 * _z(out["ret_20d"])
            + 0.5 * _z(out["vol_ratio"]) + 0.3 * _z(out["amount"])
            + 0.4 * out["above_ma20"].astype(float)
            - 0.5 * _z((out["rsi"] - 60).clip(lower=0))   # RSI 越超买扣分越多
        )
        out["score"] = score
        out["signal"] = self._signal_by_rank(score)
        out["reason"] = out.apply(self._reason, axis=1)
        out["risk"] = out.apply(self._risk, axis=1)
        # 硬性排除：站不上 MA20 或明显超买
        bad = (~out["above_ma20"]) | (out["rsi"] > 80)
        out.loc[bad, "signal"] = "排除"
        return out

    @staticmethod
    def _reason(r) -> str:
        p = []
        if r["ret_5d"] > 0: p.append(f"5日+{r['ret_5d']*100:.1f}%")
        if r["ret_20d"] > 0: p.append(f"20日+{r['ret_20d']*100:.1f}%")
        if r["above_ma20"]: p.append("站上MA20")
        if r["vol_ratio"] > 1.2: p.append(f"放量(量比{r['vol_ratio']:.1f})")
        return "，".join(p) or "动量一般"

    @staticmethod
    def _risk(r) -> str:
        p = []
        if r["rsi"] > 75: p.append("RSI偏高,短期超买")
        if r["volatility"] > 0.45: p.append("波动较大")
        if r["amount"] < 5e7: p.append("成交额偏低")
        if r.get("is_st"): p.append("ST风险")
        return "，".join(p) or "风险可控"


class TrendQualityProfile(ScreenProfile):
    key = "trend_quality"
    name = "稳健趋势选股"
    horizon = "1-8 周中短线"

    def evaluate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        uptrend = (out["above_ma20"] & out["above_ma60"] & (out["ma20"] > out["ma60"])).astype(float)
        score = (
            1.0 * uptrend + 0.6 * _z(out["ret_60d"])
            - 0.6 * _z(out["volatility"]) - 0.5 * _z(-out["max_drawdown"])  # 回撤越小(接近0)越好
            + 0.3 * _z(out["amount"])
        )
        out["score"] = score
        out["_uptrend"] = uptrend
        out["signal"] = self._signal_by_rank(score)
        out["reason"] = out.apply(self._reason, axis=1)
        out["risk"] = out.apply(self._risk, axis=1)
        out.loc[out["_uptrend"] == 0, "signal"] = out.loc[out["_uptrend"] == 0, "signal"].replace("买入候选", "观察")
        out = out.drop(columns=["_uptrend"])
        return out

    @staticmethod
    def _reason(r) -> str:
        p = []
        if r["above_ma20"] and r["above_ma60"] and r["ma20"] > r["ma60"]:
            p.append("多头排列(MA20>MA60)")
        elif r["above_ma60"]:
            p.append("位于MA60上方")
        if r["volatility"] < 0.3: p.append("波动较低")
        if r["max_drawdown"] > -0.2: p.append("回撤可控")
        if r["ret_60d"] > 0: p.append(f"60日+{r['ret_60d']*100:.1f}%")
        return "，".join(p) or "趋势一般"

    @staticmethod
    def _risk(r) -> str:
        p = []
        if not (r["above_ma20"] and r["above_ma60"]): p.append("趋势走弱")
        if r["max_drawdown"] < -0.35: p.append("历史回撤较大")
        if r["volatility"] > 0.45: p.append("波动较大")
        if r.get("is_st"): p.append("ST风险")
        return "，".join(p) or "风险可控"


class QualityValueProfile(ScreenProfile):
    key = "quality_value"
    name = "质量价值选股"
    horizon = "1-6 个月"

    def evaluate(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        pe = out["pe"].where(out["pe"] > 0)            # 剔除亏损/异常 PE
        roe = out["roe"]
        value = -_z(pe.fillna(pe.median())) - _z(out["pb"].fillna(out["pb"].median()))
        quality = _z(roe.fillna(roe.median())) if roe.notna().any() else 0.0
        growth = (
            _z(out["revenue_yoy"].fillna(0)) + _z(out["net_profit_yoy"].fillna(0))
            if out["revenue_yoy"].notna().any() else 0.0
        )
        trend = out["above_ma60"].astype(float)        # 趋势过滤
        score = value + 1.0 * quality + 0.6 * growth + 0.3 * trend
        out["score"] = score
        out["signal"] = self._signal_by_rank(score)
        out["reason"] = out.apply(self._reason, axis=1)
        out["risk"] = out.apply(self._risk, axis=1)
        return out

    @staticmethod
    def _reason(r) -> str:
        p = []
        if pd.notna(r.get("roe")) and r["roe"] > 0.1: p.append(f"ROE {r['roe']*100:.1f}%")
        if pd.notna(r.get("pe")) and 0 < r["pe"] < 25: p.append(f"低PE({r['pe']:.0f})")
        if pd.notna(r.get("pb")) and r["pb"] < 3: p.append(f"低PB({r['pb']:.1f})")
        if pd.notna(r.get("revenue_yoy")) and r["revenue_yoy"] > 0: p.append("营收增长")
        if r["above_ma60"]: p.append("趋势向好")
        return "，".join(p) or "估值/质量一般"

    @staticmethod
    def _risk(r) -> str:
        p = []
        if not pd.notna(r.get("pe")) or r.get("pe", 0) <= 0: p.append("PE异常/可能亏损")
        if not r["above_ma60"]: p.append("趋势偏弱")
        if pd.notna(r.get("roe")) and r["roe"] < 0.05: p.append("盈利能力偏弱")
        if r.get("is_st"): p.append("ST风险")
        return "，".join(p) or "风险可控"


PROFILES: Dict[str, ScreenProfile] = {
    p.key: p for p in [ShortMomentumProfile(), TrendQualityProfile(), QualityValueProfile()]
}


# ============================================================ 选股器
class Screener:
    def __init__(self, config: Optional[ScreenConfig] = None, profile=None) -> None:
        self.cfg = config or ScreenConfig()
        if profile is None:
            self.profile = PROFILES["short_momentum"]
        elif isinstance(profile, str):
            self.profile = PROFILES.get(profile, PROFILES["short_momentum"])
        else:
            self.profile = profile

    def screen(
        self,
        data,
        universe: Optional[Sequence[str]] = None,
        asof=None,
        top_n: int = 20,
        auction: Optional[Dict[str, Dict[str, float]]] = None,
    ) -> pd.DataFrame:
        universe = list(universe) if universe else list(data.symbols)
        asof = pd.Timestamp(asof) if asof is not None else None

        ctx = data.pit(asof) if asof is not None else _nullctx()
        rows = []
        with ctx:
            for sym in universe:
                row = self._features(data, sym, auction)
                if row is not None:
                    rows.append(row)

        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows).set_index("symbol")
        df = self.profile.evaluate(df)
        df = df.sort_values("score", ascending=False)
        df.insert(0, "rank", range(1, len(df) + 1))

        front = ["rank", "name", "industry", "close", "ret_5d", "ret_20d", "ret_60d",
                 "amount", "rsi", "score", "signal", "reason", "risk"]
        cols = [c for c in front if c in df.columns] + [c for c in df.columns if c not in front]
        return df[cols].head(top_n).round(4)

    def _features(self, data, sym: str, auction):
        from aqs.data.industry import industry_of

        inst = data.instrument(sym)
        is_st = bool(inst and inst.is_st)
        if self.cfg.exclude_st and is_st:
            return None
        try:
            bars = data.get_price(sym, fields=["close", "volume", "amount"])
        except KeyError:
            return None
        bars = bars.dropna(subset=["close"])
        if len(bars) < self.cfg.min_history:
            return None
        last_ts = bars.index[-1]
        if self.cfg.exclude_suspended and data.is_suspended(sym, last_ts):
            return None

        close = bars["close"].astype(float)
        vol = bars["volume"].astype(float)
        amt = bars["amount"].astype(float) if "amount" in bars else (close * vol)
        last = float(close.iloc[-1])
        amount20 = float(amt.tail(20).mean())
        if self.cfg.min_amount and amount20 < self.cfg.min_amount:
            return None

        def ret(n):
            return float(close.iloc[-1] / close.iloc[-1 - n] - 1.0) if len(close) > n else np.nan

        ma20 = float(close.tail(20).mean())
        ma60 = float(close.tail(60).mean()) if len(close) >= 60 else float("nan")
        recent = close.tail(120)
        mdd = float((recent / recent.cummax() - 1).min())

        fund = data.get_fundamentals([sym], fields=["pe", "pb", "roe", "revenue_yoy", "net_profit_yoy"])
        f = fund.loc[sym] if (not fund.empty and sym in fund.index) else {}

        row = {
            "symbol": sym,
            "name": inst.name if inst else "",
            "industry": (inst.industry if inst else "") or industry_of(sym),
            "close": round(last, 2),
            "ret_5d": ret(5), "ret_20d": ret(20), "ret_60d": ret(60), "ret_120d": ret(120),
            "amount": amount20,
            "vol_ratio": float(vol.tail(5).mean() / (vol.tail(20).mean() + 1e-9)) if vol.tail(20).mean() else 1.0,
            "above_ma20": bool(last > ma20),
            "above_ma60": bool(pd.notna(ma60) and last > ma60),
            "ma20": ma20, "ma60": ma60,
            "volatility": float(close.pct_change().tail(20).std(ddof=0) * np.sqrt(252)),
            "max_drawdown": mdd,
            "rsi": round(_rsi(close, 14), 1),
            "is_st": is_st,
            "pe": float(f["pe"]) if "pe" in f and pd.notna(f["pe"]) else np.nan,
            "pb": float(f["pb"]) if "pb" in f and pd.notna(f["pb"]) else np.nan,
            "roe": float(f["roe"]) if "roe" in f and pd.notna(f["roe"]) else np.nan,
            "revenue_yoy": float(f["revenue_yoy"]) if "revenue_yoy" in f and pd.notna(f["revenue_yoy"]) else np.nan,
            "net_profit_yoy": float(f["net_profit_yoy"]) if "net_profit_yoy" in f and pd.notna(f["net_profit_yoy"]) else np.nan,
        }
        if auction and sym in auction:
            row["auction_gap"] = float(auction[sym].get("gap", np.nan))
            row["auction_vol_ratio"] = float(auction[sym].get("auction_vol_ratio", np.nan))
        return row


class _nullctx:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
