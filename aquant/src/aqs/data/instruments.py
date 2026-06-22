"""Instrument metadata and A-share board classification.

Encodes the differences between the main board, ChiNext (创业板), STAR market
(科创板) and the Beijing Stock Exchange (北交所), plus ST / risk-warning flags,
which drive different price-limit rules in the matching engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Board(str, Enum):
    MAIN = "MAIN"          # 沪深主板
    CHINEXT = "CHINEXT"    # 创业板 (3xxxxx)
    STAR = "STAR"          # 科创板 (688xxx)
    BSE = "BSE"            # 北交所 (8xxxxx / 4xxxxx)
    ETF = "ETF"            # 交易型开放式基金
    CONVERTIBLE = "CB"     # 可转债
    INDEX = "INDEX"        # 指数
    FUTURES = "FUTURES"    # 期货


class AssetType(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    CONVERTIBLE_BOND = "convertible_bond"
    INDEX = "index"
    FUTURES = "futures"
    OPTION = "option"


@dataclass
class Instrument:
    """Static metadata for a tradable instrument."""

    symbol: str                       # e.g. 600000.SH
    name: str = ""
    asset_type: AssetType = AssetType.STOCK
    board: Board = Board.MAIN
    industry: str = "未分类"
    list_date: Optional[str] = None   # IPO 上市日期
    delist_date: Optional[str] = None # 退市日期 (None = 在市)
    is_st: bool = False               # ST / *ST / 风险警示
    lot_size: int = 100

    @property
    def is_active(self) -> bool:
        return self.delist_date is None


def classify_board(symbol: str) -> Board:
    """Infer board from an A-share ticker code.

    Accepts ``600000.SH`` style symbols. Falls back to MAIN.
    """
    code = symbol.split(".")[0]
    if not code.isdigit():
        return Board.MAIN
    if code.startswith("688"):
        return Board.STAR
    if code.startswith("300") or code.startswith("301"):
        return Board.CHINEXT
    if code.startswith(("8", "4", "920")):
        return Board.BSE
    if code.startswith(("11", "12")):
        return Board.CONVERTIBLE
    if code.startswith(("15", "51", "56", "58")):
        return Board.ETF
    return Board.MAIN


def price_limit_ratio(instrument: Instrument, cfg) -> float:
    """Return the daily price-limit ratio for an instrument given config."""
    if instrument.is_st:
        return cfg.price_limit_st
    if instrument.board in (Board.STAR, Board.CHINEXT):
        return cfg.price_limit_star
    if instrument.board == Board.BSE:
        return cfg.price_limit_bse
    if instrument.board in (Board.ETF, Board.INDEX, Board.CONVERTIBLE):
        # ETFs typically ±10%; convertible bonds have their own regime, treated
        # leniently here for the offline simulator.
        return cfg.price_limit_main
    return cfg.price_limit_main
