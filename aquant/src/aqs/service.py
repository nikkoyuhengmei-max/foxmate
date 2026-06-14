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


# 实际生效的数据来源（区分配置与回退结果）。
_ACTUAL: Dict[str, Any] = {"source": None, "is_real": False}

# 指数成分股缓存
_UNIVERSE_CACHE: Dict[str, List[str]] = {}


def resolve_universe(universe) -> List[str]:
    """把 universe（列表 / 'hs300' / 'zz500' / 'sz50' / 'custom'）解析为代码列表。"""
    if isinstance(universe, (list, tuple)):
        return list(universe)
    if not universe or universe in ("custom", "default"):
        return list(DATA_CFG["symbols"])
    name = str(universe).lower()
    if name in ("hs300", "zz500", "sz50"):
        if name in _UNIVERSE_CACHE:
            return _UNIVERSE_CACHE[name]
        try:
            from aqs.data.sources.baostock_source import fetch_index_constituents

            syms = fetch_index_constituents(name)
            if syms:
                _UNIVERSE_CACHE[name] = syms
                return syms
        except Exception as exc:  # noqa: BLE001
            print(f"[universe] 获取 {name} 成分失败，使用默认股票池：{exc}")
    return list(DATA_CFG["symbols"])


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
            _ACTUAL["source"], _ACTUAL["is_real"] = src, True
        except Exception as exc:  # noqa: BLE001
            print(f"[data] 数据源 '{src}' 取数失败，回退到示例数据：{exc}")
            mgr = None

    if mgr is None:
        mgr = MarketDataManager.from_sample(config)
        _ACTUAL["source"], _ACTUAL["is_real"] = "sample", False

    _DATA_CACHE["default"] = mgr
    return mgr


def active_source() -> str:
    return _ACTUAL["source"] or DATA_CFG["source"]


def data_status() -> Dict[str, Any]:
    """仪表盘顶部状态：数据源 / 数据日期 / 系统时间 / 是否真实数据。"""
    mgr = get_data_manager()
    sessions = mgr.trading_dates()
    data_date = str(sessions[-1].date()) if len(sessions) else None
    return {
        "configured_source": DATA_CFG["source"],
        "actual_source": _ACTUAL["source"] or DATA_CFG["source"],
        "is_real_data": bool(_ACTUAL["is_real"]),
        "data_date": data_date,
        "system_time": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_symbols": len(mgr.symbols),
        "universe_start": DATA_CFG["start"],
        "universe_end": DATA_CFG["end"],
    }


def list_strategies() -> Dict[str, str]:
    return {key: cls.name for key, cls in TEMPLATES.items()}


def _make_strategy(name: str, params: Optional[dict] = None):
    import inspect

    if name not in TEMPLATES:
        raise KeyError(f"unknown strategy '{name}'. Available: {list(TEMPLATES)}")
    cls = TEMPLATES[name]
    params = dict(params or {})
    # 只保留该策略构造函数接受的参数（如 rebalance/top_n 等），其余忽略
    sig = inspect.signature(cls.__init__)
    accepted = {k: v for k, v in params.items() if k in sig.parameters}
    return cls(**accepted)


# Strategies that intentionally concentrate into one/few names (or hold the whole
# universe) run under a concentration-aware risk profile, otherwise the single-name
# cap would block every order. Diversification limits still apply to the rest.
_CONCENTRATED = {"grid", "etf_rotation", "buy_and_hold"}


def _risk_for(strategy: str, config: SystemConfig, max_position: Optional[float] = None) -> RiskManager:
    import copy

    cfg = copy.copy(config.risk)
    if strategy in _CONCENTRATED:
        cfg.max_position_per_stock = 1.0
        cfg.max_position_per_industry = 1.0
        cfg.max_total_position = 0.98
    if max_position is not None:
        cfg.max_position_per_stock = float(max_position)
    return RiskManager(cfg)


OUTPUTS_DIR = os.getenv("AQUANT_OUTPUTS_DIR", "outputs")


def _ensure_outputs() -> str:
    os.makedirs(OUTPUTS_DIR, exist_ok=True)
    return OUTPUTS_DIR


def run_backtest(
    strategy: str = "multi_factor",
    params: Optional[dict] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    fill_mode: str = "next_open",
    rebalance: Optional[str] = None,
    max_position: Optional[float] = None,
    config: SystemConfig = DEFAULT_CONFIG,
    monte_carlo: bool = True,
    save: bool = False,
) -> Dict[str, Any]:
    mdm = get_data_manager(config)
    risk = _risk_for(strategy, config, max_position=max_position)
    comp = ComplianceMonitor(config.compliance)
    sparams = dict(params or {})
    if rebalance:
        sparams["rebalance"] = rebalance
    strat = _make_strategy(strategy, sparams)
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

    if save:
        out["saved"] = _save_backtest(strategy, out, result)
    return out


# 报告里展示的核心指标（中文标签）
_REPORT_FIELDS = [
    ("total_return", "累计收益", True),
    ("annual_return", "年化收益", True),
    ("benchmark_return", "基准收益", True),
    ("excess_return", "超额收益", True),
    ("max_drawdown", "最大回撤", True),
    ("sharpe", "夏普", False),
    ("win_rate", "胜率", True),
]


def _save_backtest(strategy: str, out: Dict[str, Any], result) -> Dict[str, str]:
    """导出回测结果到 outputs/backtest_策略_日期.{csv,html}。"""
    d = _ensure_outputs()
    date = _dt.date.today().isoformat()
    base = f"backtest_{strategy}_{date}"
    m = out["metrics"]

    # CSV：核心指标 + 成交次数/换手率
    rows = []
    for key, label, _ in _REPORT_FIELDS:
        rows.append({"指标": label, "数值": m.get(key)})
    rows.append({"指标": "交易次数", "数值": out["n_trades"]})
    rows.append({"指标": "换手率", "数值": out["risk_review"].get("turnover")})
    csv_path = os.path.join(d, f"{base}.csv")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    # HTML 报告
    html_path = os.path.join(d, f"{base}.html")
    with open(html_path, "w", encoding="utf-8") as fh:
        fh.write(_backtest_html(strategy, out))

    # 同时写一份"最新回测"指针，供 dashboard 读取
    latest = os.path.join(d, "latest_backtest.json")
    import json

    with open(latest, "w", encoding="utf-8") as fh:
        json.dump({
            "strategy": strategy, "date": date, "metrics": m,
            "n_trades": out["n_trades"], "turnover": out["risk_review"].get("turnover"),
            "equity_curve": out["equity_curve"], "benchmark_curve": out["benchmark_curve"],
            "drawdown": out["drawdown"], "monthly_returns": out["monthly_returns"],
        }, fh, ensure_ascii=False)
    return {"csv": csv_path, "html": html_path, "latest": latest}


def _backtest_html(strategy: str, out: Dict[str, Any]) -> str:
    m = out["metrics"]
    def fmt(key, pct):
        v = m.get(key, 0.0)
        return f"{v*100:.2f}%" if pct else f"{v:.2f}"
    rows = "".join(
        f"<tr><td>{label}</td><td>{fmt(key, pct)}</td></tr>" for key, label, pct in _REPORT_FIELDS
    )
    rows += f"<tr><td>交易次数</td><td>{out['n_trades']}</td></tr>"
    rows += f"<tr><td>换手率</td><td>{out['risk_review'].get('turnover', 0):.2f}</td></tr>"
    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>回测报告 {strategy}</title>
<style>body{{font-family:sans-serif;max-width:680px;margin:40px auto;color:#222}}
table{{border-collapse:collapse;width:100%}}td{{padding:8px 12px;border-bottom:1px solid #eee}}
td:last-child{{text-align:right;font-weight:600}}h1{{font-size:20px}}.warn{{color:#999;font-size:12px}}</style>
</head><body>
<h1>回测报告 · {out.get('strategy_name', strategy)} ({strategy})</h1>
<p class="warn">数据版本 {out.get('data_version','-')} · 生成于 {_dt.datetime.now():%Y-%m-%d %H:%M}</p>
<table>{rows}</table>
<p class="warn">结果仅为量化回测参考，不构成投资建议。</p>
</body></html>"""


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
    bench = mdm.benchmark()
    report = analyze(equity, bench["close"] if len(bench) else None, periods=config.annualization)
    trades = trader.broker.query_trades()
    saved = _write_trades(trades, mode="paper")
    return {
        "strategy": strategy,
        "metrics": {k: round(float(v), 6) for k, v in report.metrics.items()},
        "compliance": comp.summary(),
        "n_trades": len(trades),
        "equity_curve": _series_to_records(equity),
        "logs": trader.logs[-100:],
        "trades_file": saved,
    }


def _manager_for_symbol(symbol: str, config: SystemConfig) -> Optional[MarketDataManager]:
    """返回包含该标的的数据管理器。

    若该标的不在已加载股票池中，则按当前数据源临时拉取它（缓存复用）。
    """
    mdm = get_data_manager(config)
    if symbol in mdm.symbols:
        return mdm
    src = DATA_CFG["source"]
    if src not in ("baostock", "akshare"):
        return None  # 示例数据无法获取任意股票
    try:
        common = dict(
            symbols=[symbol], start=DATA_CFG["start"], end=DATA_CFG["end"],
            benchmark=DATA_CFG["benchmark"], cache_dir=DATA_CFG["cache_dir"],
            refresh=False, config=config,
        )
        m = MarketDataManager.from_baostock(**common) if src == "baostock" else MarketDataManager.from_akshare(**common)
        return m if symbol in m.symbols else None
    except Exception as exc:  # noqa: BLE001
        print(f"[forecast] 拉取 {symbol} 数据失败：{exc}")
        return None


def search_stocks(q: str, limit: int = 20) -> List[dict]:
    from aqs.data import directory

    return directory.search(q, limit=limit)


def watchlist() -> List[dict]:
    from aqs.data import directory

    return directory.watchlist()


def add_to_watchlist(query: str) -> dict:
    from aqs.data import directory

    return directory.add_watchlist(query)


def remove_from_watchlist(symbol: str) -> dict:
    from aqs.data import directory

    return directory.remove_watchlist(symbol)


def forecast_symbol(symbol: str, horizon: int = 5, config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    from aqs.ml.forecast import analyze_and_forecast
    from aqs.data import directory

    # 支持输入代码或名称（如 "贵州茅台" / "600519" / "600519.SH"）
    resolved = directory.resolve(symbol)
    if not resolved:
        return {"symbol": symbol, "error": "未找到该股票代码或名称"}

    mdm = _manager_for_symbol(resolved, config)
    if mdm is None:
        return {"symbol": resolved, "error": "无法获取该股票数据（示例数据模式仅支持内置标的，请切换到 Baostock/AkShare）"}

    res = analyze_and_forecast(mdm, resolved, horizon=horizon)
    # 补充名称
    inst = mdm.instrument(resolved)
    res["name"] = (inst.name if inst and inst.name else directory.name_of(resolved))
    symbol = resolved

    # 附加数据区间信息 + 数据是否陈旧的警告
    try:
        df = mdm.get_price(symbol).dropna(subset=["close"])
        if len(df):
            latest = df.index[-1]
            n = len(df)
            split = int(n * 0.7)
            res["data"] = {
                "training_start": str(df.index[0].date()),
                "training_end": str(df.index[max(split - 1, 0)].date()),
                "test_start": str(df.index[min(split, n - 1)].date()),
                "latest_data_date": str(latest.date()),
            }
            sessions = mdm.trading_dates()
            market_latest = sessions[-1] if len(sessions) else latest
            stale_days = int((market_latest - latest).days)
            res["data"]["stale_days"] = stale_days
            res["data"]["is_stale"] = stale_days > 7
    except Exception:
        pass
    return res


def recent_trades(limit: int = 200) -> Dict[str, Any]:
    """读取真实/模拟成交记录（outputs/trades.csv 或 records/trades.csv）。

    没有记录时返回 has_records=False，前端显示"暂无真实成交记录"。
    """
    for path in (os.path.join(OUTPUTS_DIR, "trades.csv"), os.path.join("records", "trades.csv")):
        if os.path.exists(path):
            try:
                df = pd.read_csv(path)
                trades = df.tail(limit).to_dict(orient="records")
                return {"has_records": True, "source_file": path, "trades": trades}
            except Exception:
                continue
    return {"has_records": False, "trades": [], "message": "暂无真实成交记录"}


def _write_trades(trades, mode: str) -> Optional[str]:
    """把 paper/live 成交追加写入 outputs/trades.csv。"""
    if not trades:
        return None
    d = _ensure_outputs()
    path = os.path.join(d, "trades.csv")
    rows = [
        {
            "timestamp": str(t.timestamp), "symbol": t.symbol, "side": t.side.value,
            "quantity": t.quantity, "price": t.price, "cost": round(t.total_cost, 2),
            "tag": t.tag, "mode": mode,
        }
        for t in trades
    ]
    new = pd.DataFrame(rows)
    if os.path.exists(path):
        try:
            old = pd.read_csv(path)
            new = pd.concat([old, new], ignore_index=True)
        except Exception:
            pass
    new.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def refresh_real_data(
    strategy: str = "multi_factor",
    forecast_sym: str = "600519.SH",
    top_n: int = 8,
) -> Dict[str, Any]:
    """重新拉取真实数据并刷新 screen / backtest / forecast 输出（供仪表盘"刷新"按钮）。"""
    get_data_manager(refresh=True)  # 重新加载数据
    screen = screen_stocks(top_n=top_n, save=True)
    backtest = run_backtest(strategy=strategy, save=True, monte_carlo=False)
    forecast = forecast_symbol(forecast_sym)
    return {
        "status": data_status(),
        "screen": screen,
        "backtest_metrics": backtest["metrics"],
        "forecast": forecast,
        "refreshed_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def screen_stocks(
    top_n: int = 8,
    universe=None,
    asof: Optional[str] = None,
    min_amount: float = 0.0,
    exclude_st: bool = True,
    auction: Optional[dict] = None,
    save: bool = False,
    config: SystemConfig = DEFAULT_CONFIG,
) -> dict:
    """快速筛选 Top N 候选股（多周期历史 + 量化指标 + 可选集合竞价）。"""
    from aqs.research.screener import Screener, ScreenConfig

    mdm = get_data_manager(config)
    syms = resolve_universe(universe) if universe is not None else list(mdm.symbols)
    syms = [s for s in syms if s in mdm.symbols]

    # 最小成交额过滤（近 20 日日均成交额）
    if min_amount and min_amount > 0:
        kept = []
        for s in syms:
            try:
                amt = mdm.get_price(s, fields=["amount"])["amount"].dropna().tail(20).mean()
            except Exception:
                amt = None
            if amt is not None and amt >= min_amount:
                kept.append(s)
        syms = kept

    cfg = ScreenConfig(exclude_st=exclude_st)
    df = Screener(cfg).screen(mdm, universe=syms or None, asof=asof, top_n=top_n, auction=auction)

    sessions = mdm.trading_dates(end=asof) if asof else mdm.trading_dates()
    asof_date = asof or (str(sessions[-1].date()) if len(sessions) else None)
    picks = df.reset_index().to_dict(orient="records") if not df.empty else []
    out = {
        "asof": asof_date,
        "top_n": top_n,
        "universe": universe if isinstance(universe, str) else (f"custom({len(syms)})" if universe else "default"),
        "min_amount": min_amount,
        "exclude_st": exclude_st,
        "is_real_data": bool(_ACTUAL["is_real"]),
        "source": active_source(),
        "picks": picks,
        "disclaimer": "选股结果仅为量化参考，不构成投资建议；请结合风控与人工复核。",
    }
    if save and not df.empty:
        d = _ensure_outputs()
        path = os.path.join(d, f"screen_{asof_date or _dt.date.today().isoformat()}.csv")
        df.reset_index().to_csv(path, index=False, encoding="utf-8-sig")
        # 最新指针
        import json
        with open(os.path.join(d, "latest_screen.json"), "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False)
        out["saved"] = path
    return out


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
