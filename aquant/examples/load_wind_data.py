"""用 Wind 真实数据跑回测的示例。

前提：本脚本必须在**安装并登录了 Wind 金融终端**、且装好 WindPy 的机器上运行。
运行：python examples/load_wind_data.py
"""

from aqs.data.market_data import MarketDataManager
from aqs.strategy.templates import MultiFactor
from aqs.backtest.engine import BacktestEngine
from aqs.risk.manager import RiskManager
from aqs.compliance.monitor import ComplianceMonitor
from aqs.performance.metrics import analyze


# 你关注的股票池（Wind 代码格式）与回测区间
UNIVERSE = [
    "600519.SH", "600036.SH", "601318.SH", "000333.SZ",
    "300750.SZ", "688981.SH", "000001.SZ", "600276.SH",
]
START, END = "2021-01-01", "2023-12-31"
BENCHMARK = "000300.SH"   # 沪深300


def main() -> None:
    print("正在从 Wind 拉取数据（需 Wind 终端已登录）...")
    data = MarketDataManager.from_wind(UNIVERSE, START, END, benchmark=BENCHMARK)

    print("数据质量检查:")
    print(data.run_quality_checks().to_string(index=False))

    engine = BacktestEngine(
        data,
        MultiFactor(top_n=4, rebalance="monthly"),
        risk_manager=RiskManager(),
        compliance=ComplianceMonitor(),
        fill_mode="next_open",
    )
    result = engine.run()
    print("\n" + analyze(result.equity_curve, result.benchmark).summary_text())
    print("数据版本:", result.data_version)


if __name__ == "__main__":
    main()
