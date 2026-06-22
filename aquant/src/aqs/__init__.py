"""AQuant - A-share quantitative trading system.

A local-first, modular quant platform for the Chinese A-share market covering the
full loop: data management -> research -> backtest -> paper trading -> live
execution -> risk control -> compliance -> performance review -> monitoring.

The package is intentionally split into independent sub-packages so that the
core engine (data, backtest, risk, compliance, performance) runs with only
``numpy`` and ``pandas`` while heavier features (web dashboard, machine
learning) are optional extras.
"""

from __future__ import annotations

__version__ = "0.1.0"

from aqs.data.market_data import MarketDataManager
from aqs.backtest.engine import BacktestEngine
from aqs.strategy.api import Strategy

__all__ = [
    "__version__",
    "MarketDataManager",
    "BacktestEngine",
    "Strategy",
]
