"""Paper-trading (sandbox) example with live-mode compliance gating.

Run from the project root:  python examples/paper_trading.py
"""

from aqs.data.market_data import MarketDataManager
from aqs.strategy.templates import DoubleMA
from aqs.risk.manager import RiskManager
from aqs.compliance.monitor import ComplianceMonitor
from aqs.compliance.filing import ProgramTradingFiling
from aqs.trading.trader import PaperTrader
from aqs.performance.metrics import analyze


def main() -> None:
    data = MarketDataManager.from_sample()

    # ---- 1) paper trading (no filing required) ----------------------------
    trader = PaperTrader(
        data,
        DoubleMA(fast=5, slow=20),
        risk_manager=RiskManager(),
        compliance=ComplianceMonitor(),
        live=False,
    )
    equity = trader.run()
    rep = analyze(equity, data.benchmark()["close"])
    print("模拟交易结果:")
    print(rep.summary_text())
    print("成交笔数:", len(trader.broker.query_trades()))

    # ---- 2) live mode is blocked until program-trading filing is complete --
    print("\n实盘启动前的合规校验 (先报告、后交易):")
    comp = ComplianceMonitor(filing=ProgramTradingFiling())  # empty filing
    live = PaperTrader(data, DoubleMA(), compliance=comp, live=True)
    try:
        live.run()
    except PermissionError as exc:
        print("  被拒(预期):", exc)

    # complete the filing, then live (sandbox) can start
    filing = ProgramTradingFiling(
        account_id="A123456", account_name="张三", broker="示例证券",
        capital_scale=1_000_000, products=["stock", "etf"],
        strategy_types=["trend"], software_version="0.1.0", filed=True,
        filing_date="2025-07-07",
    )
    comp2 = ComplianceMonitor(filing=filing)
    live_ok = PaperTrader(data, DoubleMA(), risk_manager=RiskManager(), compliance=comp2, live=True)
    eq2 = live_ok.run()
    print("  报备完成后实盘(沙盒)启动成功, 步数:", len(eq2))


if __name__ == "__main__":
    main()
