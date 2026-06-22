"""券商 miniQMT 数据源适配器（基于 xtquant.xtdata）。

REQUIREMENTS / 使用前提
--------------------------------------------------------------------------
1. 在**安装并登录了券商 QMT / miniQMT 客户端**的机器上运行（数据由本地客户端提供）。
2. 账号已开通 QMT/miniQMT 权限（通常开一个普通证券账户并向券商申请即可，免数据费）。
3. 安装 xtquant（随 QMT 客户端附带的 Python 库）。

提供历史日线、实时行情订阅与**集合竞价快照**，代码格式与本系统一致（如 600519.SH）。
本文件按 xtquant 公开用法编写，需在你的 QMT 机器上实跑验证；字段/接口随版本略有差异，
报错发我即可适配。
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from aqs.data.calendar import TradingCalendar
from aqs.data.instruments import AssetType, Instrument, classify_board
from aqs.data.sample_data import SampleDataset


_DIVIDEND = {"qfq": "front", "hfq": "back", "": "none", "none": "none"}


class QMTDataSource:
    def __init__(self) -> None:
        try:
            from xtquant import xtdata  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local install
            raise ImportError("未找到 xtquant。请在装有券商 QMT/miniQMT 客户端的机器上安装 xtquant。") from exc
        self.xtdata = xtdata

    # --------------------------------------------------------------- bars
    def get_bars(self, symbols: Sequence[str], start: str, end: str, adjust: str = "qfq"):
        s = start.replace("-", "")
        e = end.replace("-", "")
        div = _DIVIDEND.get(adjust, "front")
        bars: Dict[str, pd.DataFrame] = {}
        adj: Dict[str, pd.Series] = {}
        fields = ["open", "high", "low", "close", "volume", "amount"]
        for sym in symbols:
            try:
                self.xtdata.download_history_data(sym, period="1d", start_time=s, end_time=e)
                res = self.xtdata.get_market_data_ex(
                    fields, [sym], period="1d", start_time=s, end_time=e, dividend_type=div
                )
            except Exception as exc:
                print(f"[QMT] 行情跳过 {sym}: {exc}")
                continue
            raw = res.get(sym) if isinstance(res, dict) else None
            if raw is None or len(raw) == 0:
                continue
            raw = raw.copy()
            raw.index = pd.to_datetime(raw.index.astype(str), format="%Y%m%d", errors="coerce")
            df = pd.DataFrame(index=raw.index)
            for c in fields:
                if c in raw.columns:
                    df[c] = pd.to_numeric(raw[c], errors="coerce")
            df["suspended"] = df["volume"].fillna(0).le(0)
            bars[sym] = df
            adj[sym] = pd.Series(1.0, index=df.index)
        return bars, adj

    # -------------------------------------------------------- instruments
    def get_instruments(self, symbols: Sequence[str]) -> Dict[str, Instrument]:
        out: Dict[str, Instrument] = {}
        for sym in symbols:
            name, list_date = "", None
            try:
                d = self.xtdata.get_instrument_detail(sym) or {}
                name = str(d.get("InstrumentName", "") or "")
                od = d.get("OpenDate")
                if od and str(od) not in ("0", "", "nan"):
                    list_date = str(pd.to_datetime(str(od), format="%Y%m%d", errors="coerce").date())
            except Exception as exc:
                print(f"[QMT] 基础信息缺失 {sym}: {exc}")
            out[sym] = Instrument(
                symbol=sym, name=name, asset_type=AssetType.STOCK, board=classify_board(sym),
                list_date=list_date, is_st=("ST" in name.upper()),
            )
        return out

    # ---------------------------------------------------------- benchmark
    def get_benchmark(self, benchmark: str, start: str, end: str) -> pd.DataFrame:
        bars, _ = self.get_bars([benchmark], start, end, adjust="none")
        return bars.get(benchmark, pd.DataFrame())

    # ------------------------------------------------------ call auction
    def get_call_auction(self, symbols: Sequence[str]) -> Dict[str, Dict[str, float]]:
        """开盘集合竞价快照：{代码: {gap: 相对昨收涨跌幅, auction_vol_ratio: 竞价量(手)}}。"""
        out: Dict[str, Dict[str, float]] = {}
        try:
            ticks = self.xtdata.get_full_tick(list(symbols))
        except Exception as exc:
            print(f"[QMT] 竞价快照失败: {exc}")
            return out
        for sym, t in (ticks or {}).items():
            try:
                last = float(t.get("lastPrice", t.get("open", np.nan)))
                prev = float(t.get("lastClose", np.nan))
                vol = float(t.get("volume", np.nan))
                gap = (last / prev - 1.0) if prev else np.nan
                out[sym] = {"gap": gap, "auction_vol_ratio": vol}
            except Exception:
                continue
        return out

    def subscribe_realtime(self, symbol: str, callback: Callable, period: str = "tick"):
        """订阅实时行情（盘中策略用）。callback(data) 在每次推送时触发。"""
        return self.xtdata.subscribe_quote(symbol, period=period, callback=callback)

    # --------------------------------------------------------- build all
    def build_dataset(
        self, symbols: Sequence[str], start: str, end: str,
        benchmark: str = "000300.SH", adjust: str = "qfq", with_fundamentals: bool = False,
    ) -> SampleDataset:
        bars, adj = self.get_bars(symbols, start, end, adjust=adjust)
        instruments = self.get_instruments(symbols)
        bench = self.get_benchmark(benchmark, start, end)
        ref = bench.index if len(bench) else (next(iter(bars.values())).index if bars else pd.DatetimeIndex([]))
        cal = TradingCalendar.from_index(ref) if len(ref) else TradingCalendar()
        return SampleDataset(
            instruments=instruments, bars=bars, benchmark=bench, benchmark_symbol=benchmark,
            adj_factors=adj, fundamentals=pd.DataFrame(), calendar=cal,
        )
