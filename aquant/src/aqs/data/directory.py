"""全 A 股股票目录：搜索（代码/名称）、代码解析、自选股。

- 目录优先从 Baostock 拉全 A 股列表并缓存到 ``data/stocks.csv``；失败则用缓存，
  再失败则退回当前已加载数据的标的。
- 支持按代码或名称搜索；支持把"贵州茅台/600519/600519.SH"解析成标准代码。
- 自选股持久化到 ``data/watchlist.csv``。
"""

from __future__ import annotations

import csv
import os
import re
from datetime import date, timedelta
from typing import Dict, List, Optional

_STOCKS_CSV = os.path.join("data", "stocks.csv")
_WATCHLIST_CSV = os.path.join("data", "watchlist.csv")

_DIR_CACHE: Optional[List[dict]] = None


# --------------------------------------------------------------- 代码工具
def normalize_code(q: str) -> Optional[str]:
    """把 '600519' / '600519.SH' / 'sh.600519' 规范成 '600519.SH'。无法识别返回 None。"""
    q = q.strip().upper().replace(" ", "")
    m = re.fullmatch(r"(SH|SZ|BJ)\.?(\d{6})", q)
    if m:
        return f"{m.group(2)}.{m.group(1)}"
    m = re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", q)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    m = re.fullmatch(r"(\d{6})", q)
    if m:
        return f"{m.group(1)}.{_infer_exchange(m.group(1))}"
    return None


def _infer_exchange(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return "SH"
    if code.startswith(("0", "1", "2", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SH"


def _to_our_code(bs_code: str) -> str:
    market, _, code = bs_code.partition(".")
    return f"{code}.{market.upper()}"


# ------------------------------------------------------------- 目录构建
def _latest_all_stock(bs):
    """取最近一个交易日的全市场列表。"""
    cur = date.today()
    for _ in range(10):
        rs = bs.query_all_stock(day=cur.isoformat())
        df = rs.get_data() if getattr(rs, "error_code", "0") == "0" else None
        if df is not None and not df.empty:
            return df
        cur -= timedelta(days=1)
    return None


def _build_from_akshare() -> List[dict]:
    """用 AkShare 拉全 A 股代码+名称（一次性，较快）。"""
    from aqs.data.industry import industry_of

    import akshare as ak  # type: ignore

    df = ak.stock_info_a_code_name()  # columns: code(6位), name
    rows: List[dict] = []
    for _, r in df.iterrows():
        code6 = str(r.get("code", "")).strip()
        if not code6.isdigit() or len(code6) != 6:
            continue
        sym = f"{code6}.{_infer_exchange(code6)}"
        rows.append({"symbol": sym, "name": str(r.get("name", "") or ""),
                     "exchange": sym.split(".")[-1], "industry": industry_of(sym)})
    return rows


def _build_from_baostock() -> List[dict]:
    from aqs.data.industry import industry_of

    import baostock as bs  # type: ignore

    bs.login()
    try:
        df = _latest_all_stock(bs)
        if df is None or df.empty:
            return []
        rows: List[dict] = []
        for _, r in df.iterrows():
            sym = _to_our_code(str(r.get("code", "")))
            code6 = sym.split(".")[0]
            if not code6.isdigit():
                continue
            if sym.endswith(".SH") and code6.startswith(("000",)):
                continue
            if sym.endswith(".SZ") and code6.startswith(("399",)):
                continue
            rows.append({"symbol": sym, "name": str(r.get("code_name", "") or ""),
                         "exchange": sym.split(".")[-1], "industry": industry_of(sym)})
        return rows
    finally:
        bs.logout()


def build_directory(save: bool = True) -> List[dict]:
    """拉全 A 股列表并缓存到 data/stocks.csv（优先 AkShare，回退 Baostock）。"""
    rows: List[dict] = []
    for builder in (_build_from_akshare, _build_from_baostock):
        try:
            rows = builder()
            if rows:
                break
        except Exception as exc:  # noqa: BLE001
            print(f"[directory] {builder.__name__} 失败：{exc}")
    if save and rows:
        os.makedirs("data", exist_ok=True)
        with open(_STOCKS_CSV, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=["symbol", "name", "exchange", "industry"])
            w.writeheader()
            w.writerows(rows)
    return rows


def _load_cache() -> Optional[List[dict]]:
    if not os.path.exists(_STOCKS_CSV):
        return None
    try:
        with open(_STOCKS_CSV, "r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return None


def load_directory(refresh: bool = False) -> List[dict]:
    """返回全市场目录（list of {symbol,name,exchange,industry}）。"""
    global _DIR_CACHE
    if _DIR_CACHE is not None and not refresh:
        return _DIR_CACHE
    rows = None if refresh else _load_cache()
    if rows is None:
        if _configured_source() == "sample":
            # 示例数据模式不联网构建全市场目录，直接用回退目录
            rows = _fallback_directory()
        else:
            try:
                rows = build_directory(save=True)
            except Exception as exc:  # noqa: BLE001
                print(f"[directory] 构建全市场列表失败，使用回退目录：{exc}")
                rows = _fallback_directory()
    if not rows:
        rows = _fallback_directory()
    _DIR_CACHE = rows
    return rows


def _configured_source() -> str:
    try:
        from aqs import service

        return service.DATA_CFG.get("source", "baostock")
    except Exception:
        return "baostock"


def _fallback_directory() -> List[dict]:
    """回退：用当前已加载数据的标的 + 行业映射里的代码。"""
    from aqs.data.industry import load_industry_map, industry_of

    out: Dict[str, dict] = {}
    try:
        from aqs import service

        mgr = service.get_data_manager()
        for sym in mgr.symbols:
            inst = mgr.instrument(sym)
            out[sym] = {"symbol": sym, "name": inst.name if inst else "",
                        "exchange": sym.split(".")[-1], "industry": inst.industry if inst else "未分类"}
    except Exception:
        pass
    for sym in load_industry_map():
        out.setdefault(sym, {"symbol": sym, "name": "", "exchange": sym.split(".")[-1],
                             "industry": industry_of(sym)})
    return list(out.values())


# ----------------------------------------------------------------- 搜索
def search(q: str, limit: int = 20) -> List[dict]:
    q = (q or "").strip()
    rows = load_directory()
    if not q:
        return rows[:limit]
    code = normalize_code(q)
    ql = q.upper()
    exact, partial = [], []
    for r in rows:
        sym = r.get("symbol", "")
        name = str(r.get("name", ""))
        if code and sym == code:
            exact.append(r)
        elif sym.upper().startswith(ql) or ql.replace(".", "") in sym.upper().replace(".", ""):
            partial.append(r)
        elif q in name:
            (exact if name == q else partial).append(r)
    out, seen = [], set()
    for r in exact + partial:
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            out.append(r)
        if len(out) >= limit:
            break
    return out


def resolve(q: str) -> Optional[str]:
    """把代码或名称解析为标准代码；找不到返回 None。"""
    code = normalize_code(q)
    if code:
        return code
    hits = search(q, limit=1)
    return hits[0]["symbol"] if hits else None


def name_of(symbol: str) -> str:
    for r in load_directory():
        if r.get("symbol") == symbol:
            return str(r.get("name", ""))
    return ""


# -------------------------------------------------------------- 自选股
def watchlist() -> List[dict]:
    if not os.path.exists(_WATCHLIST_CSV):
        return []
    try:
        with open(_WATCHLIST_CSV, "r", encoding="utf-8") as fh:
            return list(csv.DictReader(fh))
    except Exception:
        return []


def _save_watchlist(rows: List[dict]) -> None:
    os.makedirs("data", exist_ok=True)
    with open(_WATCHLIST_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "name"])
        w.writeheader()
        w.writerows(rows)


def add_watchlist(query: str) -> dict:
    sym = resolve(query)
    if not sym:
        return {"ok": False, "message": "未找到该股票代码或名称"}
    rows = watchlist()
    if any(r["symbol"] == sym for r in rows):
        return {"ok": True, "symbol": sym, "message": "已在自选股中"}
    rows.append({"symbol": sym, "name": name_of(sym)})
    _save_watchlist(rows)
    return {"ok": True, "symbol": sym, "message": "已加入自选股"}


def remove_watchlist(symbol: str) -> dict:
    sym = normalize_code(symbol) or symbol
    rows = [r for r in watchlist() if r["symbol"] != sym]
    _save_watchlist(rows)
    return {"ok": True, "symbol": sym, "message": "已移除"}
