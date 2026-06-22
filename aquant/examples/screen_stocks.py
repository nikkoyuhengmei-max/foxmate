"""选股器示例：多周期历史 + 量化指标 + (可选)集合竞价，快速筛选 5-10 支候选股。

运行：python examples/screen_stocks.py

接入 iFinD 后，可把集合竞价快照传给选股器（开盘前/开盘时）：
    from aqs.data.sources.ths import THSDataSource
    src = THSDataSource()
    auction = src.get_call_auction(universe)            # 竞价跳空/量比
    data = MarketDataManager.from_ths(universe, start, end)
    picks = Screener().screen(data, top_n=8, auction=auction)
"""

from aqs.data.market_data import MarketDataManager
from aqs.research.screener import Screener


def main() -> None:
    data = MarketDataManager.from_sample()
    picks = Screener().screen(data, top_n=8)
    cols = ["score", "name", "industry", "close", "ret_5d", "ret_20d", "ret_120d", "ret_250d", "rsi", "vol_ratio"]
    cols = [c for c in cols if c in picks.columns]
    print("Top 候选股（示例合成数据，仅演示）:")
    print(picks[cols].to_string())
    print("\n提示：选股结果仅为量化参考，不构成投资建议；请结合风控与人工复核。")


if __name__ == "__main__":
    main()
