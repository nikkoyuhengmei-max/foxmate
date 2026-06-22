"""Trading subsystem: broker gateway, OMS, EMS and paper-trading sandbox.

The same :class:`~aqs.strategy.api.Context` contract used in backtest is provided
here, so a strategy moves backtest -> paper -> live unchanged. A
:class:`SimulatedBroker` lets you paper-trade against (replayed or live) market
data without sending real orders; a real broker is added by implementing
:class:`BrokerGateway`.
"""

from aqs.trading.broker import BrokerGateway, SimulatedBroker, BrokerAccount
from aqs.trading.oms import OrderManagementSystem
from aqs.trading.ems import ExecutionManagementSystem
from aqs.trading.trader import PaperTrader

__all__ = [
    "BrokerGateway",
    "SimulatedBroker",
    "BrokerAccount",
    "OrderManagementSystem",
    "ExecutionManagementSystem",
    "PaperTrader",
    "QMTBroker",
]


def __getattr__(name):  # lazy import so package loads without xtquant
    if name == "QMTBroker":
        from aqs.trading.qmt_broker import QMTBroker

        return QMTBroker
    raise AttributeError(name)
