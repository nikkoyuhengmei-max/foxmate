"""用 Baostock（免费、稳定、免注册）取真实数据并选股 + 回测。

首次联网取数后会写入本地缓存目录 .cache/，之后秒读、不再反复联网（避免限流）。
安装：pip install baostock
运行：python examples/load_baostock_data.py
"""

from aqs.data.market_data import MarketDataManager
from aqs.research.screener import Screener
from aqs.strategy.templates import MultiFactor
from aqs.backtest.engine import BacktestEngine
from aqs.risk.manager import RiskManager
from aqs.compliance.monitor import ComplianceMonitor
from aqs.performance.metrics import analyze


UNIVERSE = [
    "600519.SH", "600036.SH", "601318.SH", "000333.SZ",
    "300750.SZ", "000001.SZ", "600276.SH", "002594.SZ",
]
START, END = "2022-01-01", "2023-12-31"


def main() -> None:
    print("从 Baostock 取真实数据（首次联网，之后走本地缓存）...")
    data = MarketDataManager.from_baostock(UNIVERSE, START, END, cache_dir=".cache")

    print("\n== 选股 Top 8 ==")
    picks = Screener().screen(data, top_n=8)
    cols = [c for c in ["score", "name", "industry", "close", "ret_5d", "ret_20d", "ret_120d", "rsi"] if c in picks.columns]
    print(picks[cols].to_string())

    print("\n== 多因子回测 ==")
    res = BacktestEngine(data, MultiFactor(top_n=4), risk_manager=RiskManager(),
                         compliance=ComplianceMonitor(), fill_mode="next_open").run()
    print(analyze(res.equity_curve, res.benchmark).summary_text())


if __name__ == "__main__":
    main()
