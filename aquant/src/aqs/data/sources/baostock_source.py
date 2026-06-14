"""Baostock 数据源适配器（免费、免注册、较稳定）。

Baostock 提供自有数据服务器（非爬网页），对密集请求基本不限流，适合个人 PC 取
A 股历史数据。一次 K 线查询即可拿到 OHLCV + 复权 + PE(TTM)/PB + 是否 ST + 换手率。

安装：``pip install baostock``。无实时行情/集合竞价（如需实时请用 AkShare 或券商 miniQMT）。
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from aqs.data.calendar import TradingCalendar
from aqs.data.instruments import AssetType, Instrument, classify_board
from aqs.data.sample_data import SampleDataset


def _to_our_code(bs_code: str) -> str:
    """'sh.600519' -> '600519.SH'。"""
    market, _, code = bs_code.partition(".")
    return f"{code}.{market.upper()}"


def fetch_index_constituents(name: str) -> List[str]:
    """获取指数成分股（'hs300'|'zz500'|'sz50'），返回本系统代码格式列表。"""
    try:
        import baostock as bs  # type: ignore
    except Exception as exc:
        raise ImportError("未找到 baostock。请先安装：pip install baostock") from exc
    fn = {
        "hs300": "query_hs300_stocks",
        "zz500": "query_zz500_stocks",
        "sz50": "query_sz50_stocks",
    }.get(name.lower())
    if fn is None:
        raise ValueError(f"未知指数 universe: {name}")
    lg = bs.login()
    try:
        rs = getattr(bs, fn)()
        if getattr(rs, "error_code", "0") != "0":
            raise RuntimeError(rs.error_msg)
        df = rs.get_data()
        col = "code" if "code" in df.columns else df.columns[-1]
        return [_to_our_code(c) for c in df[col].tolist()]
    finally:
        bs.logout()


def _bs_code(symbol: str) -> str:
    """'600519.SH' -> 'sh.600519'；'000001.SZ' -> 'sz.000001'。"""
    code, _, suffix = symbol.partition(".")
    suffix = suffix.upper()
    if suffix == "SH":
        return f"sh.{code}"
    if suffix == "SZ":
        return f"sz.{code}"
    # 指数等按代码推断
    return f"sh.{code}" if code.startswith(("0", "6", "9")) else f"sz.{code}"


# adjustflag: 1=后复权 2=前复权 3=不复权
_ADJUST = {"qfq": "2", "hfq": "1", "": "3", "none": "3"}


class BaostockDataSource:
    def __init__(self) -> None:
        try:
            import baostock as bs  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local install
            raise ImportError("未找到 baostock。请先安装：pip install baostock") from exc
        self.bs = bs
        lg = bs.login()
        if getattr(lg, "error_code", "0") != "0":
            raise RuntimeError(f"Baostock 登录失败: {lg.error_msg}")

    def logout(self) -> None:
        try:
            self.bs.logout()
        except Exception:
            pass

    # --------------------------------------------------------------- bars
    def get_bars(self, symbols: Sequence[str], start: str, end: str, adjust: str = "qfq"):
        fields = "date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ,isST"
        flag = _ADJUST.get(adjust, "2")
        bars: Dict[str, pd.DataFrame] = {}
        adj: Dict[str, pd.Series] = {}
        st_map: Dict[str, bool] = {}
        fund_rows: List[dict] = []
        for sym in symbols:
            rs = self.bs.query_history_k_data_plus(
                _bs_code(sym), fields, start_date=start, end_date=end, frequency="d", adjustflag=flag
            )
            if getattr(rs, "error_code", "0") != "0":
                print(f"[Baostock] 行情跳过 {sym}: {rs.error_msg}")
                continue
            raw = rs.get_data()
            if raw is None or raw.empty:
                continue
            raw.index = pd.to_datetime(raw["date"])
            num = lambda c: pd.to_numeric(raw[c], errors="coerce")
            df = pd.DataFrame({
                "open": num("open"), "high": num("high"), "low": num("low"),
                "close": num("close"), "volume": num("volume"), "amount": num("amount"),
            }, index=raw.index)
            df["suspended"] = df["volume"].fillna(0).le(0)
            bars[sym] = df
            adj[sym] = pd.Series(1.0, index=df.index)  # 已按 adjustflag 复权
            # 是否 ST（取最近一日）
            if "isST" in raw.columns and len(raw):
                st_map[sym] = str(raw["isST"].iloc[-1]) == "1"
            # 基本面：PE(TTM)/PB 月末抽样
            fdf = pd.DataFrame({"pe": num("peTTM"), "pb": num("pbMRQ")}, index=raw.index)
            monthly = fdf.resample("ME").last().dropna(how="all")
            for ts, r in monthly.iterrows():
                fund_rows.append({
                    "symbol": sym, "report_period": ts, "disclosure_date": ts,
                    "pe": float(r["pe"]) if pd.notna(r["pe"]) else np.nan,
                    "pb": float(r["pb"]) if pd.notna(r["pb"]) else np.nan,
                    "roe": np.nan, "revenue_yoy": np.nan, "net_profit_yoy": np.nan,
                })
        fundamentals = pd.DataFrame(fund_rows) if fund_rows else pd.DataFrame()
        return bars, adj, st_map, fundamentals

    # -------------------------------------------------------- instruments
    def get_instruments(self, symbols: Sequence[str], st_map: Dict[str, bool]) -> Dict[str, Instrument]:
        out: Dict[str, Instrument] = {}
        for sym in symbols:
            name, list_date, delist_date = "", None, None
            try:
                rs = self.bs.query_stock_basic(code=_bs_code(sym))
                d = rs.get_data() if getattr(rs, "error_code", "0") == "0" else None
                if d is not None and not d.empty:
                    row = d.iloc[0]
                    name = str(row.get("code_name", "") or "")
                    ld = row.get("ipoDate")
                    od = row.get("outDate")
                    list_date = str(ld) if ld else None
                    delist_date = str(od) if od and str(od) not in ("", "nan") else None
            except Exception as exc:
                print(f"[Baostock] 基础信息缺失 {sym}: {exc}")
            out[sym] = Instrument(
                symbol=sym, name=name, asset_type=AssetType.STOCK, board=classify_board(sym),
                list_date=list_date, delist_date=delist_date,
                is_st=st_map.get(sym, "ST" in name.upper()),
            )
        return out

    # ---------------------------------------------------------- benchmark
    def get_benchmark(self, benchmark: str, start: str, end: str) -> pd.DataFrame:
        rs = self.bs.query_history_k_data_plus(
            _bs_code(benchmark), "date,open,high,low,close,volume,amount",
            start_date=start, end_date=end, frequency="d", adjustflag="3",
        )
        if getattr(rs, "error_code", "0") != "0":
            print(f"[Baostock] 指数获取失败 {benchmark}: {rs.error_msg}")
            return pd.DataFrame()
        raw = rs.get_data()
        if raw is None or raw.empty:
            return pd.DataFrame()
        raw.index = pd.to_datetime(raw["date"])
        num = lambda c: pd.to_numeric(raw[c], errors="coerce")
        out = pd.DataFrame({c: num(c) for c in ["open", "high", "low", "close", "volume", "amount"]}, index=raw.index)
        out["suspended"] = False
        return out

    # ----------------------------------------------------------- calendar
    def trading_calendar(self, start: str, end: str) -> TradingCalendar:
        try:
            rs = self.bs.query_trade_dates(start_date=start, end_date=end)
            d = rs.get_data()
            trading = d[d["is_trading_day"] == "1"]["calendar_date"]
            return TradingCalendar.from_index(pd.DatetimeIndex(pd.to_datetime(trading)))
        except Exception as exc:
            print(f"[Baostock] 交易日历回退: {exc}")
            return TradingCalendar()

    # --------------------------------------------------------- build all
    def build_dataset(
        self, symbols: Sequence[str], start: str, end: str,
        benchmark: str = "000300.SH", adjust: str = "qfq", with_fundamentals: bool = True,
    ) -> SampleDataset:
        bars, adj, st_map, fundamentals = self.get_bars(symbols, start, end, adjust=adjust)
        instruments = self.get_instruments(symbols, st_map)
        bench = self.get_benchmark(benchmark, start, end)
        cal = self.trading_calendar(start, end)
        if not with_fundamentals:
            fundamentals = pd.DataFrame()
        return SampleDataset(
            instruments=instruments, bars=bars, benchmark=bench, benchmark_symbol=benchmark,
            adj_factors=adj, fundamentals=fundamentals, calendar=cal,
        )
