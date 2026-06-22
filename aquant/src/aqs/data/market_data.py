"""Market data manager with point-in-time (PIT) semantics.

This is the single source of truth that the research, backtest and trading layers
query. Its most important job is *avoiding look-ahead bias*:

* When an ``as_of`` time is set, ``get_price`` never returns bars dated after it.
* ``get_fundamentals`` filters by *disclosure date*, not report period, so a
  strategy can only see a financial figure once it was actually public.

It also exposes A-share specifics: adjustment factors (pre/post/none), ST flags,
suspensions and daily price limits.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Dict, Iterable, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

from aqs.config import SystemConfig, DEFAULT_CONFIG
from aqs.data.calendar import TradingCalendar
from aqs.data.instruments import Instrument, price_limit_ratio
from aqs.data.quality import QualityReport, check_bars, clean_bars, quality_summary
from aqs.data.sample_data import SampleDataset, generate_dataset

Adjust = str  # "none" | "pre" | "post"


class MarketDataManager:
    """Holds bars/fundamentals/metadata and serves PIT-correct queries."""

    def __init__(self, config: SystemConfig = DEFAULT_CONFIG) -> None:
        self.config = config
        self._bars: Dict[str, pd.DataFrame] = {}
        self._adj: Dict[str, pd.Series] = {}
        self._instruments: Dict[str, Instrument] = {}
        self._fundamentals: pd.DataFrame = pd.DataFrame()
        self._benchmark: pd.DataFrame = pd.DataFrame()
        self._benchmark_symbol: str = config.benchmark
        self.calendar: TradingCalendar = TradingCalendar()
        self._as_of: Optional[pd.Timestamp] = None
        self.data_version: str = "uninitialized"

    # ------------------------------------------------------------------ load
    @classmethod
    def from_sample(cls, config: SystemConfig = DEFAULT_CONFIG, **kwargs) -> "MarketDataManager":
        mgr = cls(config)
        mgr.load_dataset(generate_dataset(**kwargs))
        return mgr

    @classmethod
    def from_wind(
        cls,
        symbols,
        start: str,
        end: str,
        benchmark: str = "000300.SH",
        with_fundamentals: bool = True,
        config: SystemConfig = DEFAULT_CONFIG,
    ) -> "MarketDataManager":
        """Build a manager from Wind (万得) data.

        Must run on a machine with the Wind terminal installed and logged in
        (see :mod:`aqs.data.sources.wind`).
        """
        from aqs.data.sources.wind import WindDataSource

        src = WindDataSource()
        ds = src.build_dataset(list(symbols), start, end, benchmark=benchmark, with_fundamentals=with_fundamentals)
        mgr = cls(config)
        mgr.load_dataset(ds)
        return mgr

    @classmethod
    def from_ths(
        cls,
        symbols,
        start: str,
        end: str,
        benchmark: str = "000300.SH",
        with_fundamentals: bool = True,
        username: Optional[str] = None,
        password: Optional[str] = None,
        config: SystemConfig = DEFAULT_CONFIG,
    ) -> "MarketDataManager":
        """Build a manager from 同花顺 iFinD data (requires iFinD pro + API).

        Credentials are read from ``THS_USERNAME`` / ``THS_PASSWORD`` env vars if
        not passed explicitly. See :mod:`aqs.data.sources.ths`.
        """
        from aqs.data.sources.ths import THSDataSource

        src = THSDataSource(username=username, password=password)
        ds = src.build_dataset(list(symbols), start, end, benchmark=benchmark, with_fundamentals=with_fundamentals)
        mgr = cls(config)
        mgr.load_dataset(ds)
        return mgr

    @classmethod
    def from_akshare(
        cls,
        symbols,
        start: str,
        end: str,
        benchmark: str = "000300.SH",
        adjust: str = "qfq",
        with_fundamentals: bool = False,
        cache_dir: Optional[str] = None,
        refresh: bool = False,
        config: SystemConfig = DEFAULT_CONFIG,
    ) -> "MarketDataManager":
        """Build a manager from free AkShare data (no account needed).

        Requires ``pip install akshare`` and internet access. Set ``cache_dir`` to
        fetch once and reuse from disk (avoids repeated rate-limiting).
        ``with_fundamentals`` defaults off to avoid slow per-stock valuation calls.
        """
        from aqs.data.sources.akshare_source import AkShareDataSource
        from aqs.data.cache import cache_key, cached_build

        def _build():
            return AkShareDataSource().build_dataset(
                list(symbols), start, end, benchmark=benchmark, adjust=adjust, with_fundamentals=with_fundamentals
            )

        key = cache_key("akshare", symbols, start, end, benchmark, adjust)
        ds = cached_build(_build, cache_dir, key, refresh)
        mgr = cls(config)
        mgr.load_dataset(ds)
        return mgr

    @classmethod
    def from_baostock(
        cls,
        symbols,
        start: str,
        end: str,
        benchmark: str = "000300.SH",
        adjust: str = "qfq",
        with_fundamentals: bool = True,
        cache_dir: Optional[str] = None,
        refresh: bool = False,
        config: SystemConfig = DEFAULT_CONFIG,
    ) -> "MarketDataManager":
        """Build a manager from free Baostock data (no account, stable server).

        Requires ``pip install baostock``. One K-line query returns OHLCV +
        adjustment + PE(TTM)/PB + ST flag + turnover. Set ``cache_dir`` to reuse
        from disk. See :mod:`aqs.data.sources.baostock_source`.
        """
        from aqs.data.sources.baostock_source import BaostockDataSource
        from aqs.data.cache import cache_key, cached_build

        def _build():
            src = BaostockDataSource()
            try:
                return src.build_dataset(
                    list(symbols), start, end, benchmark=benchmark, adjust=adjust, with_fundamentals=with_fundamentals
                )
            finally:
                src.logout()

        key = cache_key("baostock", symbols, start, end, benchmark, adjust)
        ds = cached_build(_build, cache_dir, key, refresh)
        mgr = cls(config)
        mgr.load_dataset(ds)
        return mgr

    @classmethod
    def from_cache(cls, symbols, names: Optional[dict] = None, benchmark: str = "000300.SH",
                   config: SystemConfig = DEFAULT_CONFIG) -> "MarketDataManager":
        """离线构建：仅从本地行情缓存 data/cache/bars 读取，不联网。"""
        from aqs.data import bars_cache
        from aqs.data.industry import industry_of
        from aqs.data.instruments import AssetType, Instrument, classify_board
        from aqs.data.sample_data import SampleDataset

        names = names or {}
        bars: Dict[str, pd.DataFrame] = {}
        instruments: Dict[str, Instrument] = {}
        adj: Dict[str, pd.Series] = {}
        for sym in symbols:
            df = bars_cache.load_bars(sym)
            if df is None or df.empty:
                continue
            bars[sym] = df
            adj[sym] = pd.Series(1.0, index=df.index)
            nm = names.get(sym, "")
            instruments[sym] = Instrument(symbol=sym, name=nm, asset_type=AssetType.STOCK,
                                          board=classify_board(sym), industry=industry_of(sym),
                                          is_st=("ST" in (nm or "").upper()))
        bench_df = bars_cache.load_bars(benchmark)
        bench = bench_df if bench_df is not None else pd.DataFrame()
        from aqs.data.calendar import TradingCalendar
        if len(bench):
            cal = TradingCalendar.from_index(bench.index)
        elif bars:
            idx = None
            for d in bars.values():
                idx = d.index if idx is None else idx.union(d.index)
            cal = TradingCalendar.from_index(pd.DatetimeIndex(idx)) if idx is not None else TradingCalendar()
        else:
            cal = TradingCalendar()
        ds = SampleDataset(instruments=instruments, bars=bars, benchmark=bench,
                           benchmark_symbol=benchmark, adj_factors=adj,
                           fundamentals=pd.DataFrame(), calendar=cal)
        mgr = cls(config)
        mgr.load_dataset(ds)
        return mgr

    @classmethod
    def from_qmt(
        cls,
        symbols,
        start: str,
        end: str,
        benchmark: str = "000300.SH",
        adjust: str = "qfq",
        cache_dir: Optional[str] = None,
        refresh: bool = False,
        config: SystemConfig = DEFAULT_CONFIG,
    ) -> "MarketDataManager":
        """Build a manager from broker miniQMT data (xtquant).

        Must run on a machine with the QMT/miniQMT client installed and logged in.
        See :mod:`aqs.data.sources.qmt`.
        """
        from aqs.data.sources.qmt import QMTDataSource
        from aqs.data.cache import cache_key, cached_build

        def _build():
            return QMTDataSource().build_dataset(list(symbols), start, end, benchmark=benchmark, adjust=adjust)

        key = cache_key("qmt", symbols, start, end, benchmark, adjust)
        ds = cached_build(_build, cache_dir, key, refresh)
        mgr = cls(config)
        mgr.load_dataset(ds)
        return mgr

    def load_dataset(self, ds: SampleDataset) -> None:
        from aqs.data.industry import fill_missing

        self._instruments = dict(ds.instruments)
        # 用本地行业映射补全缺失行业
        for sym, inst in self._instruments.items():
            inst.industry = fill_missing(inst.industry, sym)
        self._bars = {s: clean_bars(df) for s, df in ds.bars.items()}
        self._adj = dict(ds.adj_factors)
        self._fundamentals = ds.fundamentals.copy()
        self._benchmark = ds.benchmark.copy()
        self._benchmark_symbol = ds.benchmark_symbol
        self.calendar = ds.calendar
        self.data_version = self._compute_version()

    def add_bars(self, symbol: str, df: pd.DataFrame, instrument: Optional[Instrument] = None) -> None:
        self._bars[symbol] = clean_bars(df)
        if instrument is not None:
            self._instruments[symbol] = instrument
        self.data_version = self._compute_version()

    def _compute_version(self) -> str:
        import hashlib

        h = hashlib.sha1()
        for sym in sorted(self._bars):
            df = self._bars[sym]
            h.update(sym.encode())
            h.update(str(len(df)).encode())
            if len(df):
                h.update(str(df.index[-1]).encode())
                # include a content checksum so different data -> different version
                close = df["close"].to_numpy(dtype="float64", na_value=0.0)
                h.update(np.round(close, 4).tobytes())
        return h.hexdigest()[:12]

    # ------------------------------------------------------------ PIT clock
    @property
    def as_of(self) -> Optional[pd.Timestamp]:
        return self._as_of

    def set_as_of(self, when: Optional[Union[str, date, pd.Timestamp]]) -> None:
        self._as_of = None if when is None else pd.Timestamp(when)

    @contextmanager
    def pit(self, when: Union[str, date, pd.Timestamp]):
        """Temporarily pin the PIT clock (look-ahead protection)."""
        prev = self._as_of
        self.set_as_of(when)
        try:
            yield self
        finally:
            self._as_of = prev

    def _clip(self, df: pd.DataFrame) -> pd.DataFrame:
        if self._as_of is not None and len(df):
            return df.loc[df.index <= self._as_of]
        return df

    # ------------------------------------------------------------- universe
    @property
    def symbols(self) -> List[str]:
        return list(self._bars)

    def instrument(self, symbol: str) -> Optional[Instrument]:
        return self._instruments.get(symbol)

    def is_st(self, symbol: str) -> bool:
        inst = self._instruments.get(symbol)
        return bool(inst and inst.is_st)

    def is_active(self, symbol: str, when: Optional[pd.Timestamp] = None) -> bool:
        inst = self._instruments.get(symbol)
        if inst is None:
            return False
        if inst.delist_date is None:
            return True
        when = when or self._as_of
        if when is None:
            return inst.is_active
        return pd.Timestamp(when) < pd.Timestamp(inst.delist_date)

    def _session_index(self) -> pd.DatetimeIndex:
        """Master session list: benchmark index, or union of all bar indices
        when no benchmark is available (e.g. the data source failed to fetch it)."""
        if len(self._benchmark):
            return pd.DatetimeIndex(self._benchmark.index)
        if not self._bars:
            return pd.DatetimeIndex([])
        union = None
        for df in self._bars.values():
            union = df.index if union is None else union.union(df.index)
        return pd.DatetimeIndex(union if union is not None else [])

    def trading_dates(self, start=None, end=None) -> pd.DatetimeIndex:
        idx = self._session_index()
        if start is not None:
            idx = idx[idx >= pd.Timestamp(start)]
        if end is not None:
            idx = idx[idx <= pd.Timestamp(end)]
        if self._as_of is not None:
            idx = idx[idx <= self._as_of]
        return pd.DatetimeIndex(idx)

    # --------------------------------------------------------------- prices
    def _apply_adjust(self, symbol: str, df: pd.DataFrame, adjust: Adjust) -> pd.DataFrame:
        if adjust == "none" or symbol not in self._adj:
            return df
        factor = self._adj[symbol].reindex(df.index).ffill().fillna(1.0)
        out = df.copy()
        price_cols = ["open", "high", "low", "close"]
        if adjust == "post":  # 后复权
            mult = factor
        elif adjust == "pre":  # 前复权: normalise so latest factor == 1
            mult = factor / factor.iloc[-1]
        else:
            return df
        for c in price_cols:
            out[c] = out[c] * mult
        return out

    def get_price(
        self,
        symbol: str,
        start=None,
        end=None,
        fields: Optional[Sequence[str]] = None,
        adjust: Adjust = "none",
    ) -> pd.DataFrame:
        """Return a (clipped, optionally adjusted) bar DataFrame for ``symbol``."""
        if symbol not in self._bars:
            raise KeyError(f"unknown symbol: {symbol}")
        df = self._clip(self._bars[symbol])
        if start is not None:
            df = df.loc[df.index >= pd.Timestamp(start)]
        if end is not None:
            df = df.loc[df.index <= pd.Timestamp(end)]
        df = self._apply_adjust(symbol, df, adjust)
        if fields is not None:
            df = df[list(fields)]
        return df

    def get_bar(self, symbol: str, when: Union[str, pd.Timestamp]) -> Optional[pd.Series]:
        """Latest bar at-or-before ``when`` (None if suspended/missing)."""
        when = pd.Timestamp(when)
        if self._as_of is not None and when > self._as_of:
            when = self._as_of
        df = self._bars.get(symbol)
        if df is None:
            return None
        sub = df.loc[df.index <= when]
        if not len(sub):
            return None
        row = sub.iloc[-1]
        if bool(row.get("suspended", False)) or pd.isna(row.get("close", np.nan)):
            return None
        return row

    def current_price(self, symbol: str, when: Union[str, pd.Timestamp], field: str = "close") -> Optional[float]:
        row = self.get_bar(symbol, when)
        if row is None:
            return None
        val = row.get(field)
        return None if pd.isna(val) else float(val)

    def is_suspended(self, symbol: str, when: Union[str, pd.Timestamp]) -> bool:
        when = pd.Timestamp(when)
        df = self._bars.get(symbol)
        if df is None or when not in df.index:
            return True
        row = df.loc[when]
        return bool(row.get("suspended", False)) or pd.isna(row.get("close", np.nan))

    def price_limits(self, symbol: str, when: Union[str, pd.Timestamp]) -> Optional[tuple[float, float]]:
        """Return (upper_limit, lower_limit) based on previous close."""
        when = pd.Timestamp(when)
        df = self._bars.get(symbol)
        inst = self._instruments.get(symbol)
        if df is None or inst is None:
            return None
        prev = df.loc[df.index < when]
        prev = prev.dropna(subset=["close"])
        if not len(prev):
            return None
        prev_close = float(prev["close"].iloc[-1])
        ratio = price_limit_ratio(inst, self.config.rules)
        upper = round(prev_close * (1 + ratio), 2)
        lower = round(prev_close * (1 - ratio), 2)
        return upper, lower

    def at_upper_limit(self, symbol: str, when) -> bool:
        limits = self.price_limits(symbol, when)
        px = self.current_price(symbol, when, "close")
        return bool(limits and px is not None and px >= limits[0] - 1e-9)

    def at_lower_limit(self, symbol: str, when) -> bool:
        limits = self.price_limits(symbol, when)
        px = self.current_price(symbol, when, "close")
        return bool(limits and px is not None and px <= limits[1] + 1e-9)

    # --------------------------------------------------------- fundamentals
    def get_fundamentals(
        self,
        symbols: Union[str, Iterable[str]],
        when: Optional[Union[str, pd.Timestamp]] = None,
        fields: Optional[Sequence[str]] = None,
    ) -> pd.DataFrame:
        """PIT fundamentals: only rows disclosed at-or-before ``when``.

        Returns the latest disclosed record per symbol.
        """
        if self._fundamentals.empty:
            return pd.DataFrame()
        when = pd.Timestamp(when) if when is not None else self._as_of
        if isinstance(symbols, str):
            symbols = [symbols]
        symbols = list(symbols)
        f = self._fundamentals
        f = f[f["symbol"].isin(symbols)]
        if when is not None:
            f = f[f["disclosure_date"] <= when]
        if f.empty:
            return pd.DataFrame()
        latest = f.sort_values("disclosure_date").groupby("symbol").tail(1)
        latest = latest.set_index("symbol")
        if fields is not None:
            keep = [c for c in fields if c in latest.columns]
            latest = latest[keep]
        return latest

    # ------------------------------------------------------------ benchmark
    @property
    def benchmark_symbol(self) -> str:
        return self._benchmark_symbol

    def benchmark(self, start=None, end=None) -> pd.DataFrame:
        df = self._clip(self._benchmark)
        if start is not None:
            df = df.loc[df.index >= pd.Timestamp(start)]
        if end is not None:
            df = df.loc[df.index <= pd.Timestamp(end)]
        return df

    # ------------------------------------------------------- quality checks
    def run_quality_checks(self) -> pd.DataFrame:
        sessions = self._benchmark.index
        reports: Dict[str, QualityReport] = {}
        for sym, df in self._bars.items():
            reports[sym] = check_bars(sym, df, sessions)
        return quality_summary(reports)
