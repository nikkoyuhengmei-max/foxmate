"""AkShare 数据源适配器（免费、免注册）。

AkShare 是开源免费的财经数据库，抓取东方财富/新浪等公开数据，**无需账号或 API 权限**，
非常适合个人 PC 上做 A 股量化。

安装：``pip install akshare``（需要联网访问相关数据站点）。

本适配器把 AkShare 的行情/基本面/指数拉成 :class:`SampleDataset`，交给
:class:`MarketDataManager` 使用，其余（回测/选股/风控/合规/仪表盘）逻辑不变。

说明：AkShare 默认返回的历史价已可选择复权方式（默认前复权 qfq）；实时与集合竞价
依赖东方财富快照接口。接口字段偶有变动，若报错把报错发我即可适配。
"""

from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from aqs.data.calendar import TradingCalendar
from aqs.data.instruments import AssetType, Instrument, classify_board
from aqs.data.sample_data import SampleDataset


# 历史行情中文列 -> 内部列名
_HIST_COLS = {
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
}


def _code(symbol: str) -> str:
    """'600519.SH' -> '600519'。"""
    return symbol.split(".")[0]


def _index_code(symbol: str) -> str:
    """'000300.SH' -> 'sh000300'（东方财富/新浪指数代码）。"""
    code = symbol.split(".")[0]
    suffix = symbol.split(".")[-1].upper() if "." in symbol else ""
    if suffix == "SH" or code.startswith(("000", "880", "999")):
        return f"sh{code}"
    if suffix == "SZ" or code.startswith("399"):
        return f"sz{code}"
    return f"sh{code}"


class AkShareDataSource:
    def __init__(self) -> None:
        try:
            import akshare as ak  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local install
            raise ImportError("未找到 akshare。请先安装：pip install akshare") from exc
        self.ak = ak
        self.request_delay = 0.0
        self.max_workers = 8   # 并发抓取行情

    _BACKOFF = [1.0, 3.0]   # 最多重试 2 次：等待 1s、3s

    def _retry(self, fn: Callable, *args, **kwargs):
        """带退避的重试（1s、3s），捕获空响应/连接错误/JSON 解析错误。"""
        last: Optional[Exception] = None
        for i in range(len(self._BACKOFF) + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:  # noqa: BLE001
                last = exc
                if i < len(self._BACKOFF):
                    time.sleep(self._BACKOFF[i])
        raise last  # type: ignore[misc]

    # --------------------------------------------------------------- bars
    def _fetch_one(self, sym: str, s: str, e: str, adjust: str):
        raw = self._retry(self.ak.stock_zh_a_hist, symbol=_code(sym), period="daily",
                          start_date=s, end_date=e, adjust=adjust)
        if raw is None or len(raw) == 0:
            return sym, None
        # 按字段名选择，避免 df.columns=[...] 造成列数不匹配
        date_col = "日期" if "日期" in raw.columns else (raw.columns[0] if len(raw.columns) else None)
        if date_col is None or "收盘" not in raw.columns:
            return sym, None
        raw = raw.copy()
        raw.index = pd.to_datetime(raw[date_col])
        df = pd.DataFrame(index=raw.index)
        for zh, col in _HIST_COLS.items():
            if zh in raw.columns:
                df[col] = pd.to_numeric(raw[zh], errors="coerce")
        if "close" not in df.columns:
            return sym, None
        df["suspended"] = False
        return sym, df

    def get_bars(
        self, symbols: Sequence[str], start: str, end: str, adjust: str = "qfq"
    ) -> tuple[Dict[str, pd.DataFrame], Dict[str, pd.Series]]:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        s = start.replace("-", "")
        e = end.replace("-", "")
        bars: Dict[str, pd.DataFrame] = {}
        adj: Dict[str, pd.Series] = {}
        symbols = list(symbols)
        failed: List[str] = []
        workers = min(self.max_workers, max(1, len(symbols)))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(self._fetch_one, sym, s, e, adjust): sym for sym in symbols}
            for fut in as_completed(futs):
                sym = futs[fut]
                try:
                    sym, df = fut.result()
                except Exception:  # noqa: BLE001 — 不逐只刷屏，汇总统计
                    failed.append(sym)
                    continue
                if df is None:
                    failed.append(sym)
                    continue
                bars[sym] = df
                adj[sym] = pd.Series(1.0, index=df.index)
        self.last_stats = {"total": len(symbols), "success": len(bars), "failed": len(failed),
                           "failed_symbols": failed}
        if failed:
            print(f"[AkShare] 行情：成功 {len(bars)} 只，失败 {len(failed)} 只（已跳过）")
        return bars, adj

    # -------------------------------------------------------- instruments
    def get_instruments(self, symbols: Sequence[str]) -> Dict[str, Instrument]:
        """不再逐只联网请求基础信息（避免限流/空响应刷屏）。

        名称在选股时由 universe 缓存批量补全；行业用本地映射；ST 由名称判断。
        """
        from aqs.data.industry import industry_of

        out: Dict[str, Instrument] = {}
        for sym in symbols:
            out[sym] = Instrument(
                symbol=sym, name="", asset_type=AssetType.STOCK,
                board=classify_board(sym), industry=industry_of(sym), is_st=False,
            )
        return out

    # ------------------------------------------------------- fundamentals
    def _valuation_series(self, code: str, indicator: str) -> pd.Series:
        df = self._retry(self.ak.stock_zh_valuation_baidu, symbol=code, indicator=indicator, period="全部")
        time.sleep(self.request_delay)
        if df is None or df.empty:
            return pd.Series(dtype=float)
        s = pd.Series(pd.to_numeric(df["value"], errors="coerce").values, index=pd.to_datetime(df["date"]))
        return s

    def get_fundamentals(self, symbols: Sequence[str], start: str, end: str) -> pd.DataFrame:
        """历史 PE(TTM)/PB（来自百度股市通），按月抽样，disclosure=采样日（PIT）。"""
        rows = []
        for sym in symbols:
            try:
                pe = self._valuation_series(_code(sym), "市盈率(TTM)")
                pb = self._valuation_series(_code(sym), "市净率")
            except Exception as exc:
                print(f"[AkShare] 基本面跳过 {sym}: {exc}")
                continue
            if pe.empty and pb.empty:
                continue
            df = pd.DataFrame({"pe": pe, "pb": pb}).sort_index()
            df = df.loc[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
            monthly = df.resample("ME").last().dropna(how="all")
            for ts, r in monthly.iterrows():
                rows.append(
                    {
                        "symbol": sym,
                        "report_period": ts,
                        "disclosure_date": ts,
                        "pe": float(r["pe"]) if pd.notna(r.get("pe")) else np.nan,
                        "pb": float(r["pb"]) if pd.notna(r.get("pb")) else np.nan,
                        "roe": np.nan,
                        "revenue_yoy": np.nan,
                        "net_profit_yoy": np.nan,
                    }
                )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values(["symbol", "disclosure_date"]).reset_index(drop=True)

    # ---------------------------------------------------------- benchmark
    def get_benchmark(self, benchmark: str, start: str, end: str) -> pd.DataFrame:
        try:
            df = self._retry(self.ak.stock_zh_index_daily_em, symbol=_index_code(benchmark))
            time.sleep(self.request_delay)
        except Exception as exc:
            print(f"[AkShare] 指数获取失败 {benchmark}: {exc}")
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()
        df = df.copy()
        df.index = pd.to_datetime(df["date"])
        df = df.loc[(df.index >= pd.Timestamp(start)) & (df.index <= pd.Timestamp(end))]
        keep = {c: c for c in ["open", "high", "low", "close", "volume", "amount"] if c in df.columns}
        out = df[list(keep)].apply(pd.to_numeric, errors="coerce")
        out["suspended"] = False
        return out

    # ------------------------------------------------------ call auction
    def get_call_auction(self, symbols: Optional[Sequence[str]] = None) -> Dict[str, Dict[str, float]]:
        """用东方财富实时快照近似集合竞价信号：{code.SH: {gap: 当日涨跌幅, auction_vol_ratio: 量比}}。

        更精确的 9:25 竞价可用 ``stock_zh_a_hist_pre_min_em`` 取盘前分钟；此处用快照便于全市场。
        """
        try:
            spot = self.ak.stock_zh_a_spot_em()
        except Exception as exc:
            print(f"[AkShare] 实时快照失败: {exc}")
            return {}
        out: Dict[str, Dict[str, float]] = {}
        want = {_code(s) for s in symbols} if symbols else None
        for _, r in spot.iterrows():
            code = str(r.get("代码", ""))
            if want is not None and code not in want:
                continue
            gap = r.get("涨跌幅")
            vr = r.get("量比")
            suffix = "SH" if code.startswith(("6", "5", "688", "9")) else "SZ"
            out[f"{code}.{suffix}"] = {
                "gap": float(gap) / 100.0 if pd.notna(gap) else np.nan,
                "auction_vol_ratio": float(vr) if pd.notna(vr) else np.nan,
            }
        return out

    # --------------------------------------------------------- build all
    def build_dataset(
        self,
        symbols: Sequence[str],
        start: str,
        end: str,
        benchmark: str = "000300.SH",
        adjust: str = "qfq",
        with_fundamentals: bool = True,
    ) -> SampleDataset:
        bars, adj = self.get_bars(symbols, start, end, adjust=adjust)
        instruments = self.get_instruments(symbols)
        bench = self.get_benchmark(benchmark, start, end)
        # 交易日历：用基准指数（若为空则用任一只股票）的日期推断
        ref_index = bench.index if len(bench) else (next(iter(bars.values())).index if bars else pd.DatetimeIndex([]))
        cal = TradingCalendar.from_index(ref_index) if len(ref_index) else TradingCalendar()
        fundamentals = self.get_fundamentals(symbols, start, end) if with_fundamentals else pd.DataFrame()
        return SampleDataset(
            instruments=instruments,
            bars=bars,
            benchmark=bench,
            benchmark_symbol=benchmark,
            adj_factors=adj,
            fundamentals=fundamentals,
            calendar=cal,
        )
