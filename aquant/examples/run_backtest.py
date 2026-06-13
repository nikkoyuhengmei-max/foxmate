"""Minimal end-to-end backtest example.

Run from the project root:  python examples/run_backtest.py
"""

from aqs.data.market_data import MarketDataManager
from aqs.strategy.templates import MultiFactor
from aqs.backtest.engine import BacktestEngine
from aqs.risk.manager import RiskManager
from aqs.compliance.monitor import ComplianceMonitor
from aqs.performance.metrics import analyze
from aqs.performance.robustness import monte_carlo_drawdown


def main() -> None:
    data = MarketDataManager.from_sample()
    print("数据质量检查:")
    print(data.run_quality_checks().to_string(index=False))

    risk = RiskManager()
    compliance = ComplianceMonitor()
    engine = BacktestEngine(
        data,
        MultiFactor(top_n=4, rebalance="monthly"),
        risk_manager=risk,
        compliance=compliance,
        fill_mode="next_open",
    )
    result = engine.run()

    report = analyze(result.equity_curve, result.benchmark)
    print("\n" + report.summary_text())

    print("\n风控复盘:", risk.review(result.trades, result.equity_curve))
    print("合规摘要:", compliance.summary())
    print("Monte-Carlo:", {k: round(v, 4) for k, v in monte_carlo_drawdown(result.returns).items()})
    print("审计链校验:", compliance.audit.verify())


if __name__ == "__main__":
    main()
