"""Factor research + trend-forecast example.

Run from the project root:  python examples/research_forecast.py
"""

import json

from aqs.data.market_data import MarketDataManager
from aqs.ml.forecast import analyze_and_forecast


def main() -> None:
    data = MarketDataManager.from_sample()

    # Point-in-time fundamentals snapshot (no look-ahead).
    snap = data.get_fundamentals(data.symbols[:5], when="2022-06-30",
                                 fields=["pe", "pb", "roe", "revenue_yoy"])
    print("PIT 基本面快照 @2022-06-30:")
    print(snap.to_string())

    print("\n走势分析与预测 (示例):")
    for sym in ["600519.SH", "300750.SZ", "688981.SH"]:
        res = analyze_and_forecast(data, sym, horizon=5)
        print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
