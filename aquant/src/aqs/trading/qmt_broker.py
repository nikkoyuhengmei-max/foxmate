"""券商 miniQMT 实盘交易网关（基于 xtquant.xttrader）。

实现 :class:`BrokerGateway` 接口，可直接被 OMS / PaperTrader 驱动，从而复用本系统的
事前风控、合规报备门禁、一键停止/只读、审计日志等全部安全机制。

REQUIREMENTS / 使用前提
--------------------------------------------------------------------------
1. 在装有并登录券商 QMT/miniQMT 客户端的机器上运行；账号开通 QMT 交易权限。
2. 安装 xtquant。
3. **实盘前必须完成程序化交易报备（先报告、后交易）**——本系统会在 live 模式强制校验。

⚠️ 安全默认：``dry_run=True`` 时**只记录、不真实下单**。确认无误后显式传 ``dry_run=False``
才会真正报单。请务必先用模拟/小资金验证。
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd

from aqs.config import SystemConfig, DEFAULT_CONFIG
from aqs.core.objects import (
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    Portfolio,
    Position,
    Trade,
)
from aqs.trading.broker import BrokerAccount, BrokerGateway


class QMTBroker(BrokerGateway):
    def __init__(
        self,
        account_id: str,
        qmt_path: str,
        session_id: Optional[int] = None,
        dry_run: bool = True,
        config: SystemConfig = DEFAULT_CONFIG,
    ) -> None:
        try:
            from xtquant.xttrader import XtQuantTrader  # type: ignore
            from xtquant.xttype import StockAccount  # type: ignore
            from xtquant import xtconstant  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local install
            raise ImportError("未找到 xtquant。请在装有券商 QMT/miniQMT 客户端的机器上安装 xtquant。") from exc

        import random

        self._xtconstant = xtconstant
        self.account_id = account_id
        self.dry_run = dry_run
        self.config = config
        self._connected = False
        self._orders: Dict[str, Order] = {}

        sid = session_id if session_id is not None else random.randint(100000, 999999)
        self._trader = XtQuantTrader(qmt_path, sid)
        self._account = StockAccount(account_id)

    # --------------------------------------------------------- connection
    def connect(self) -> bool:
        self._trader.start()
        rc = self._trader.connect()
        if rc != 0:
            raise RuntimeError(f"QMT 连接失败 code={rc}（确认客户端已登录、路径正确）")
        sc = self._trader.subscribe(self._account)
        if sc != 0:
            raise RuntimeError(f"QMT 订阅账户失败 code={sc}")
        self._connected = True
        return True

    def disconnect(self) -> None:
        try:
            self._trader.stop()
        finally:
            self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------- orders
    def submit(self, order: Order) -> Order:
        if not self._connected:
            order.status = OrderStatus.REJECTED
            order.reason = "QMT 未连接"
            return order
        self._orders[order.order_id] = order

        if self.dry_run:
            order.status = OrderStatus.REJECTED
            order.reason = "dry_run 模式：仅记录，未真实下单"
            return order

        xc = self._xtconstant
        side = xc.STOCK_BUY if order.side == OrderSide.BUY else xc.STOCK_SELL
        if order.order_type == OrderType.LIMIT and order.limit_price:
            price_type, price = xc.FIX_PRICE, float(order.limit_price)
        else:
            # 最新价/对手价；不同券商常量可能不同，必要时调整
            price_type, price = xc.LATEST_PRICE, 0.0
        seq = self._trader.order_stock(
            self._account, order.symbol, side, int(order.quantity), price_type, price,
            "AQuant", order.tag or order.order_id,
        )
        if seq is None or seq < 0:
            order.status = OrderStatus.REJECTED
            order.reason = f"QMT 报单失败 seq={seq}"
        else:
            order.status = OrderStatus.PENDING  # 实际成交以回报/查询为准
            order.reason = f"qmt_seq={seq}"
        return order

    def cancel(self, order_id: str) -> bool:
        if self.dry_run or not self._connected:
            return False
        try:
            rc = self._trader.cancel_order_stock(self._account, order_id)
            return rc == 0
        except Exception:
            return False

    # ------------------------------------------------------------ queries
    def query_account(self) -> BrokerAccount:
        asset = self._trader.query_stock_asset(self._account)
        cash = float(getattr(asset, "cash", 0.0)) if asset else 0.0
        total = float(getattr(asset, "total_asset", 0.0)) if asset else 0.0
        mv = float(getattr(asset, "market_value", 0.0)) if asset else 0.0
        return BrokerAccount(cash=cash, total_value=total, positions_value=mv,
                             positions=self.query_positions())

    def query_positions(self) -> Dict[str, Position]:
        out: Dict[str, Position] = {}
        try:
            positions = self._trader.query_stock_positions(self._account) or []
        except Exception:
            return out
        for p in positions:
            vol = int(getattr(p, "volume", 0))
            if vol <= 0:
                continue
            sym = getattr(p, "stock_code", "")
            out[sym] = Position(
                symbol=sym,
                quantity=vol,
                available=int(getattr(p, "can_use_volume", 0)),
                avg_cost=float(getattr(p, "avg_price", getattr(p, "open_price", 0.0)) or 0.0),
                last_price=float(getattr(p, "market_value", 0.0) or 0.0) / vol if vol else 0.0,
            )
        return out

    def get_portfolio(self) -> Portfolio:
        acct = self.query_account()
        pf = Portfolio(acct.cash)
        pf.cash = acct.cash
        pf.positions = self.query_positions()
        return pf

    def query_orders(self) -> List[Order]:
        return list(self._orders.values())

    def query_trades(self) -> List[Trade]:
        trades: List[Trade] = []
        try:
            raw = self._trader.query_stock_trades(self._account) or []
        except Exception:
            return trades
        for t in raw:
            sym = getattr(t, "stock_code", "")
            qty = int(getattr(t, "traded_volume", 0))
            price = float(getattr(t, "traded_price", 0.0))
            side = OrderSide.BUY if getattr(t, "order_type", 0) == self._xtconstant.STOCK_BUY else OrderSide.SELL
            trades.append(Trade(
                order_id=str(getattr(t, "order_id", "")), symbol=sym, side=side, quantity=qty,
                price=price, commission=0.0, stamp_duty=0.0, transfer_fee=0.0,
                timestamp=pd.Timestamp.now(), tag=str(getattr(t, "order_remark", "")),
            ))
        return trades
