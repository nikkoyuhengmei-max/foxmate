import pandas as pd
import pytest

from aqs.data.market_data import MarketDataManager
from aqs.research.screener import Screener, ScreenConfig


@pytest.fixture(scope="module")
def mdm():
    return MarketDataManager.from_sample(end="2023-12-31")


def test_screen_returns_top_n(mdm):
    df = Screener().screen(mdm, top_n=5)
    assert not df.empty
    assert len(df) <= 5
    assert "score" in df.columns
    # sorted by score descending
    assert df["score"].is_monotonic_decreasing


def test_screen_excludes_st(mdm):
    df = Screener(ScreenConfig(exclude_st=True)).screen(mdm, top_n=20)
    for sym in df.index:
        inst = mdm.instrument(sym)
        assert not (inst and inst.is_st)


def test_screen_pit_no_lookahead(mdm):
    # screening as-of an early date must not leak future data
    df = Screener().screen(mdm, asof="2021-06-30", top_n=5)
    assert not df.empty
    # PIT clock restored after screen
    assert mdm.as_of is None


def test_screen_auction_factor(mdm):
    universe = mdm.symbols[:6]
    auction = {s: {"gap": 0.02 if i == 0 else -0.01, "auction_vol_ratio": 2.0 if i == 0 else 1.0}
               for i, s in enumerate(universe)}
    df = Screener().screen(mdm, universe=universe, auction=auction, top_n=6)
    assert "auction_gap" in df.columns
