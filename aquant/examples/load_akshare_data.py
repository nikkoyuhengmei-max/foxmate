"""用免费的 AkShare 真实数据跑「选股 + 回测」（无需账号）。

安装：pip install akshare
运行：python examples/load_akshare_data.py
"""

from aqs.data.market_data import MarketDataManager
from aqs.research.screener import Screener
from aqs.strategy.templates import MultiFactor
from aqs.backtest.engine import BacktestEngine
from aqs.risk.manager import RiskManager
from aqs.compliance.monitor import ComplianceMonitor
from aqs.performance.metrics import analyze


# 你的自选股池（A 股代码.交易所）
UNIVERSE = [
    "600519.SH", "600036.SH", "601318.SH", "000333.SZ",
    "300750.SZ", "000001.SZ", "600276.SH", "002594.SZ",
]
START, END = "2022-01-01", "2023-12-31"
BENCHMARK = "000300.SH"


def main() -> None:
    print("从 AkShare 拉取真实数据（需联网，免账号）...")
    data = MarketDataManager.from_akshare(UNIVERSE, START, END, benchmark=BENCHMARK)

    print("\n== 选股 Top 8 ==")
    picks = Screener().screen(data, top_n=8)
    cols = [c for c in ["score", "name", "industry", "close", "ret_5d", "ret_20d", "ret_120d", "rsi"] if c in picks.columns]
    print(picks[cols].to_string())

    print("\n== 多因子回测 ==")
    engine = BacktestEngine(data, MultiFactor(top_n=4), risk_manager=RiskManager(),
                            compliance=ComplianceMonitor(), fill_mode="next_open")
    res = engine.run()
    print(analyze(res.equity_curve, res.benchmark).summary_text())


if __name__ == "__main__":
    main()
