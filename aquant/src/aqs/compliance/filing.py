"""Program-trading filing ("程序化交易报备") information management.

Investors must report account, capital, trading and software information and
follow "先报告、后交易" (report first, then trade). This module models that
filing and validates completeness before live trading is allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


@dataclass
class ProgramTradingFiling:
    # 账户信息
    account_id: str = ""
    account_name: str = ""
    broker: str = ""
    # 资金信息
    capital_scale: float = 0.0
    leverage_used: bool = False
    # 交易信息
    products: List[str] = field(default_factory=list)          # 拟交易品种
    max_orders_per_second: int = 0                             # 最高申报频率
    max_orders_per_day: int = 0                                # 全日最高申报笔数
    strategy_types: List[str] = field(default_factory=list)    # 策略类型
    # 软件信息
    software_name: str = "AQuant"
    software_version: str = ""
    deployment: str = "personal_pc"                           # 服务器部署方式
    access_method: str = "broker_api"                         # 接口接入方式
    # 状态
    filed: bool = False
    filing_date: Optional[str] = None

    REQUIRED = (
        "account_id",
        "account_name",
        "broker",
        "capital_scale",
        "products",
        "strategy_types",
        "software_version",
    )

    def missing_fields(self) -> List[str]:
        missing = []
        for f in self.REQUIRED:
            val = getattr(self, f)
            if val in ("", 0, None) or (isinstance(val, list) and not val):
                missing.append(f)
        return missing

    def is_complete(self) -> bool:
        return not self.missing_fields()

    def is_high_frequency(self, per_second_threshold: int, per_day_threshold: int) -> bool:
        return (
            self.max_orders_per_second >= per_second_threshold
            or self.max_orders_per_day >= per_day_threshold
        )

    def to_dict(self) -> Dict:
        return asdict(self)
