"""日内 5 分钟行情缓存与高频参与度因子（离线）。

目录：data/cache/intraday_5m/{symbol}/{date}.parquet
字段：datetime,open,high,low,close,volume,amount,source,updated_at

第一版仅用 5 分钟行情（不接逐笔/Level-2），数据更新（联网）与选股（离线）分离。
高频因子：
- activity_score   高频参与度 0–100
- direction_score  高频资金方向 -100–+100
- intraday_signal  日内参与信号
禁止使用 mock 分钟数据：无真实缓存时返回“数据缺失”。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from aqs.data.bars_cache import _call_timeout

INTRADAY_DIR = os.path.join("data", "cache", "intraday_5m")
STALE_DAYS = 5
_COLS = ["datetime", "open", "high", "low", "close", "volume", "amount", "source", "updated_at"]


def sym_dir(symbol: str) -> str:
    return os.path.join(INTRADAY_DIR, symbol)


def date_path(symbol: str, date: str) -> str:
    return os.path.join(sym_dir(symbol), f"{date}.parquet")


def _sina_symbol(symbol: str) -> str:
    code, _, ex = symbol.partition(".")
    return ("sh" if ex.upper() == "SH" else "sz") + code


# ----------------------------------------------------------------- I/O
def available_dates(symbol: str) -> List[str]:
    d = sym_dir(symbol)
    if not os.path.isdir(d):
        return []
    return sorted(f[:-8] for f in os.listdir(d) if f.endswith(".parquet"))


def save_day(symbol: str, date: str, df: pd.DataFrame, source: str) -> None:
    os.makedirs(sym_dir(symbol), exist_ok=True)
    out = df.copy()
    out["datetime"] = pd.to_datetime(out["datetime"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    out["source"] = source
    out["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out[_COLS].to_parquet(date_path(symbol, date), index=False)


def load_day(symbol: str, date: str) -> Optional[pd.DataFrame]:
    p = date_path(symbol, date)
    if not os.path.exists(p):
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.to_datetime(df["datetime"])
        return df.sort_index()
    except Exception:
        return None


def load_latest(symbol: str) -> Optional[Tuple[str, pd.DataFrame]]:
    ds = available_dates(symbol)
    if not ds:
        return None
    df = load_day(symbol, ds[-1])
    return (ds[-1], df) if df is not None else None


def is_fresh(symbol: str, stale_days: int = STALE_DAYS) -> bool:
    ds = available_dates(symbol)
    if not ds:
        return False
    last = pd.to_datetime(ds[-1])
    return (pd.Timestamp.today().normalize() - last.normalize()).days <= stale_days


def status(symbols: List[str]) -> Dict[str, int]:
    cached = valid = stale = 0
    for s in symbols:
        ds = available_dates(s)
        if not ds:
            continue
        cached += 1
        if is_fresh(s):
            valid += 1
        else:
            stale += 1
    total = len(symbols)
    return {"universe_count": total, "cached_count": cached, "valid_count": valid,
            "missing_count": total - cached, "stale_count": stale}


def _stats_path(universe: str) -> str:
    return os.path.join(INTRADAY_DIR, f"_update_{universe}.json")


def save_update_stats(universe: str, stats: dict) -> None:
    os.makedirs(INTRADAY_DIR, exist_ok=True)
    stats = dict(stats)
    stats["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(_stats_path(universe), "w", encoding="utf-8") as fh:
            json.dump(stats, fh, ensure_ascii=False)
    except Exception:
        pass


def load_update_stats(universe: str) -> dict:
    p = _stats_path(universe)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


# --------------------------------------------------- 单只取数（AkShare/Sina）
def _sina_fetch(symbol: str) -> Optional[pd.DataFrame]:
    import akshare as ak  # type: ignore

    raw = ak.stock_zh_a_minute(symbol=_sina_symbol(symbol), period="5", adjust="qfq")
    if raw is None or len(raw) == 0 or "close" not in raw.columns:
        return None
    df = pd.DataFrame()
    df["datetime"] = pd.to_datetime(raw["day"])
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(raw[c], errors="coerce") if c in raw.columns else float("nan")
    return df.dropna(subset=["close"])


def update_intraday(symbols: List[str], on_progress: Optional[Callable] = None,
                    force: bool = False, per_symbol_timeout: float = 20.0,
                    days_keep: int = 5, universe: str = "") -> dict:
    """更新 5 分钟行情缓存（AkShare/Sina 源），保存最近 days_keep 个交易日。"""
    total = len(symbols)
    cached = success = failed = 0
    failed_syms: List[str] = []
    ak_fail = 0
    ak_off = False
    t0 = time.time()
    try:
        for i, sym in enumerate(symbols):
            if not force and is_fresh(sym):
                cached += 1
                if on_progress:
                    on_progress(i + 1, total, sym, cached, success, failed, time.time() - t0, "cache")
                continue
            df = None
            if not ak_off:
                v, _ = _call_timeout(lambda: _sina_fetch(sym), per_symbol_timeout)
                if v is not None and len(v):
                    df, ak_fail = v, 0
                else:
                    ak_fail += 1
                    if ak_fail >= 5:
                        ak_off = True
                        print("[intraday-update] AkShare 连续失败 5 次，暂停下载")
            if df is not None and len(df):
                g = df.copy()
                g["_date"] = g["datetime"].dt.strftime("%Y-%m-%d")
                dates = sorted(g["_date"].unique())[-days_keep:]
                wrote = 0
                for d in dates:
                    if not force and os.path.exists(date_path(sym, d)):
                        continue
                    save_day(sym, d, g[g["_date"] == d].drop(columns="_date"), "akshare")
                    wrote += 1
                success += 1
            else:
                failed += 1
                failed_syms.append(sym)
            if on_progress:
                on_progress(i + 1, total, sym, cached, success, failed, time.time() - t0,
                            "ok" if df is not None else "fail")
    except KeyboardInterrupt:
        print("\n[intraday-update] 已中断，已成功的数据已保存。")
    stats = {"universe": universe, "total": total, "cached": cached, "success": success,
             "failed": failed, "failed_symbols": failed_syms[:50],
             "elapsed_seconds": round(time.time() - t0, 1)}
    if universe:
        save_update_stats(universe, stats)
    return stats


# --------------------------------------------------- 高频因子
def _clip(x, lo, hi):
    return float(max(lo, min(hi, x)))


_EMPTY = {
    "activity_score": np.nan, "direction_score": np.nan, "intraday_signal": "数据缺失",
    "open30_amount_ratio": np.nan, "close30_amount_ratio": np.nan,
    "active_bar_ratio": np.nan, "volprice_sync": np.nan, "pullback_risk": np.nan,
    "intraday_date": None,
}


def compute_intraday_factors(symbol: str, daily_amount20: Optional[float] = None) -> dict:
    """从本地 5 分钟缓存计算高频参与度/资金方向（无缓存返回“数据缺失”）。"""
    latest = load_latest(symbol)
    if latest is None:
        return dict(_EMPTY)
    date, df = latest
    if df is None or len(df) < 12:
        return dict(_EMPTY)

    openp = df["open"].astype(float).values
    high = df["high"].astype(float).values
    close = df["close"].astype(float).values
    vol = df["volume"].astype(float).fillna(0).values
    amt = df["amount"].astype(float).fillna(0).values
    n = len(df)
    total_amt = float(amt.sum())
    total_vol = float(vol.sum())
    if total_amt <= 0 or total_vol <= 0:
        return dict(_EMPTY)

    med_amt = float(np.median(amt))
    k = max(1, round(n * 30.0 / 240.0))   # 约 30 分钟对应的 K 线数（约 6）
    upbar = close >= openp

    # ---------- activity_score 子项（0–100）----------
    ratio = total_amt / daily_amount20 if (daily_amount20 and daily_amount20 > 0) else 1.0
    s_amount = _clip(ratio * 50.0, 0, 100)

    active = amt > 1.5 * med_amt
    active_ratio = float(active.mean())
    s_active = _clip(active_ratio / 0.35 * 100.0, 0, 100)

    segs = 8
    seg_idx = (np.arange(n) * segs // n)
    covered = len(set(seg_idx[active])) if active.any() else 0
    s_persist = covered / segs * 100.0

    highvol = vol > np.median(vol)
    sync = float((upbar & highvol).sum()) / max(1, int(highvol.sum()))
    s_sync = _clip(sync * 100.0, 0, 100)

    open30 = float(amt[:k].sum()) / total_amt
    close30 = float(amt[-k:].sum()) / total_amt
    baseline = (2.0 * k) / n
    s_oc = _clip((open30 + close30) / (baseline * 2.0) * 100.0, 0, 100)

    top3 = float(np.sort(amt)[-3:].sum()) / total_amt
    s_conc = _clip(100.0 - (top3 - 0.15) / 0.45 * 100.0, 0, 100)

    activity_score = (0.25 * s_amount + 0.20 * s_active + 0.20 * s_persist
                      + 0.15 * s_sync + 0.10 * s_oc + 0.10 * s_conc)

    # ---------- direction_score（-100–+100）----------
    up_volume_ratio = float(vol[upbar].sum()) / total_vol
    down_volume_ratio = float(vol[~upbar].sum()) / total_vol
    net_vol = up_volume_ratio - down_volume_ratio
    day_close = float(close[-1])
    vwap = total_amt / total_vol
    close_vs_vwap = day_close / vwap - 1.0
    close30_ret = day_close / float(close[-k]) - 1.0 if n > k else 0.0
    day_high = float(high.max())
    intraday_drawdown = (day_high - day_close) / day_high if day_high > 0 else 0.0
    hv_down = float((highvol & ~upbar).sum()) / max(1, int(highvol.sum()))
    direction_raw = (0.35 * net_vol
                     + 0.25 * np.tanh(close_vs_vwap * 60.0)
                     + 0.20 * np.tanh(close30_ret * 120.0)
                     - 0.10 * np.tanh(intraday_drawdown * 40.0)
                     - 0.10 * hv_down)
    direction_score = _clip(direction_raw * 100.0, -100, 100)

    # ---------- 日内参与信号 ----------
    if activity_score < 40:
        sig = "参与度不足"
    elif direction_score < -30:
        sig = "放量下跌偏空"
    elif intraday_drawdown > 0.03 and direction_score < 30:
        sig = "冲高回落风险"
    elif close30_ret > 0.004 and direction_score > 15:
        sig = "尾盘资金介入"
    elif activity_score >= 60 and direction_score > 30:
        sig = "持续活跃偏多"
    else:
        sig = "活跃但方向分歧"

    return {
        "activity_score": round(activity_score, 1),
        "direction_score": round(direction_score, 1),
        "intraday_signal": sig,
        "open30_amount_ratio": round(open30, 4),
        "close30_amount_ratio": round(close30, 4),
        "active_bar_ratio": round(active_ratio, 4),
        "volprice_sync": round(s_sync, 1),
        "pullback_risk": round(intraday_drawdown, 4),
        "intraday_date": date,
    }
