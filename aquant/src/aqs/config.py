"""Global configuration objects for the AQuant system.

All tunable numbers (trading costs, risk limits, regulatory thresholds) are kept
here as dataclasses rather than hard-coded throughout the codebase. This makes
them easy to tweak per exchange / board / date, which is a hard requirement of
the program-trading rules ("规则参数化", do not hard-code regulation).
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass
class CostConfig:
    """A-share trading cost model.

    Defaults reflect common 2025 retail A-share costs. Stamp duty is charged on
    sells only; commission has a per-order minimum; transfer fee applies to
    Shanghai/Shenzhen stocks.
    """

    commission_rate: float = 0.00025       # 万2.5 佣金
    min_commission: float = 5.0            # 单笔最低佣金 5 元
    stamp_duty_rate: float = 0.0005        # 印花税 0.05%，仅卖出
    transfer_fee_rate: float = 0.00001     # 过户费 0.001%（双向）
    slippage_bps: float = 2.0              # 滑点（基点，双向）

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class TradingRuleConfig:
    """Market micro-structure rules used by the matching engine."""

    lot_size: int = 100                    # 一手 = 100 股
    settlement: str = "T+1"                # A 股 T+1
    # Price-limit ratios by board. Used when reference data is unavailable.
    price_limit_main: float = 0.10         # 主板 ±10%
    price_limit_star: float = 0.20         # 科创板/创业板 ±20%
    price_limit_bse: float = 0.30          # 北交所 ±30%
    price_limit_st: float = 0.05           # ST/*ST ±5%
    new_stock_no_limit_days: int = 0       # 新股上市首日规则（占位）


@dataclass
class RiskConfig:
    """Pre-trade / real-time risk limits."""

    max_position_per_stock: float = 0.25   # 单票最大仓位 (占总资产)
    max_position_per_industry: float = 0.40
    max_order_value: float = 1_000_000.0   # 单笔最大下单金额
    max_daily_turnover: float = 5.0        # 单日最大换手率 (倍)
    max_total_position: float = 0.95       # 最大总仓位
    max_holdings: int = 50                 # 最大持仓只数
    max_drawdown_stop: float = 0.20        # 触发停机的最大回撤
    max_daily_loss: float = 0.05           # 单日最大亏损
    forbid_st: bool = True                 # 禁止买入 ST / 风险警示
    min_adv_ratio: float = 0.05            # 单笔不超过近期日均成交额的比例


@dataclass
class ComplianceConfig:
    """Program-trading / HFT regulatory thresholds.

    Defaults follow the publicly disclosed HFT identification standards of the
    exchanges (e.g. SSE): per-account peak >= 300 orders+cancels per second, or
    >= 20000 orders+cancels in a single day. These are configurable because the
    rules differ by exchange and may be updated by regulators.
    """

    hft_orders_per_second: int = 300       # 每秒申报+撤单 阈值
    hft_orders_per_day: int = 20_000       # 全日申报+撤单 阈值
    high_cancel_ratio: float = 0.50        # 撤单比例预警阈值
    require_filing_before_live: bool = True # 实盘前必须完成程序化交易报备
    warn_at_pct_of_threshold: float = 0.8  # 达到阈值 80% 时预警


@dataclass
class SystemConfig:
    """Top-level config aggregating all sub-configs."""

    cost: CostConfig = field(default_factory=CostConfig)
    rules: TradingRuleConfig = field(default_factory=TradingRuleConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    compliance: ComplianceConfig = field(default_factory=ComplianceConfig)

    initial_cash: float = 1_000_000.0
    benchmark: str = "000300.SH"           # 沪深300 作为默认基准
    annualization: int = 252               # 年化交易日

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cost": self.cost.to_dict(),
            "rules": asdict(self.rules),
            "risk": asdict(self.risk),
            "compliance": asdict(self.compliance),
            "initial_cash": self.initial_cash,
            "benchmark": self.benchmark,
            "annualization": self.annualization,
        }


DEFAULT_CONFIG = SystemConfig()
