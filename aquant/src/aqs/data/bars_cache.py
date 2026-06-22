"""本地历史行情缓存（每只股票一个 parquet），支持离线选股。

目录：data/cache/bars/{symbol}.parquet
字段：date,open,high,low,close,volume,amount,source,updated_at

设计要点：
- 数据更新（联网）与选股（离线）完全分离。
- AkShare 优先，Baostock 仅作补缺；每只股票硬超时，连续失败熔断。
- Baostock 通过 socket 默认超时避免 recv 永久阻塞。
- 增量更新：只更新缺失或过期的股票。
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional

import pandas as pd

BARS_DIR = os.path.join("data", "cache", "bars")
VALID_MIN_ROWS = 60          # 至少多少根 K 线才算有效
STALE_DAYS = 15              # 最新日期距今超过该天数视为过期
_COLS = ["date", "open", "high", "low", "close", "volume", "amount", "source", "updated_at"]

# 各股票池“有效行情”数量门槛（用于离线选股前置校验）
VALID_GATES = {"hs300": 250, "zz500": 400, "hs800": 650, "default_fast": 40, "all": 1000}


def bar_path(symbol: str) -> str:
    return os.path.join(BARS_DIR, f"{symbol}.parquet")


# ----------------------------------------------------------------- I/O
def save_bars(symbol: str, df: pd.DataFrame, source: str) -> None:
    os.makedirs(BARS_DIR, exist_ok=True)
    out = df.copy()
    if out.index.name == "date" or isinstance(out.index, pd.DatetimeIndex):
        out = out.reset_index().rename(columns={out.index.name or "index": "date"})
    if "date" not in out.columns:
        out["date"] = pd.to_datetime(df.index)
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        if c not in out.columns:
            out[c] = float("nan")
    out["source"] = source
    out["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    out[_COLS].to_parquet(bar_path(symbol), index=False)


def load_bars(symbol: str) -> Optional[pd.DataFrame]:
    p = bar_path(symbol)
    if not os.path.exists(p):
        return None
    try:
        df = pd.read_parquet(p)
        if df.empty:
            return None
        df.index = pd.to_datetime(df["date"])
        df = df.sort_index()
        out = pd.DataFrame(index=df.index)
        for c in ["open", "high", "low", "close", "volume", "amount"]:
            out[c] = pd.to_numeric(df[c], errors="coerce") if c in df.columns else float("nan")
        out["suspended"] = out["volume"].fillna(0).le(0)
        return out
    except Exception:
        return None


def bar_meta(symbol: str):
    df = load_bars(symbol)
    if df is None or df.empty:
        return None
    return {"rows": len(df), "last_date": df.index[-1]}


def is_valid(symbol: str, min_rows: int = VALID_MIN_ROWS, stale_days: int = STALE_DAYS) -> bool:
    m = bar_meta(symbol)
    if m is None or m["rows"] < min_rows:
        return False
    return (pd.Timestamp.today().normalize() - m["last_date"].normalize()).days <= stale_days


def status(symbols: List[str]) -> Dict[str, int]:
    cached = valid = stale = 0
    for s in symbols:
        m = bar_meta(s)
        if m is None:
            continue
        cached += 1
        if m["rows"] >= VALID_MIN_ROWS and (pd.Timestamp.today().normalize() - m["last_date"].normalize()).days <= STALE_DAYS:
            valid += 1
        else:
            stale += 1
    total = len(symbols)
    return {"universe_count": total, "cached_count": cached, "valid_count": valid,
            "missing_count": total - cached, "stale_count": stale}


# ----------------------------------------------------- 更新统计持久化
def _stats_path(universe: str) -> str:
    return os.path.join(BARS_DIR, f"_update_{universe}.json")


def save_update_stats(universe: str, stats: dict) -> None:
    os.makedirs(BARS_DIR, exist_ok=True)
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


# --------------------------------------------------- 硬超时调用
def _call_timeout(fn, timeout: float):
    """在守护线程里执行 fn，超时返回 None（线程被放弃，进程退出时随之结束）。"""
    box = {}
    def run():
        try:
            box["v"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["e"] = exc
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return None, TimeoutError("hard timeout")
    return box.get("v"), box.get("e")


# --------------------------------------------------- 单只取数
def _ak_fetch(symbol: str, s: str, e: str) -> Optional[pd.DataFrame]:
    import akshare as ak  # type: ignore

    code = symbol.split(".")[0]
    raw = ak.stock_zh_a_hist(symbol=code, period="daily", start_date=s, end_date=e, adjust="qfq")
    if raw is None or len(raw) == 0 or "收盘" not in raw.columns:
        return None
    raw = raw.copy()
    raw.index = pd.to_datetime(raw["日期"] if "日期" in raw.columns else raw.iloc[:, 0])
    m = {"开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume", "成交额": "amount"}
    df = pd.DataFrame(index=raw.index)
    for zh, col in m.items():
        if zh in raw.columns:
            df[col] = pd.to_numeric(raw[zh], errors="coerce")
    return df if "close" in df.columns else None


def _bs_fetch(bs, symbol: str, start: str, end: str) -> Optional[pd.DataFrame]:
    from aqs.data.directory import to_baostock_symbol

    rs = bs.query_history_k_data_plus(
        to_baostock_symbol(symbol), "date,open,high,low,close,volume,amount",
        start_date=start, end_date=end, frequency="d", adjustflag="2")
    if getattr(rs, "error_code", "1") != "0":
        return None
    raw = rs.get_data()
    if raw is None or raw.empty:
        return None
    raw.index = pd.to_datetime(raw["date"])
    df = pd.DataFrame(index=raw.index)
    for c in ["open", "high", "low", "close", "volume", "amount"]:
        df[c] = pd.to_numeric(raw[c], errors="coerce")
    return df


def update_bars(symbols: List[str], start: str, end: str,
                on_progress: Optional[Callable] = None, force: bool = False,
                per_symbol_timeout: float = 20.0, universe: str = "") -> dict:
    """更新历史行情缓存（AkShare 优先，Baostock 补缺）。返回统计。"""
    import socket

    total = len(symbols)
    cached = success = failed = 0
    failed_syms: List[str] = []
    ak_fail = 0
    ak_off = False
    bs_fail = 0
    bs_off = False
    bs = None
    bs_started = False
    t0 = time.time()
    s_compact = start.replace("-", "")
    e_compact = end.replace("-", "")

    try:
        for i, sym in enumerate(symbols):
            if not force and is_valid(sym):
                cached += 1
                if on_progress:
                    on_progress(i + 1, total, sym, cached, success, failed, time.time() - t0, "cache")
                continue
            df = None
            used = None
            # 1) AkShare（主）
            if not ak_off:
                v, err = _call_timeout(lambda: _ak_fetch(sym, s_compact, e_compact), per_symbol_timeout)
                if v is not None and len(v):
                    df, used, ak_fail = v, "akshare", 0
                else:
                    ak_fail += 1
                    if ak_fail >= 5:
                        ak_off = True
                        print("[data-update] AkShare 连续失败 5 次，暂停 AkShare，改用 Baostock")
            # 2) Baostock（补缺）
            if df is None and not bs_off:
                if not bs_started:
                    bs_started = True
                    try:
                        socket.setdefaulttimeout(per_symbol_timeout)   # 硬超时，避免 recv 永久阻塞
                        import baostock as bs_mod  # type: ignore
                        lg = bs_mod.login()
                        bs = bs_mod if getattr(lg, "error_code", "1") == "0" else None
                        if bs is None:
                            bs_off = True
                    except Exception:
                        bs, bs_off = None, True
                if bs is not None:
                    v, err = _call_timeout(lambda: _bs_fetch(bs, sym, start, end), per_symbol_timeout + 5)
                    if v is not None and len(v):
                        df, used, bs_fail = v, "baostock", 0
                    else:
                        bs_fail += 1
                        if bs_fail >= 3:
                            bs_off = True
                            print("[data-update] Baostock 连续失败 3 次，停止 Baostock")
            if df is not None and len(df):
                save_bars(sym, df, used)
                success += 1
            else:
                failed += 1
                failed_syms.append(sym)
            if on_progress:
                on_progress(i + 1, total, sym, cached, success, failed, time.time() - t0, used or "fail")
    except KeyboardInterrupt:
        print("\n[data-update] 已中断，已成功的数据已保存。")
    finally:
        if bs is not None:
            try:
                bs.logout()
            except Exception:
                pass
        try:
            socket.setdefaulttimeout(None)
        except Exception:
            pass

    stats = {"universe": universe, "total": total, "cached": cached, "success": success,
             "failed": failed, "failed_symbols": failed_syms[:50],
             "elapsed_seconds": round(time.time() - t0, 1)}
    if universe:
        save_update_stats(universe, stats)
    return stats
