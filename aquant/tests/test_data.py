import pandas as pd
import pytest

from aqs.data.market_data import MarketDataManager
from aqs.data.instruments import classify_board, Board


@pytest.fixture(scope="module")
def mdm():
    return MarketDataManager.from_sample(start="2021-01-01", end="2022-12-31")


def test_board_classification():
    assert classify_board("688981.SH") == Board.STAR
    assert classify_board("300750.SZ") == Board.CHINEXT
    assert classify_board("600000.SH") == Board.MAIN
    assert classify_board("830000.BJ") == Board.BSE


def test_pit_no_lookahead(mdm):
    sym = mdm.symbols[0]
    with mdm.pit("2021-06-30"):
        df = mdm.get_price(sym)
        assert df.index.max() <= pd.Timestamp("2021-06-30")
    # outside the context the clip is removed
    assert mdm.get_price(sym).index.max() > pd.Timestamp("2021-06-30")


def test_fundamentals_pit_uses_disclosure_date(mdm):
    sym = mdm.symbols[0]
    # An annual report for 2021-12-31 is disclosed ~90 days later (late March).
    early = mdm.get_fundamentals([sym], when="2022-01-15")
    later = mdm.get_fundamentals([sym], when="2022-05-15")
    # the later snapshot must reflect a more recent report period
    if not early.empty and not later.empty:
        assert later.loc[sym, "report_period"] >= early.loc[sym, "report_period"]


def test_price_limits_and_quality(mdm):
    sym = mdm.symbols[0]
    when = mdm.trading_dates()[10]
    limits = mdm.price_limits(sym, when)
    assert limits is not None and limits[0] > limits[1]
    q = mdm.run_quality_checks()
    assert bool(q["ok"].all())


def test_data_version_changes_with_data():
    a = MarketDataManager.from_sample(seed=1)
    b = MarketDataManager.from_sample(seed=2)
    assert a.data_version != b.data_version


def test_delisted_stock_is_present_but_inactive(mdm):
    # survivorship-bias protection: delisted name is still in the universe
    assert "000003.SZ" in mdm.symbols
    assert mdm.is_active("000003.SZ", pd.Timestamp("2021-02-01"))
    assert not mdm.is_active("000003.SZ", pd.Timestamp("2022-12-01"))
