"""Data-quality control utilities.

Cleans obviously broken bars, reports gaps/duplicates and flags issues that lead
to bad backtests (zero/negative prices, high<low, missing sessions).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np
import pandas as pd


@dataclass
class QualityReport:
    symbol: str
    rows: int
    duplicates: int = 0
    missing_sessions: int = 0
    nan_rows: int = 0
    invalid_ohlc: int = 0
    nonpositive_price: int = 0
    issues: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def check_bars(symbol: str, df: pd.DataFrame, sessions: pd.DatetimeIndex | None = None) -> QualityReport:
    rep = QualityReport(symbol=symbol, rows=len(df))

    dup = int(df.index.duplicated().sum())
    if dup:
        rep.duplicates = dup
        rep.issues.append(f"{dup} duplicate timestamps")

    if sessions is not None:
        expected = pd.DatetimeIndex(sessions)
        missing = expected.difference(df.index)
        if len(missing):
            rep.missing_sessions = len(missing)

    present = df.dropna(subset=["close"])
    rep.nan_rows = len(df) - len(present)

    if len(present):
        invalid = (present["high"] < present["low"]).sum()
        invalid += (present["high"] < present["close"]).sum()
        invalid += (present["low"] > present["close"]).sum()
        rep.invalid_ohlc = int(invalid)
        if invalid:
            rep.issues.append(f"{int(invalid)} bars with inconsistent OHLC")

        nonpos = int((present[["open", "high", "low", "close"]] <= 0).any(axis=1).sum())
        rep.nonpositive_price = nonpos
        if nonpos:
            rep.issues.append(f"{nonpos} bars with non-positive prices")

    return rep


def clean_bars(df: pd.DataFrame) -> pd.DataFrame:
    """Return a cleaned copy: drop duplicate timestamps, repair non-positive
    prices and inconsistent OHLC where possible. Suspended/NaN rows are kept so
    survivorship and suspension handling stays correct downstream."""
    out = df[~df.index.duplicated(keep="last")].copy()
    out = out.sort_index()

    price_cols = ["open", "high", "low", "close"]
    valid = out[price_cols].notna().all(axis=1)
    # Non-positive prices -> mark invalid (NaN) rather than guess.
    nonpos = (out[price_cols] <= 0).any(axis=1) & valid
    out.loc[nonpos, price_cols] = np.nan

    # Repair high/low envelope so high>=max(o,c) and low<=min(o,c).
    rep = out[price_cols].notna().all(axis=1)
    sub = out.loc[rep]
    out.loc[rep, "high"] = sub[["high", "open", "close"]].max(axis=1)
    out.loc[rep, "low"] = sub[["low", "open", "close"]].min(axis=1)
    return out


def quality_summary(reports: Dict[str, QualityReport]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "symbol": r.symbol,
                "rows": r.rows,
                "duplicates": r.duplicates,
                "missing_sessions": r.missing_sessions,
                "nan_rows": r.nan_rows,
                "invalid_ohlc": r.invalid_ohlc,
                "nonpositive_price": r.nonpositive_price,
                "ok": r.ok,
            }
            for r in reports.values()
        ]
    )
