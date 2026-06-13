"""Trading calendar for the A-share market.

For a self-contained, offline-runnable system we synthesize a calendar from
weekdays and a configurable holiday set. In production this would be replaced by
an official exchange calendar feed, but the interface stays the same.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, List, Optional, Sequence

import pandas as pd


# A small built-in set of well-known mainland China public holidays is not
# exhaustive; callers may pass their own holiday list. Weekends are always off.
_DEFAULT_HOLIDAYS: set[date] = set()


class TradingCalendar:
    """A weekday-based trading calendar with optional holiday exclusions."""

    def __init__(self, holidays: Optional[Iterable[date]] = None) -> None:
        self.holidays: set[date] = set(holidays) if holidays else set(_DEFAULT_HOLIDAYS)

    def is_trading_day(self, day: date) -> bool:
        if day.weekday() >= 5:  # Sat/Sun
            return False
        return day not in self.holidays

    def sessions(self, start: date, end: date) -> List[pd.Timestamp]:
        """Return all trading sessions in ``[start, end]`` inclusive."""
        out: List[pd.Timestamp] = []
        cur = start
        while cur <= end:
            if self.is_trading_day(cur):
                out.append(pd.Timestamp(cur))
            cur += timedelta(days=1)
        return out

    def next_session(self, day: date) -> pd.Timestamp:
        cur = day + timedelta(days=1)
        while not self.is_trading_day(cur):
            cur += timedelta(days=1)
        return pd.Timestamp(cur)

    def prev_session(self, day: date) -> pd.Timestamp:
        cur = day - timedelta(days=1)
        while not self.is_trading_day(cur):
            cur -= timedelta(days=1)
        return pd.Timestamp(cur)

    def shift(self, day: date, n: int) -> pd.Timestamp:
        """Shift ``n`` trading sessions forward (n>0) or backward (n<0)."""
        cur = pd.Timestamp(day)
        step = 1 if n >= 0 else -1
        for _ in range(abs(n)):
            cur = self.next_session(cur) if step > 0 else self.prev_session(cur)
        return cur

    @staticmethod
    def from_index(index: Sequence[pd.Timestamp]) -> "TradingCalendar":
        """Build a calendar whose trading days are exactly ``index`` (any other
        weekday is treated as a holiday)."""
        idx = pd.DatetimeIndex(index)
        all_days = pd.date_range(idx.min(), idx.max(), freq="D")
        trading = {d.date() for d in idx}
        holidays = {d.date() for d in all_days if d.weekday() < 5 and d.date() not in trading}
        return TradingCalendar(holidays=holidays)
