"""Data management subsystem.

Covers market data (multi-frequency), fundamentals, A-share specifics
(adjustment factors, ST flags, price limits, suspensions), trading calendar,
data-quality control and a point-in-time (PIT) view to avoid look-ahead bias.
"""

from aqs.data.market_data import MarketDataManager
from aqs.data.calendar import TradingCalendar
from aqs.data.instruments import Instrument, Board, classify_board

__all__ = [
    "MarketDataManager",
    "TradingCalendar",
    "Instrument",
    "Board",
    "classify_board",
]
