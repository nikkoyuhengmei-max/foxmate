"""High-level service layer.

Wires the modules together into a few coarse operations (run a backtest, run a
paper-trading session, forecast a symbol, data-quality report) that are reused by
both the CLI and the web API so behaviour stays consistent.
"""

from __future__ import annotations

import datetime as _dt
import os
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

# 默认蓝筹/各行业代表股池（可被 configure_data / 环境变量覆盖）
_DEFAULT_UNIVERSE = [
    "600519.SH", "600036.SH", "601318.SH", "000333.SZ", "300750.SZ", "000001.SZ",
    "600276.SH", "002594.SZ", "601899.SH", "600900.SH", "000651.SZ", "002415.SZ",
    "600030.SH", "300059.SZ", "688981.SH", "601012.SH",
]


def _default_dates() -> tuple[str, str]:
    end = _dt.date.today()
    start = end - _dt.timedelta(days=365 * 2)
    return start.isoformat(), end.isoformat()


def _env_symbols() -> List[str]:
    raw = os.getenv("AQUANT_SYMBOLS")
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else list(_DEFAULT_UNIVERSE)


_s, _e = _default_dates()
DATA_CFG: Dict[str, Any] = {
    "source": os.getenv("AQUANT_SOURCE", "baostock"),   # baostock | akshare | sample
    "symbols": _env_symbols(),
    "start": os.getenv("AQUANT_START", _s),
    "end": os.getenv("AQUANT_END", _e),
    "benchmark": os.getenv("AQUANT_BENCHMARK", "000300.SH"),
    "cache_dir": os.getenv("AQUANT_CACHE_DIR", ".cache"),
    "refresh": False,
}


def configure_data(
    source: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    benchmark: Optional[str] = None,
    cache_dir: Optional[str] = None,
    refresh: Optional[bool] = None,
) -> None:
    """更新全局数据源配置，并清空已加载的数据缓存。"""
    if source is not None:
        DATA_CFG["source"] = source
    if symbols:
        DATA_CFG["symbols"] = symbols
    if start is not None:
        DATA_CFG["start"] = start
    if end is not None:
        DATA_CFG["end"] = end
    if benchmark is not None:
        DATA_CFG["benchmark"] = benchmark
    if cache_dir is not None:
        DATA_CFG["cache_dir"] = cache_dir
    if refresh is not None:
        DATA_CFG["refresh"] = refresh
    _DATA_CACHE.pop("default", None)


def get_data_manager(config: SystemConfig = DEFAULT_CONFIG, refresh: bool = False) -> MarketDataManager:
    if not refresh and "default" in _DATA_CACHE:
        return _DATA_CACHE["default"]

    cfg = DATA_CFG
    src = cfg["source"]
    mgr: Optional[MarketDataManager] = None

    if src in ("baostock", "akshare"):
        try:
            common = dict(
                symbols=cfg["symbols"], start=cfg["start"], end=cfg["end"],
                benchmark=cfg["benchmark"], cache_dir=cfg["cache_dir"],
                refresh=cfg["refresh"], config=config,
            )
            if src == "baostock":
                mgr = MarketDataManager.from_baostock(**common)
            else:
                mgr = MarketDataManager.from_akshare(**common)
            if not mgr.symbols:
                raise RuntimeError("数据源未返回任何标的")
        except Exception as exc:  # noqa: BLE001
            print(f"[data] 数据源 '{src}' 取数失败，回退到示例数据：{exc}")
            mgr = None

    if mgr is None:
        mgr = MarketDataManager.from_sample(config)

    _DATA_CACHE["default"] = mgr
    return mgr


def active_source() -> str:
    """返回当前实际生效的数据源（区分配置值与回退结果）。"""
    mgr = _DATA_CACHE.get("default")
    if mgr is None:
        return DATA_CFG["source"]
    return DATA_CFG["source"]


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
