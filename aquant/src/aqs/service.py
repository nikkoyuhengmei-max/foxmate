"""High-level service layer.

Wires the modules together into a few coarse operations (run a backtest, run a
paper-trading session, forecast a symbol, data-quality report) that are reused by
both the CLI and the web API so behaviour stays consistent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from aqs.config import SystemConfig, DEFAULT_CONFIG
from aqs.backtest.engine import BacktestEngine
from aqs.compliance.monitor import ComplianceMonitor
from aqs.compliance.filing import ProgramTradingFiling
from aqs.data.market_data import MarketDataManager
from aqs.performance.metrics import analyze
from aqs.performance.robustness import monte_carlo_drawdown
from aqs.risk.manager import RiskManager
from aqs.strategy.templates import TEMPLATES
from aqs.trading.trader import PaperTrader


_DATA_CACHE: Dict[str, MarketDataManager] = {}


def get_data_manager(config: SystemConfig = DEFAULT_CONFIG, refresh: bool = False) -> MarketDataManager:
    if refresh or "default" not in _DATA_CACHE:
        _DATA_CACHE["default"] = MarketDataManager.from_sample(config)
    return _DATA_CACHE["default"]


def list_strategies() -> Dict[str, str]:
    return {key: cls.name for key, cls in TEMPLATES.items()}


def _make_strategy(name: str, params: Optional[dict] = None):
    if name not in TEMPLATES:
        raise KeyError(f"unknown strategy '{name}'. Available: {list(TEMPLATES)}")
    params = params or {}
    return TEMPLATES[name](**params)


# Strategies that intentionally concentrate into one/few names run under a
# concentration-aware risk profile (the single-name cap would otherwise block
# every order). Diversification limits still apply to the diversified templates.
_CONCENTRATED = {"grid", "etf_rotation"}


def _risk_for(strategy: str, config: SystemConfig) -> RiskManager:
    cfg = config.risk
    if strategy in _CONCENTRATED:
        import copy

        cfg = copy.copy(config.risk)
        cfg.max_position_per_stock = 1.0
        cfg.max_position_per_industry = 1.0
        cfg.max_total_position = 0.98
    return RiskManager(cfg)


def run_backtest(
    strategy: str = "multi_factor",
    params: Optional[dict] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    fill_mode: str = "next_open",
    config: SystemConfig = DEFAULT_CONFIG,
    monte_carlo: bool = True,
) -> Dict[str, Any]:
    mdm = get_data_manager(config)
    risk = _risk_for(strategy, config)
    comp = ComplianceMonitor(config.compliance)
    strat = _make_strategy(strategy, params)
    engine = BacktestEngine(mdm, strat, config, risk_manager=risk, compliance=comp, fill_mode=fill_mode)
    result = engine.run(start, end)
    report = analyze(result.equity_curve, result.benchmark, periods=config.annualization)

    out: Dict[str, Any] = {
        "strategy": strategy,
        "strategy_name": strat.name,
        "params": params or {},
        "data_version": result.data_version,
        "metrics": {k: round(float(v), 6) for k, v in report.metrics.items()},
        "risk_review": risk.review(result.trades, result.equity_curve),
        "compliance": comp.summary(),
        "n_trades": len(result.trades),
        "n_orders": len(result.orders),
        "equity_curve": _series_to_records(result.equity_curve),
        "benchmark_curve": _series_to_records(
            (result.benchmark / result.benchmark.iloc[0] * result.equity_curve.iloc[0])
            if len(result.benchmark) else result.benchmark
        ),
        "drawdown": _series_to_records(report.drawdown),
        "monthly_returns": _monthly_to_records(report.monthly_returns),
        "trades": [_trade_dict(t) for t in result.trades[-200:]],
        "risk_events": risk.events_frame().to_dict(orient="records") if risk.events else [],
        "compliance_alerts": comp.alerts_frame().to_dict(orient="records") if comp.alerts else [],
        "logs": result.logs[-200:],
        "summary_text": report.summary_text(),
    }
    if monte_carlo:
        out["monte_carlo"] = {k: round(v, 6) for k, v in monte_carlo_drawdown(result.returns).items()}
    return out


def run_paper(
    strategy: str = "double_ma",
    params: Optional[dict] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    config: SystemConfig = DEFAULT_CONFIG,
) -> Dict[str, Any]:
    mdm = get_data_manager(config)
    risk = _risk_for(strategy, config)
    comp = ComplianceMonitor(config.compliance)
    trader = PaperTrader(mdm, _make_strategy(strategy, params), config, risk_manager=risk, compliance=comp, live=False)
    equity = trader.run(start, end)
    report = analyze(equity, mdm.benchmark()["close"], periods=config.annualization)
    return {
        "strategy": strategy,
        "metrics": {k: round(float(v), 6) for k, v in report.metrics.items()},
        "compliance": comp.summary(),
        "n_trades": len(trader.broker.query_trades()),
        "equity_curve": _series_to_records(equity),
        "logs": trader.logs[-100:],
    }


def forecast_symbol(symbol: str, horizon: int = 5, config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    from aqs.ml.forecast import analyze_and_forecast

    mdm = get_data_manager(config)
    return analyze_and_forecast(mdm, symbol, horizon=horizon)


def screen_stocks(
    top_n: int = 8,
    universe: Optional[List[str]] = None,
    asof: Optional[str] = None,
    auction: Optional[dict] = None,
    config: SystemConfig = DEFAULT_CONFIG,
) -> dict:
    """快速筛选 Top N 候选股（多周期历史 + 量化指标 + 可选集合竞价）。"""
    from aqs.research.screener import Screener

    mdm = get_data_manager(config)
    df = Screener().screen(mdm, universe=universe, asof=asof, top_n=top_n, auction=auction)
    return {
        "asof": asof or (str(mdm.benchmark().index[-1].date()) if len(mdm.benchmark()) else None),
        "top_n": top_n,
        "picks": df.reset_index().to_dict(orient="records") if not df.empty else [],
        "disclaimer": "选股结果仅为量化参考，不构成投资建议；请结合风控与人工复核。",
    }


def data_quality(config: SystemConfig = DEFAULT_CONFIG) -> List[dict]:
    mdm = get_data_manager(config)
    return mdm.run_quality_checks().to_dict(orient="records")


def list_symbols(config: SystemConfig = DEFAULT_CONFIG) -> List[dict]:
    mdm = get_data_manager(config)
    rows = []
    for sym in mdm.symbols:
        inst = mdm.instrument(sym)
        rows.append(
            {
                "symbol": sym,
                "name": inst.name if inst else "",
                "board": inst.board.value if inst else "",
                "industry": inst.industry if inst else "",
                "is_st": inst.is_st if inst else False,
                "active": inst.is_active if inst else True,
            }
        )
    return rows


# --------------------------------------------------------------- helpers
def _series_to_records(s: pd.Series) -> List[dict]:
    if s is None or len(s) == 0:
        return []
    return [{"date": str(idx.date()), "value": round(float(v), 4)} for idx, v in s.items() if pd.notna(v)]


def _monthly_to_records(df: pd.DataFrame) -> List[dict]:
    if df is None or df.empty:
        return []
    out = []
    for year, row in df.iterrows():
        for col, val in row.items():
            if pd.notna(val):
                out.append({"year": int(year), "month": col, "ret": round(float(val), 4)})
    return out


def _trade_dict(t) -> dict:
    return {
        "timestamp": str(t.timestamp.date()),
        "symbol": t.symbol,
        "side": t.side.value,
        "quantity": t.quantity,
        "price": t.price,
        "cost": round(t.total_cost, 2),
        "tag": t.tag,
    }
