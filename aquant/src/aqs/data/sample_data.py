"""Synthetic A-share dataset generator.

So the whole system is runnable offline without a paid data vendor, this module
produces a realistic-looking universe of daily OHLCV bars, a benchmark index,
adjustment factors, suspension flags and point-in-time fundamentals.

The generated data deliberately includes the messy bits that matter for honest
backtesting: a delisted stock (survivorship bias test), an ST stock, suspended
sessions, and fundamentals tagged with a real *disclosure date* that lags the
*report period* (look-ahead protection).
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from aqs.data.calendar import TradingCalendar
from aqs.data.instruments import AssetType, Board, Instrument, classify_board


_INDUSTRIES = ["银行", "白酒", "医药", "半导体", "新能源", "地产", "券商", "消费"]

_UNIVERSE = [
    # symbol, name, industry, board hint
    ("600000.SH", "示例银行", "银行", Board.MAIN),
    ("600519.SH", "示例白酒", "白酒", Board.MAIN),
    ("600276.SH", "示例医药", "医药", Board.MAIN),
    ("000001.SZ", "示例平安", "银行", Board.MAIN),
    ("000333.SZ", "示例美的", "消费", Board.MAIN),
    ("300750.SZ", "示例电池", "新能源", Board.CHINEXT),
    ("300059.SZ", "示例东财", "券商", Board.CHINEXT),
    ("688981.SH", "示例芯片", "半导体", Board.STAR),
    ("688111.SH", "示例软件", "半导体", Board.STAR),
    ("000002.SZ", "示例地产", "地产", Board.MAIN),
    ("601318.SH", "示例保险", "银行", Board.MAIN),
    ("002594.SZ", "示例车企", "新能源", Board.MAIN),
]


def _simulate_price_path(
    n: int,
    start_price: float,
    drift: float,
    vol: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Geometric-brownian-ish daily close path."""
    shocks = rng.normal(loc=drift, scale=vol, size=n)
    log_path = np.cumsum(shocks)
    return start_price * np.exp(log_path)


def generate_dataset(
    start: str = "2021-01-01",
    end: str = "2023-12-31",
    seed: int = 7,
    include_delisted: bool = True,
) -> "SampleDataset":
    """Generate a deterministic synthetic dataset."""
    rng = np.random.default_rng(seed)
    cal = TradingCalendar()
    sessions = cal.sessions(date.fromisoformat(start), date.fromisoformat(end))
    idx = pd.DatetimeIndex(sessions)
    n = len(idx)

    instruments: Dict[str, Instrument] = {}
    bars: Dict[str, pd.DataFrame] = {}
    adj_factors: Dict[str, pd.Series] = {}

    universe = list(_UNIVERSE)
    if include_delisted:
        universe.append(("000003.SZ", "示例退市", "地产", Board.MAIN))

    for symbol, name, industry, board in universe:
        start_price = float(rng.uniform(8, 80))
        drift = float(rng.normal(0.0004, 0.0003))
        vol = float(rng.uniform(0.015, 0.035))
        close = _simulate_price_path(n, start_price, drift, vol, rng)

        # Build OHLC around close.
        intraday = np.abs(rng.normal(0.0, vol, size=n))
        high = close * (1 + intraday)
        low = close * (1 - intraday)
        open_ = np.concatenate([[close[0]], close[:-1]]) * (1 + rng.normal(0, vol / 2, n))
        open_ = np.clip(open_, low, high)
        volume = rng.uniform(5e6, 8e7, size=n) * (1 + np.abs(rng.normal(0, 0.5, n)))
        amount = volume * close

        df = pd.DataFrame(
            {
                "open": np.round(open_, 2),
                "high": np.round(high, 2),
                "low": np.round(low, 2),
                "close": np.round(close, 2),
                "volume": np.round(volume, 0),
                "amount": np.round(amount, 0),
                "suspended": False,
            },
            index=idx,
        )

        is_st = False
        delist_date: Optional[str] = None

        if symbol == "000003.SZ":
            # Delisted partway through: NaN out the tail to emulate delisting.
            cutoff = int(n * 0.6)
            price_cols = ["open", "high", "low", "close", "volume", "amount"]
            df.iloc[cutoff:, [df.columns.get_loc(c) for c in price_cols]] = np.nan
            df.iloc[cutoff:, df.columns.get_loc("suspended")] = True
            delist_date = str(idx[cutoff].date())
            is_st = True

        if symbol == "000002.SZ":
            # Mark as ST for the second half of the sample.
            is_st = True

        # Random multi-day suspensions for a couple of names.
        if symbol in ("688111.SH", "002594.SZ"):
            sstart = int(n * 0.3)
            df.iloc[sstart : sstart + 5, df.columns.get_loc("suspended")] = True

        bars[symbol] = df

        # Adjustment factor: a single dividend event mid-sample bumps the factor.
        factor = pd.Series(1.0, index=idx)
        ex_div = int(n * 0.5)
        factor.iloc[ex_div:] = 1.0 / 0.98  # ~2% cash dividend
        adj_factors[symbol] = factor

        instruments[symbol] = Instrument(
            symbol=symbol,
            name=name,
            asset_type=AssetType.STOCK,
            board=board if board else classify_board(symbol),
            industry=industry,
            list_date=str(idx[0].date()),
            delist_date=delist_date,
            is_st=is_st,
            lot_size=100,
        )

    # Benchmark index (CSI 300 proxy): broad-market drift, lower vol.
    bench_close = _simulate_price_path(n, 4000.0, 0.0002, 0.011, rng)
    benchmark = pd.DataFrame(
        {
            "open": np.round(bench_close, 2),
            "high": np.round(bench_close * 1.005, 2),
            "low": np.round(bench_close * 0.995, 2),
            "close": np.round(bench_close, 2),
            "volume": rng.uniform(1e9, 2e9, n),
            "amount": rng.uniform(1e11, 2e11, n),
            "suspended": False,
        },
        index=idx,
    )

    fundamentals = _generate_fundamentals(list(instruments), idx, rng)

    return SampleDataset(
        instruments=instruments,
        bars=bars,
        benchmark=benchmark,
        benchmark_symbol="000300.SH",
        adj_factors=adj_factors,
        fundamentals=fundamentals,
        calendar=cal,
    )


def _generate_fundamentals(
    symbols: List[str], idx: pd.DatetimeIndex, rng: np.random.Generator
) -> pd.DataFrame:
    """Quarterly fundamentals with a *disclosure date* that lags the report
    period (PIT correctness)."""
    rows = []
    years = sorted({d.year for d in idx})
    # Report period end -> typical disclosure lag (days).
    quarters = [
        ("03-31", 30),   # Q1 reported by end of April
        ("06-30", 60),   # H1 reported by end of August
        ("09-30", 30),   # Q3 reported by end of October
        ("12-31", 90),   # Annual reported by end of March next year
    ]
    for sym in symbols:
        base_roe = float(rng.uniform(0.05, 0.25))
        base_pe = float(rng.uniform(8, 45))
        for yr in years:
            for q_end, lag in quarters:
                report_period = pd.Timestamp(f"{yr}-{q_end}")
                disclosure = report_period + pd.Timedelta(days=lag)
                rows.append(
                    {
                        "symbol": sym,
                        "report_period": report_period,
                        "disclosure_date": disclosure,
                        "pe": round(base_pe * float(rng.uniform(0.8, 1.2)), 2),
                        "pb": round(float(rng.uniform(0.8, 6)), 2),
                        "roe": round(base_roe * float(rng.uniform(0.8, 1.2)), 4),
                        "revenue_yoy": round(float(rng.normal(0.1, 0.2)), 4),
                        "net_profit_yoy": round(float(rng.normal(0.1, 0.3)), 4),
                    }
                )
    df = pd.DataFrame(rows)
    return df.sort_values(["symbol", "disclosure_date"]).reset_index(drop=True)


class SampleDataset:
    """Container bundling everything :class:`MarketDataManager` needs."""

    def __init__(
        self,
        instruments: Dict[str, Instrument],
        bars: Dict[str, pd.DataFrame],
        benchmark: pd.DataFrame,
        benchmark_symbol: str,
        adj_factors: Dict[str, pd.Series],
        fundamentals: pd.DataFrame,
        calendar: TradingCalendar,
    ) -> None:
        self.instruments = instruments
        self.bars = bars
        self.benchmark = benchmark
        self.benchmark_symbol = benchmark_symbol
        self.adj_factors = adj_factors
        self.fundamentals = fundamentals
        self.calendar = calendar
