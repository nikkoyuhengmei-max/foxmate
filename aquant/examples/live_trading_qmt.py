"""券商 miniQMT 实盘（沙盒/实盘）示例 —— 默认 dry_run，不会真实下单。

前提：在装有并登录券商 QMT/miniQMT 客户端的机器上运行；已安装 xtquant；
并且**已完成程序化交易报备**（先报告、后交易）。

安全说明：
- 默认 ``dry_run=True``，只记录不下单；确认无误后才改 ``dry_run=False``。
- 实盘前系统强制校验报备信息是否完整，否则拒绝启动。
- 内置一键停止 / 只读 / 自动停机 等安全阀。

运行：python examples/live_trading_qmt.py
"""

from aqs.config import DEFAULT_CONFIG
from aqs.data.market_data import MarketDataManager
from aqs.strategy.templates import DoubleMA
from aqs.risk.manager import RiskManager
from aqs.compliance.monitor import ComplianceMonitor
from aqs.compliance.filing import ProgramTradingFiling
from aqs.trading.trader import PaperTrader


QMT_PATH = r"D:\\国金QMT交易端\\userdata_mini"   # 改成你的 miniQMT 路径
ACCOUNT_ID = "你的资金账号"
UNIVERSE = ["600519.SH", "000333.SZ", "600036.SH"]


def main() -> None:
    from aqs.trading.qmt_broker import QMTBroker

    # 1) 行情：用 QMT 本地数据（也可换成 baostock 历史 + QMT 实时）
    data = MarketDataManager.from_qmt(UNIVERSE, "2023-01-01", "2024-12-31", cache_dir=".cache")

    # 2) 合规报备（必须完整，否则实盘被拒）
    filing = ProgramTradingFiling(
        account_id=ACCOUNT_ID, account_name="本人", broker="券商名称",
        capital_scale=200000, products=["stock"], strategy_types=["trend"],
        software_version="0.1.0", filed=True, filing_date="2025-07-07",
    )
    compliance = ComplianceMonitor(filing=filing)

    # 3) 实盘券商（dry_run=True：只记录不下单；确认后改 False 才真实交易）
    broker = QMTBroker(account_id=ACCOUNT_ID, qmt_path=QMT_PATH, dry_run=True, config=DEFAULT_CONFIG)
    broker.connect()

    trader = PaperTrader(
        data, DoubleMA(fast=5, slow=20),
        risk_manager=RiskManager(), compliance=compliance, live=True, broker=broker,
    )

    # 盘中可循环调用 trader.step(当前时间) 驱动策略；这里用历史回放演示一次跑批：
    equity = trader.run()
    print("运行结束，步数:", len(equity))
    print("合规摘要:", compliance.summary())
    # 紧急情况：trader.stop_trading() 一键停止 + 全撤 + 只读


if __name__ == "__main__":
    main()
