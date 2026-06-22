"""A-share trading cost model: commission, stamp duty, transfer fee, slippage."""

from __future__ import annotations

from dataclasses import dataclass

from aqs.config import CostConfig
from aqs.core.objects import OrderSide


@dataclass
class CostBreakdown:
    commission: float
    stamp_duty: float
    transfer_fee: float

    @property
    def total(self) -> float:
        return self.commission + self.stamp_duty + self.transfer_fee


class CostModel:
    def __init__(self, cfg: CostConfig) -> None:
        self.cfg = cfg

    def fees(self, side: OrderSide, price: float, quantity: int) -> CostBreakdown:
        gross = price * quantity
        commission = max(gross * self.cfg.commission_rate, self.cfg.min_commission)
        transfer = gross * self.cfg.transfer_fee_rate
        stamp = gross * self.cfg.stamp_duty_rate if side == OrderSide.SELL else 0.0
        return CostBreakdown(
            commission=round(commission, 2),
            stamp_duty=round(stamp, 2),
            transfer_fee=round(transfer, 2),
        )

    def apply_slippage(self, side: OrderSide, price: float) -> float:
        """Worsen the fill by the configured slippage (bps)."""
        slip = self.cfg.slippage_bps / 10_000.0
        if side == OrderSide.BUY:
            return price * (1 + slip)
        return price * (1 - slip)
