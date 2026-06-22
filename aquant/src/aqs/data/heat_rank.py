"""热度榜（人气榜）股票池：统一接口 + 东方财富实现 + 本地缓存（离线）。

第一版数据源：AKShare 东方财富股票人气榜 stock_hot_rank_em（官方稳定接口）。
预留 TonghuashunHeatProvider / ManualHeatProvider（本版不实现同花顺网页抓取）。

缓存：data/cache/heat_rank/{date}.parquet 与 latest.parquet
字段：date,snapshot_time,rank,symbol,name,latest_price,pct_change,heat_score,source,updated_at

原则：
- 禁止 mock 数据填补失败；接口失败时保留旧缓存并标注旧日期，不覆盖有效缓存。
- 热度更新（联网）与离线选股分离；screen 只读缓存。
- 每日快照按日期保存，供历史/回测使用；回测只能用当日已存在的快照。
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from aqs.data.bars_cache import _call_timeout

HEAT_DIR = os.path.join("data", "cache", "heat_rank")
_COLS = ["date", "snapshot_time", "rank", "symbol", "name", "latest_price",
         "pct_change", "heat_score", "source", "updated_at"]


def _em_symbol(s: str) -> str:
    s = str(s).strip().upper()
    if s[:2] in ("SH", "SZ", "BJ"):
        return f"{s[2:]}.{s[:2]}"
    if s[:2] in ("60", "68", "11", "51"):
        return f"{s}.SH"
    return f"{s}.SZ"


# ----------------------------------------------------------------- Providers
class HeatRankProvider:
    source = "base"

    def fetch(self, top: int = 100, timeout: float = 15.0) -> pd.DataFrame:
        raise NotImplementedError


class EastmoneyHeatProvider(HeatRankProvider):
    source = "eastmoney"

    def fetch(self, top: int = 100, timeout: float = 15.0) -> pd.DataFrame:
        def _go():
            import akshare as ak  # type: ignore
            return ak.stock_hot_rank_em()
        raw, err = _call_timeout(_go, timeout)
        if raw is None:
            raise RuntimeError(f"东方财富人气榜请求失败/超时：{err or '无响应'}")
        if len(raw) == 0 or "代码" not in raw.columns:
            raise RuntimeError("东方财富人气榜返回为空")
        raw = raw.head(top).copy()
        out = pd.DataFrame()
        out["rank"] = pd.to_numeric(raw["当前排名"], errors="coerce")
        out["symbol"] = raw["代码"].map(_em_symbol)
        out["name"] = raw["股票名称"].astype(str)
        out["latest_price"] = pd.to_numeric(raw.get("最新价"), errors="coerce")
        out["pct_change"] = pd.to_numeric(raw.get("涨跌幅"), errors="coerce")
        out = out.dropna(subset=["rank", "symbol"]).sort_values("rank")
        out["heat_score"] = (101 - out["rank"]).clip(lower=1, upper=100)
        return out


class TonghuashunHeatProvider(HeatRankProvider):
    source = "tonghuashun"

    def fetch(self, top: int = 100, timeout: float = 15.0) -> pd.DataFrame:
        raise NotImplementedError("本版未实现同花顺网页抓取热度榜。")


class ManualHeatProvider(HeatRankProvider):
    source = "manual"

    def fetch(self, top: int = 100, timeout: float = 15.0) -> pd.DataFrame:
        p = os.path.join(HEAT_DIR, "manual.csv")
        if not os.path.exists(p):
            raise RuntimeError(f"未找到人工热度榜文件：{p}")
        df = pd.read_csv(p, dtype={"symbol": str}).head(top)
        if "symbol" not in df.columns:
            raise RuntimeError("manual.csv 缺少 symbol 列")
        df["rank"] = range(1, len(df) + 1)
        df["heat_score"] = (101 - df["rank"]).clip(lower=1, upper=100)
        for c in ("name", "latest_price", "pct_change"):
            if c not in df.columns:
                df[c] = None
        return df[["rank", "symbol", "name", "latest_price", "pct_change", "heat_score"]]


_PROVIDERS = {"eastmoney": EastmoneyHeatProvider, "tonghuashun": TonghuashunHeatProvider,
              "manual": ManualHeatProvider}


def get_provider(source: str = "eastmoney") -> HeatRankProvider:
    cls = _PROVIDERS.get(str(source).lower())
    if cls is None:
        raise ValueError(f"未知热度榜来源：{source}（可用：{', '.join(_PROVIDERS)}）")
    return cls()


# ----------------------------------------------------------------- I/O
def date_path(date: str) -> str:
    return os.path.join(HEAT_DIR, f"{date}.parquet")


def latest_path() -> str:
    return os.path.join(HEAT_DIR, "latest.parquet")


def load_latest() -> Optional[pd.DataFrame]:
    p = latest_path()
    if not os.path.exists(p):
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def load_for_date(date: str) -> Optional[pd.DataFrame]:
    p = date_path(date)
    if not os.path.exists(p):
        return None
    try:
        return pd.read_parquet(p)
    except Exception:
        return None


def available_dates() -> List[str]:
    if not os.path.isdir(HEAT_DIR):
        return []
    return sorted(f[:-8] for f in os.listdir(HEAT_DIR)
                  if f.endswith(".parquet") and f != "latest.parquet")


def update_heat(source: str = "eastmoney", top: int = 100, timeout: float = 15.0) -> Dict:
    """联网更新热度榜并写入缓存。失败时保留旧缓存，返回 stale 信息。"""
    provider = get_provider(source)
    now = datetime.now()
    date = now.strftime("%Y-%m-%d")
    try:
        df = provider.fetch(top=top, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        old = load_latest()
        old_date = str(old["date"].iloc[0]) if old is not None and "date" in old and len(old) else None
        return {"success": False, "source": source, "error": str(exc),
                "stale": old is not None, "last_date": old_date,
                "count": int(len(old)) if old is not None else 0}
    df = df.copy()
    df["date"] = date
    df["snapshot_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
    df["source"] = source
    df["updated_at"] = now.strftime("%Y-%m-%d %H:%M:%S")
    for c in _COLS:
        if c not in df.columns:
            df[c] = None
    df = df[_COLS]
    os.makedirs(HEAT_DIR, exist_ok=True)
    df.to_parquet(date_path(date), index=False)        # 历史快照（按日期，不覆盖）
    df.to_parquet(latest_path(), index=False)          # 最新
    return {"success": True, "source": source, "date": date,
            "snapshot_time": df["snapshot_time"].iloc[0], "count": int(len(df))}


def status() -> Dict:
    latest = load_latest()
    dates = available_dates()
    if latest is None:
        return {"available": False, "count": 0, "date": None, "snapshot_time": None,
                "source": None, "updated_at": None, "history_days": len(dates)}
    return {"available": True, "count": int(len(latest)),
            "date": str(latest["date"].iloc[0]) if "date" in latest else None,
            "snapshot_time": str(latest["snapshot_time"].iloc[0]) if "snapshot_time" in latest else None,
            "source": str(latest["source"].iloc[0]) if "source" in latest else None,
            "updated_at": str(latest["updated_at"].iloc[0]) if "updated_at" in latest else None,
            "history_days": len(dates)}


def _snapshot(asof: Optional[str] = None) -> Optional[pd.DataFrame]:
    """返回用于该时点的热度快照：asof 给定则只用当日快照（缺失返回 None），否则用 latest。"""
    if asof:
        return load_for_date(str(asof)[:10])
    return load_latest()


def top_symbols(top: int = 100, asof: Optional[str] = None) -> List[str]:
    df = _snapshot(asof)
    if df is None or len(df) == 0:
        return []
    return df.sort_values("rank").head(top)["symbol"].tolist()


def names_map(asof: Optional[str] = None) -> Dict[str, str]:
    df = _snapshot(asof)
    if df is None:
        return {}
    return {r["symbol"]: r.get("name", "") for _, r in df.iterrows()}


def heat_map(asof: Optional[str] = None, top: int = 100) -> Dict[str, dict]:
    """返回 {symbol: {heat_rank, heat_score, heat_source, heat_updated}}（离线，仅读缓存）。"""
    df = _snapshot(asof)
    if df is None or len(df) == 0:
        return {}
    df = df.sort_values("rank").head(top)
    out = {}
    for _, r in df.iterrows():
        out[r["symbol"]] = {
            "heat_rank": int(r["rank"]),
            "heat_score": float(r["heat_score"]),
            "heat_source": str(r.get("source", "")),
            "heat_updated": str(r.get("snapshot_time", "")),
        }
    return out
