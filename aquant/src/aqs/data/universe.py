"""股票池加载与缓存。

加载顺序（可被 refresh / source 覆盖）：
1) 本地缓存  data/cache/universe/{hs300,zz500,sz50,all_a}.csv
2) AkShare   指数成分 / 全A 列表
3) Baostock  指数成分 / 全A 列表

三者都失败时返回明确错误，**不返回伪造的小样本池**。
缓存 CSV 字段：symbol,name,exchange,industry,source,updated_at
"""

from __future__ import annotations

import csv
import os
import time
from datetime import datetime
from typing import Dict, List, Optional

CACHE_DIR = os.path.join("data", "cache", "universe")
_FILES = {"hs300": "hs300.csv", "zz500": "zz500.csv", "sz50": "sz50.csv", "all": "all_a.csv"}
_INDEX_CODE = {"hs300": "000300", "zz500": "000905", "sz50": "000016"}
_FIELDS = ["symbol", "name", "exchange", "industry", "source", "updated_at"]


def _infer_exchange(code: str) -> str:
    if code.startswith(("6", "5", "9")):
        return "SH"
    if code.startswith(("0", "1", "2", "3")):
        return "SZ"
    if code.startswith(("4", "8")):
        return "BJ"
    return "SH"


def _to_sym(code6: str) -> str:
    return f"{code6}.{_infer_exchange(code6)}"


def cache_path(name: str) -> str:
    return os.path.join(CACHE_DIR, _FILES.get(name, f"{name}.csv"))


def _retry(fn, tries=3, base=0.8):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(base * (2 ** i))
    raise last


# ----------------------------------------------------------------- AkShare
def _ak_index(name: str) -> List[dict]:
    import akshare as ak  # type: ignore
    from aqs.data.industry import industry_of

    sym = _INDEX_CODE[name]
    df = _retry(lambda: ak.index_stock_cons_csindex(symbol=sym))
    code_col = next((c for c in df.columns if "成分券代码" in c or "成份券代码" in c or c in ("品种代码", "代码")), None)
    name_col = next((c for c in df.columns if "成分券名称" in c or "成份券名称" in c or c in ("品种名称", "名称")), None)
    rows = []
    for _, r in df.iterrows():
        c = str(r[code_col]).strip().zfill(6)
        if not (c.isdigit() and len(c) == 6):
            continue
        sym_full = _to_sym(c)
        nm = str(r[name_col]) if name_col else ""
        rows.append({"symbol": sym_full, "name": nm, "exchange": sym_full.split(".")[-1],
                     "industry": industry_of(sym_full), "source": "akshare"})
    return rows


def _ak_all() -> List[dict]:
    import akshare as ak  # type: ignore
    from aqs.data.industry import industry_of

    rows = []
    # 优先 spot_em（含名称），失败再 stock_info_a_code_name
    try:
        df = _retry(lambda: ak.stock_zh_a_spot_em())
        for _, r in df.iterrows():
            c = str(r.get("代码", "")).strip()
            if c.isdigit() and len(c) == 6:
                s = _to_sym(c)
                rows.append({"symbol": s, "name": str(r.get("名称", "") or ""), "exchange": s.split(".")[-1],
                             "industry": industry_of(s), "source": "akshare"})
        if rows:
            return rows
    except Exception:
        pass
    df = _retry(lambda: ak.stock_info_a_code_name())
    for _, r in df.iterrows():
        c = str(r.get("code", "")).strip()
        if c.isdigit() and len(c) == 6:
            s = _to_sym(c)
            rows.append({"symbol": s, "name": str(r.get("name", "") or ""), "exchange": s.split(".")[-1],
                         "industry": industry_of(s), "source": "akshare"})
    return rows


# ---------------------------------------------------------------- Baostock
def _bs_index(name: str) -> List[dict]:
    import baostock as bs  # type: ignore
    from aqs.data.industry import industry_of

    fn = {"hs300": "query_hs300_stocks", "zz500": "query_zz500_stocks", "sz50": "query_sz50_stocks"}[name]
    bs.login()
    try:
        rs = getattr(bs, fn)()
        if getattr(rs, "error_code", "1") != "0":
            raise RuntimeError(rs.error_msg)
        df = rs.get_data()
        rows = []
        col = "code" if "code" in df.columns else df.columns[-1]
        ncol = "code_name" if "code_name" in df.columns else None
        for _, r in df.iterrows():
            market, _, code = str(r[col]).partition(".")
            s = f"{code}.{market.upper()}"
            rows.append({"symbol": s, "name": str(r[ncol]) if ncol else "", "exchange": market.upper(),
                         "industry": industry_of(s), "source": "baostock"})
        return rows
    finally:
        bs.logout()


def _bs_all() -> List[dict]:
    import baostock as bs  # type: ignore
    from datetime import date, timedelta
    from aqs.data.industry import industry_of

    bs.login()
    try:
        cur = date.today()
        df = None
        for _ in range(10):
            rs = bs.query_all_stock(day=cur.isoformat())
            d = rs.get_data() if getattr(rs, "error_code", "1") == "0" else None
            if d is not None and not d.empty:
                df = d
                break
            cur -= timedelta(days=1)
        if df is None:
            return []
        rows = []
        for _, r in df.iterrows():
            market, _, code = str(r.get("code", "")).partition(".")
            if not code.isdigit() or len(code) != 6:
                continue
            s = f"{code}.{market.upper()}"
            if s.endswith(".SH") and code.startswith("000"):
                continue
            if s.endswith(".SZ") and code.startswith("399"):
                continue
            rows.append({"symbol": s, "name": str(r.get("code_name", "") or ""), "exchange": market.upper(),
                         "industry": industry_of(s), "source": "baostock"})
        return rows
    finally:
        bs.logout()


# ------------------------------------------------------------------- cache
def read_cache(name: str) -> Optional[List[dict]]:
    path = cache_path(name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
        return rows or None
    except Exception:
        return None


def save_cache(name: str, rows: List[dict], source: str) -> str:
    path = cache_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({"symbol": r.get("symbol", ""), "name": r.get("name", ""),
                        "exchange": r.get("exchange", ""), "industry": r.get("industry", ""),
                        "source": source, "updated_at": now})
    return path


def load(name: str, source: Optional[str] = None, refresh: bool = False) -> Dict:
    """加载股票池，返回诊断信息。source 可强制 akshare/baostock。"""
    name = str(name).lower()
    errors: List[str] = []
    path = cache_path(name)

    # 1) 缓存
    if not refresh and source is None:
        cached = read_cache(name)
        if cached:
            updated = cached[0].get("updated_at")
            return {"name": name, "source": "cache", "rows": cached,
                    "symbols": [r["symbol"] for r in cached], "raw_count": len(cached),
                    "cache_path": path, "updated_at": updated, "errors": []}

    # 2/3) AkShare -> Baostock（或按 source 指定）
    order = [source] if source else ["akshare", "baostock"]
    for src in order:
        try:
            if name == "all":
                rows = _ak_all() if src == "akshare" else _bs_all()
            elif name in _INDEX_CODE:
                rows = _ak_index(name) if src == "akshare" else _bs_index(name)
            else:
                rows = []
            if rows:
                save_cache(name, rows, src)
                return {"name": name, "source": src, "rows": rows,
                        "symbols": [r["symbol"] for r in rows], "raw_count": len(rows),
                        "cache_path": path, "updated_at": "刚刚", "errors": errors}
            errors.append(f"{src} 返回空")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{src}: {exc}")

    # 都失败：尝试旧缓存兜底（明确标注）
    cached = read_cache(name)
    if cached:
        errors.append("实时获取失败，使用旧缓存")
        return {"name": name, "source": "cache(stale)", "rows": cached,
                "symbols": [r["symbol"] for r in cached], "raw_count": len(cached),
                "cache_path": path, "updated_at": cached[0].get("updated_at"), "errors": errors}

    return {"name": name, "source": "none", "rows": [], "symbols": [], "raw_count": 0,
            "cache_path": path, "updated_at": None,
            "errors": errors or ["数据源没有返回股票（AkShare/Baostock 均失败或缓存为空）"]}
