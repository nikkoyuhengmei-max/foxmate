"""用同花顺 iFinD 真实数据跑回测的示例。

前提：iFinD 专业版 + 数据 API 权限，已安装 iFinDPy SDK。
账号通过环境变量提供（不要写进代码）：
    export THS_USERNAME=你的账号
    export THS_PASSWORD=你的密码
运行：python examples/load_ths_data.py
"""

from aqs.data.market_data import MarketDataManager
from aqs.strategy.templates import MultiFactor
from aqs.backtest.engine import BacktestEngine
from aqs.risk.manager import RiskManager
from aqs.compliance.monitor import ComplianceMonitor
from aqs.performance.metrics import analyze


UNIVERSE = [
    "600519.SH", "600036.SH", "601318.SH", "000333.SZ",
    "300750.SZ", "688981.SH", "000001.SZ", "600276.SH",
]
START, END = "2021-01-01", "2023-12-31"
BENCHMARK = "000300.SH"


def main() -> None:
    print("正在从同花顺 iFinD 拉取数据（需已设置 THS_USERNAME/THS_PASSWORD 且开通 API）...")
    data = MarketDataManager.from_ths(UNIVERSE, START, END, benchmark=BENCHMARK)

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
