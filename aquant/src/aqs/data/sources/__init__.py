"""Real market-data source adapters.

Each adapter pulls data from an external provider and returns a dataset that
:class:`~aqs.data.market_data.MarketDataManager` can load, so the rest of the
system (backtest / risk / compliance / dashboard) is unchanged regardless of
where the data comes from.

Adapters that require a vendor terminal (e.g. Wind) must run on the machine where
that terminal is installed and logged in.
"""

__all__ = ["WindDataSource", "THSDataSource"]


def __getattr__(name):  # lazy import so the package loads without vendor SDKs
    if name == "WindDataSource":
        from aqs.data.sources.wind import WindDataSource

        return WindDataSource
    if name == "THSDataSource":
        from aqs.data.sources.ths import THSDataSource

        return THSDataSource
    raise AttributeError(name)
