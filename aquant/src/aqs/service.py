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

# 默认快速池：真实 A 股固定列表（来源 aqs.data.universe.DEFAULT_FAST）。
from aqs.data.universe import DEFAULT_FAST as _DEFAULT_UNIVERSE  # noqa: E402


def _default_dates() -> tuple[str, str]:
    end = _dt.date.today()
    start = end - _dt.timedelta(days=365 * 2)
    return start.isoformat(), end.isoformat()


def _env_symbols() -> List[str]:
    raw = os.getenv("AQUANT_SYMBOLS")
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else list(_DEFAULT_UNIVERSE)


class DataSourceError(Exception):
    """真实数据源不可用（登录/取数/网络失败）。默认不回退到示例数据。"""


_s, _e = _default_dates()
DATA_CFG: Dict[str, Any] = {
    "source": os.getenv("AQUANT_SOURCE", "akshare"),   # akshare(优先) | baostock(备用) | sample
    "symbols": _env_symbols(),
    "start": os.getenv("AQUANT_START", _s),
    "end": os.getenv("AQUANT_END", _e),
    "benchmark": os.getenv("AQUANT_BENCHMARK", "000300.SH"),
    "cache_dir": os.getenv("AQUANT_CACHE_DIR", os.path.join("data", "cache")),
    "refresh": False,
    # 演示模式：仅当显式开启才允许使用 mock/示例数据
    "demo_mode": os.getenv("AQUANT_DEMO", "").lower() in ("1", "true", "yes"),
    # 舆情数据源：auto(CSV→真实→演示mock) | csv | mock | none
    "sentiment_source": os.getenv("AQUANT_SENTIMENT_SOURCE", "auto"),
}


def configure_data(
    source: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    benchmark: Optional[str] = None,
    cache_dir: Optional[str] = None,
    refresh: Optional[bool] = None,
    demo_mode: Optional[bool] = None,
) -> None:
    """更新全局数据源配置，并清空已加载的数据缓存。"""
    if demo_mode is not None:
        DATA_CFG["demo_mode"] = bool(demo_mode)
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
_ACTUAL: Dict[str, Any] = {"source": None, "is_real": False, "using_mock": False, "error": None,
                           "universe": None}

# 指数成分股缓存
_UNIVERSE_CACHE: Dict[str, List[str]] = {}


_INDEX_MIN = {"hs300": 250, "zz500": 450, "hs800": 700, "all": 1000, "sz50": 40, "default_fast": 50}
# 最近一次 universe 加载的元信息（供状态栏展示）
_LAST_UNIVERSE_META: Dict[str, Any] = {}
_LAST_UNIVERSE_NAMES: Dict[str, str] = {}


_GLOBAL_NAME_MAP: Dict[str, str] = {}


def _global_name_map() -> Dict[str, str]:
    """全市场代码→名称（缓存）：用于补全名称。优先本地 all_a 缓存，其次 AkShare。"""
    global _GLOBAL_NAME_MAP
    if _GLOBAL_NAME_MAP:
        return _GLOBAL_NAME_MAP
    out: Dict[str, str] = {}
    # 1) 已有的 universe 缓存（all_a / hs800 / hs300 / zz500）
    try:
        import csv as _csv
        from aqs.data import universe as U
        for nm in ("all", "hs800", "hs300", "zz500"):
            p = U.cache_path(nm)
            if os.path.exists(p):
                with open(p, encoding="utf-8") as fh:
                    for r in _csv.DictReader(fh):
                        if r.get("symbol") and r.get("name"):
                            out.setdefault(r["symbol"], r["name"])
    except Exception:
        pass
    _GLOBAL_NAME_MAP = out
    return out


def _fill_names(picks: List[dict], universe_names: Optional[Dict[str, str]] = None) -> None:
    """补全选股结果中的股票名称：universe 缓存 → 全市场缓存 → 否则“名称缺失”。"""
    universe_names = universe_names or {}
    gmap = None
    missing = []
    for p in picks:
        if p.get("name"):
            continue
        sym = p.get("symbol")
        nm = universe_names.get(sym)
        if not nm:
            if gmap is None:
                gmap = _global_name_map()
            nm = gmap.get(sym)
        if not nm:
            missing.append(sym)
            nm = "名称缺失"
        p["name"] = nm
    if missing:
        print(f"[names] 名称缺失 {len(missing)} 只: {missing[:10]}")


def load_universe(name, source: Optional[str] = None, use_cache: bool = True,
                  refresh: bool = False) -> Dict[str, Any]:
    """加载股票池，返回 {name, source, size, symbols, cache_file, updated_at, error, errors}。

    指数/全A：缓存 → AkShare → Baostock；都失败则 error（不回退到小样本池）。
    """
    if isinstance(name, (list, tuple)):
        return {"name": "custom", "source": "custom", "symbols": list(name), "size": len(name),
                "cache_file": None, "updated_at": None, "error": None, "errors": []}
    key = str(name or "").lower()

    if key in ("", "default", "custom"):
        syms = list(DATA_CFG["symbols"])
        return {"name": "default", "source": "default", "symbols": syms, "size": len(syms),
                "cache_file": None, "updated_at": None, "error": None, "errors": []}

    if key == "watchlist":
        from aqs.data import directory
        syms = [r["symbol"] for r in directory.watchlist()]
        return {"name": "watchlist", "source": "watchlist", "symbols": syms, "size": len(syms),
                "cache_file": directory._WATCHLIST_CSV, "updated_at": None,
                "error": None if syms else "自选股为空，请先加入自选。", "errors": []}

    if key in ("hs300", "zz500", "sz50", "all", "broad", "default_fast", "hs800"):
        from aqs.data import universe as U
        key = "all" if key == "broad" else key
        info = U.load(key, source=source, refresh=refresh or (not use_cache))
        size = info["raw_count"]
        err = None
        if size == 0:
            err = "；".join(info.get("errors") or []) or "数据源没有返回股票"
        names = {r["symbol"]: r.get("name", "") for r in info.get("rows", [])}
        return {"name": key, "source": info["source"], "symbols": info["symbols"], "size": size,
                "cache_file": info["cache_path"], "updated_at": info["updated_at"],
                "error": err, "errors": info.get("errors", []), "names": names}

    syms = list(DATA_CFG["symbols"])
    return {"name": "default", "source": "default", "symbols": syms, "size": len(syms),
            "cache_file": None, "updated_at": None, "error": None, "errors": [], "names": {}}


def resolve_universe(universe) -> List[str]:
    """解析 universe 为代码列表，并记录来源元信息（_LAST_UNIVERSE_META）。"""
    global _LAST_UNIVERSE_META, _LAST_UNIVERSE_NAMES
    info = load_universe(universe)
    _LAST_UNIVERSE_META = {k: info.get(k) for k in ("name", "source", "size", "cache_file", "updated_at", "error", "errors")}
    _LAST_UNIVERSE_NAMES = info.get("names", {}) or {}
    return info.get("symbols", [])


def data_update(universe: str = "hs800", force: bool = False, on_progress=None,
                per_symbol_timeout: float = 20.0, config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """联网更新历史行情缓存到 data/cache/bars（AkShare 优先，Baostock 补缺）。"""
    from aqs.data import bars_cache

    info = load_universe(universe)
    syms = info.get("symbols", [])
    if not syms:
        return {"success": False, "universe": universe, "error": info.get("error") or "股票池为空"}
    targets = list(dict.fromkeys(syms + [DATA_CFG["benchmark"]]))
    stats = bars_cache.update_bars(targets, DATA_CFG["start"], DATA_CFG["end"],
                                   on_progress=on_progress, force=force,
                                   per_symbol_timeout=per_symbol_timeout, universe=str(universe).lower())
    st = bars_cache.status(syms)
    return {"success": True, "universe": universe, **stats, **st}


def _resolve_symbols_arg(universe: Optional[str], symbols: Optional[List[str]]):
    """返回 (symbols, label)：优先用显式 symbols，否则按股票池解析。"""
    if symbols:
        return list(symbols), f"custom({len(symbols)})"
    info = load_universe(universe or "hs800")
    return info.get("symbols", []), (universe or "hs800")


def intraday_update(universe: str = "hs300", symbols: Optional[List[str]] = None, force: bool = False,
                    on_progress=None, per_symbol_timeout: float = 20.0) -> Dict[str, Any]:
    """联网更新 5 分钟行情缓存到 data/cache/intraday_5m（与选股分离）。"""
    from aqs.data import intraday_cache

    syms, label = _resolve_symbols_arg(universe, symbols)
    if not syms:
        return {"success": False, "universe": label, "error": "股票池为空"}
    stats = intraday_cache.update_intraday(syms, on_progress=on_progress, force=force,
                                           per_symbol_timeout=per_symbol_timeout,
                                           universe=label.lower())
    return {"success": True, "universe": label, **stats, **intraday_cache.status(syms)}


def intraday_status(universe: str = "hs800", symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """5 分钟行情缓存状态（离线）。"""
    from aqs.data import intraday_cache

    syms, label = _resolve_symbols_arg(universe, symbols)
    st = intraday_cache.status(syms)
    upd = intraday_cache.load_update_stats(label.lower())
    return {
        "universe": label,
        "universe_count": st["universe_count"],
        "cached_count": st["cached_count"],
        "valid_count": st["valid_count"],
        "missing_count": st["missing_count"],
        "stale_count": st["stale_count"],
        "failed_count": int(upd.get("failed", 0)),
        "last_updated": upd.get("last_updated"),
        "update_command": f"aquant intraday-update --universe {label.lower()}",
    }


def intraday_factors(symbols: List[str]) -> Dict[str, Any]:
    """返回若干股票的高频参与度/资金方向（离线，供验收/调试）。"""
    from aqs.data import intraday_cache, bars_cache

    out = {}
    for s in symbols:
        amt20 = None
        b = bars_cache.load_bars(s)
        if b is not None and "amount" in b:
            amt20 = float(b["amount"].astype(float).tail(20).mean())
        out[s] = intraday_cache.compute_intraday_factors(s, amt20)
    return out


def universe_data_status(universe: str = "hs800") -> Dict[str, Any]:
    """离线行情缓存状态（供 /api/data/status 与 CLI data-status）。"""
    from aqs.data import bars_cache

    info = load_universe(universe)
    syms = info.get("symbols", [])
    st = bars_cache.status(syms)
    upd = bars_cache.load_update_stats(str(universe).lower())
    gate = bars_cache.VALID_GATES.get(str(universe).lower(), 1)
    return {
        "universe": universe,
        "universe_count": st["universe_count"],
        "cached_count": st["cached_count"],
        "valid_count": st["valid_count"],
        "missing_count": st["missing_count"],
        "stale_count": st["stale_count"],
        "failed_count": int(upd.get("failed", 0)),
        "last_updated": upd.get("last_updated"),
        "ready_for_screening": st["valid_count"] >= gate,
        "update_command": f"aquant data-update --universe {str(universe).lower()}",
    }


def universe_status(name: str) -> Dict[str, Any]:
    """股票池诊断状态（供 /api/universe/status）。"""
    info = load_universe(name)
    diag = _LAST_SCREEN_DIAG if str(_LAST_SCREEN_DIAG.get("universe", "")).lower() == str(name).lower() else {}
    gate = _INDEX_MIN.get(str(name).lower())
    ok = not info.get("error") and (gate is None or info["size"] >= gate)
    return {
        "success": bool(ok),
        "universe": info["name"],
        "source": info["source"],
        "raw_count": info["size"],
        "after_basic_filter_count": diag.get("after_basic_filter_count"),
        "after_liquidity_filter_count": diag.get("after_liquidity_filter_count"),
        "final_count": diag.get("final_count"),
        "cache_path": info["cache_file"],
        "updated_at": info["updated_at"],
        "errors": info.get("errors", []) + ([info["error"]] if info.get("error") else []),
        "empty_reason": diag.get("empty_reason"),
    }


def _build_real_manager(symbols: List[str], config: SystemConfig, use_cache: bool = True):
    """按真实数据源构建管理器；配置源取数失败/为空时自动切换另一真实源。

    返回 (manager_or_None, used_source, errors)。
    """
    src = DATA_CFG["source"] if DATA_CFG["source"] in ("baostock", "akshare") else "baostock"
    order = [src] + [s for s in ("baostock", "akshare") if s != src]
    errs: List[str] = []
    last = None
    for s in order:
        common = dict(symbols=list(symbols), start=DATA_CFG["start"], end=DATA_CFG["end"],
                      benchmark=DATA_CFG["benchmark"], cache_dir=DATA_CFG["cache_dir"],
                      refresh=not use_cache, config=config)
        try:
            m = MarketDataManager.from_baostock(**common) if s == "baostock" else MarketDataManager.from_akshare(**common)
            if m.symbols:
                return m, s, errs
            errs.append(f"{s} 返回 0 只行情")
            last = m
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{s}: {exc}")
    return last, None, errs


def _manager_for_universe(syms: List[str], config: SystemConfig, use_cache: bool = True):
    """为给定股票池构建数据管理器（真实模式下直接按 syms 取数，跨源回退；不依赖默认池）。"""
    # 演示/示例模式：用示例数据并取交集
    if DATA_CFG.get("demo_mode") or DATA_CFG["source"] == "sample":
        mdm = get_data_manager(config)
        return mdm, [s for s in syms if s in mdm.symbols]
    m, used, errs = _build_real_manager(syms, config, use_cache=use_cache)
    if m is None:
        _ACTUAL["error"] = "；".join(errs)
        return MarketDataManager(config), []
    if used:
        _ACTUAL.update({"source": used, "is_real": True, "using_mock": False, "error": None})
    got = [s for s in syms if s in m.symbols]
    return m, got


_MKTCAP_CACHE: Dict[str, Dict[str, float]] = {}


def _get_market_caps(symbols: List[str]) -> Optional[Dict[str, float]]:
    """尽力获取市值（元）。优先 AkShare 全市场快照；失败则返回 None（市值显示 N/A）。"""
    if "all" in _MKTCAP_CACHE:
        caps = _MKTCAP_CACHE["all"]
        return {s: caps[s] for s in symbols if s in caps} or None
    try:
        import akshare as ak  # type: ignore

        spot = ak.stock_zh_a_spot_em()
        caps: Dict[str, float] = {}
        for _, r in spot.iterrows():
            code = str(r.get("代码", ""))
            mc = r.get("总市值")
            if code and pd.notna(mc):
                suffix = "SH" if code.startswith(("6", "5", "9")) else "SZ"
                caps[f"{code}.{suffix}"] = float(mc)
        if caps:
            _MKTCAP_CACHE["all"] = caps
            return {s: caps[s] for s in symbols if s in caps} or None
    except Exception as exc:  # noqa: BLE001
        print(f"[mktcap] 获取市值失败（按 N/A 处理）：{exc}")
    return None


def get_data_manager(config: SystemConfig = DEFAULT_CONFIG, refresh: bool = False) -> MarketDataManager:
    if not refresh and "default" in _DATA_CACHE:
        return _DATA_CACHE["default"]

    cfg = DATA_CFG
    src = cfg["source"]
    use_mock = cfg.get("demo_mode") or src == "sample"

    if use_mock:
        mgr = MarketDataManager.from_sample(config)
        _ACTUAL.update({"source": "sample", "is_real": False, "using_mock": True, "error": None})
        _DATA_CACHE["default"] = mgr
        return mgr

    # 真实数据源：配置源失败自动切换另一真实源；都失败不回退 mock，抛错由上层显示原因
    mgr, used, errs = _build_real_manager(cfg["symbols"], config, use_cache=not cfg["refresh"])
    if mgr is None or not mgr.symbols:
        msg = "真实数据源不可用，请检查 Baostock/AkShare 或网络连接（" + "；".join(errs) + "）"
        _ACTUAL.update({"source": src, "is_real": False, "using_mock": False, "error": msg})
        raise DataSourceError(msg)
    _ACTUAL.update({"source": used or src, "is_real": True, "using_mock": False, "error": None})
    _DATA_CACHE["default"] = mgr
    return mgr


def data_source_check() -> Dict[str, Any]:
    """检测各数据源可用性，供仪表盘「数据源检测」按钮。"""
    out = {
        "baostock_import": False, "baostock_login": False, "baostock_sample_ok": False,
        "akshare_import": False, "akshare_sample_ok": False,
        "using_mock": bool(_ACTUAL.get("using_mock")),
        "actual_source": _ACTUAL.get("source"),
        "configured_source": DATA_CFG["source"],
        "demo_mode": bool(DATA_CFG.get("demo_mode")),
        "error": None,
    }
    errs: List[str] = []
    try:
        import baostock as bs  # type: ignore
        out["baostock_import"] = True
        try:
            lg = bs.login()
            if getattr(lg, "error_code", "1") == "0":
                out["baostock_login"] = True
                rs = bs.query_history_k_data_plus(
                    "sh.600519", "date,close", start_date="2023-12-01", end_date="2023-12-10",
                    frequency="d", adjustflag="3")
                df = rs.get_data() if getattr(rs, "error_code", "1") == "0" else None
                out["baostock_sample_ok"] = bool(df is not None and not df.empty)
            else:
                errs.append(f"baostock 登录失败: {getattr(lg, 'error_msg', '')}")
            bs.logout()
        except Exception as exc:  # noqa: BLE001
            errs.append(f"baostock: {exc}")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"baostock 未安装: {exc}")
    try:
        import akshare as ak  # type: ignore
        out["akshare_import"] = True
        try:
            df = ak.stock_zh_a_hist(symbol="600519", period="daily",
                                    start_date="20231201", end_date="20231210", adjust="qfq")
            out["akshare_sample_ok"] = bool(df is not None and not df.empty)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"akshare 获取失败: {exc}")
    except Exception as exc:  # noqa: BLE001
        errs.append(f"akshare 未安装: {exc}")
    out["error"] = "; ".join(errs) if errs else None
    return out


def active_source() -> str:
    return _ACTUAL["source"] or DATA_CFG["source"]


def data_status() -> Dict[str, Any]:
    """仪表盘顶部状态：数据源 / 数据日期 / 系统时间 / 是否真实数据。"""
    base = {
        "configured_source": DATA_CFG["source"],
        "actual_source": _ACTUAL["source"] or DATA_CFG["source"],
        "is_real_data": False,
        "using_mock": bool(DATA_CFG.get("demo_mode") or DATA_CFG["source"] == "sample"),
        "demo_mode": bool(DATA_CFG.get("demo_mode")),
        "data_date": None,
        "system_time": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "n_symbols": 0,
        "universe_start": DATA_CFG["start"],
        "universe_end": DATA_CFG["end"],
        "error": None,
    }
    try:
        mgr = get_data_manager()
    except DataSourceError as exc:
        base["error"] = str(exc)
        return base
    sessions = mgr.trading_dates()
    base.update({
        "actual_source": _ACTUAL["source"] or DATA_CFG["source"],
        "is_real_data": bool(_ACTUAL["is_real"]),
        "using_mock": bool(_ACTUAL["using_mock"]),
        "data_date": str(sessions[-1].date()) if len(sessions) else None,
        "n_symbols": len(mgr.symbols),
        "error": _ACTUAL.get("error"),
        "universe": _ACTUAL.get("universe"),
    })
    return base


def list_strategies() -> Dict[str, str]:
    return {key: cls.name for key, cls in TEMPLATES.items()}


_STRATEGY_DESC = {
    "predictive_ranking": {
        "use": "找未来 3/5/10 天可能上涨的股票（不是已经最强的），给出上涨概率/预期收益/风险等级。",
        "factors": "K线技术(MA/MACD/KDJ/RSI/布林/ATR)+量价资金+趋势形态+舆情关注度+风险，两层模型(规则过滤+预测评分)。",
        "risk": "预测概率不代表确定收益，历史表现不代表未来；跌破关键均线模型信号可能失效。",
    },
    "short_strength": {
        "use": "筛选近期放量上攻、值得 1-10 天重点观察的短线强势股（非慢速蓝筹）。",
        "factors": "3/5/10日涨幅、量能放大倍数、站上MA5/MA10、突破20日新高、RSI 50-85。",
        "risk": "短线波动大，追高/超买风险高；务必设止损，避免连续大跌与流动性差个股。",
    },
    "trend_quality": {
        "use": "筛选趋势稳健、回撤可控、适合 1-8 周持有的中短线趋势股。",
        "factors": "MA20/MA60多头排列、20日波动率、最大回撤、成交额稳定性、价格强度。",
        "risk": "趋势可能反转；放量破位需及时离场。",
    },
    "quality_value": {
        "use": "筛选估值合理、盈利质量好、适合 1-6 个月中线的质量价值股。",
        "factors": "ROE、低PE/PB、营收/净利增长、趋势过滤。",
        "risk": "价值回归较慢；注意基本面变化与行业景气下行。",
    },
}


def strategy_catalog() -> Dict[str, Any]:
    """返回分类后的策略目录：核心 / 高级实验，含中文名、适用周期与说明。"""
    from aqs.strategy.templates import CORE_STRATEGIES, ADVANCED_STRATEGIES, DEFAULT_STRATEGY
    from aqs.research.screener import PROFILES

    def entry(key):
        cls = TEMPLATES[key]
        prof = PROFILES.get(key)
        d = _STRATEGY_DESC.get(key, {})
        return {"key": key, "name": cls.name, "horizon": getattr(prof, "horizon", ""),
                "use": d.get("use", ""), "factors": d.get("factors", ""), "risk": d.get("risk", "")}

    return {
        "core": [entry(k) for k in CORE_STRATEGIES],
        "advanced": [entry(k) for k in ADVANCED_STRATEGIES],
        "default": DEFAULT_STRATEGY,
    }


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
    strategy: str = "predictive_ranking",
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

    eq = result.equity_curve
    out: Dict[str, Any] = {
        "strategy": strategy,
        "strategy_name": strat.name,
        "params": params or {},
        "settings": {
            "benchmark": mdm.benchmark_symbol,
            "fill_mode": fill_mode,
            "rebalance": rebalance or getattr(strat, "rebalance", None),
            "start": str(eq.index[0].date()) if len(eq) else None,
            "end": str(eq.index[-1].date()) if len(eq) else None,
            "commission_rate": config.cost.commission_rate,
            "stamp_duty_rate": config.cost.stamp_duty_rate,
            "slippage_bps": config.cost.slippage_bps,
            "max_position": max_position if max_position is not None else config.risk.max_position_per_stock,
        },
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
    if DATA_CFG.get("demo_mode") or DATA_CFG["source"] == "sample":
        mdm = get_data_manager(config)
        return mdm if symbol in mdm.symbols else None
    m, _used, _errs = _build_real_manager([symbol], config, use_cache=True)
    return m if (m is not None and symbol in m.symbols) else None


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


def _sentiment_records(symbols, names=None, asof=None, use_cache: bool = True):
    """获取一组股票的舆情记录 (records, meta)。"""
    from aqs.sentiment.engine import SentimentEngine

    eng = SentimentEngine(source=DATA_CFG.get("sentiment_source", "auto"),
                          demo_mode=bool(DATA_CFG.get("demo_mode")))
    return eng.get_sentiment(list(symbols), names=names or {}, asof=asof, use_cache=use_cache)


def sentiment_for(symbol: str, config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """单只股票舆情详情。"""
    from aqs.data import directory

    resolved = directory.resolve(symbol) or symbol
    name = directory.name_of(resolved)
    records, meta = _sentiment_records([resolved], names={resolved: name})
    rec = records.get(resolved)
    if not rec:
        return {"symbol": resolved, "name": name, "available": False, "meta": meta,
                "message": "暂无舆情数据（未接入真实舆情源；演示模式下可用示例舆情）。",
                "disclaimer": meta.get("disclaimer", "")}
    return {"symbol": resolved, "name": name or rec.get("name", ""), "available": True,
            "is_mock": bool(rec.get("is_mock")), "meta": meta, "sentiment": rec,
            "disclaimer": meta.get("disclaimer", "")}


def sentiment_top(top_n: int = 20, universe=None, config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """按关注度排序的热门股。"""
    mdm = get_data_manager(config)
    syms = resolve_universe(universe) if universe is not None and str(universe) not in ("", "default") else list(mdm.symbols)
    names = {s: (mdm.instrument(s).name if mdm.instrument(s) else "") for s in syms}
    records, meta = _sentiment_records(syms, names=names)
    rows = sorted(records.values(), key=lambda r: r.get("attention_score", 0), reverse=True)[:top_n]
    return {"top_n": top_n, "available": bool(rows), "is_mock": bool(meta.get("is_mock")),
            "meta": meta, "results": rows, "disclaimer": meta.get("disclaimer", "")}


def predict_symbol(symbol: str, horizon: int = 5, use_sentiment: bool = False,
                   config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """单只股票的预测上涨模型结果。"""
    from aqs.data import directory
    from aqs.ml.predictive import predict_universe, DISCLAIMER

    resolved = directory.resolve(symbol)
    if not resolved:
        return {"success": False, "error": "未找到该股票代码或名称。"}
    try:
        mdm = _manager_for_symbol(resolved, config)
    except Exception as exc:  # noqa: BLE001
        return {"success": False, "error": f"数据源取数失败，请检查 Baostock/AkShare：{exc}"}
    if mdm is None:
        return {"success": False, "error": "数据源取数失败，请检查 Baostock/AkShare。"}
    sentiment = None
    if use_sentiment:
        sentiment, _ = _sentiment_records([resolved], names={resolved: directory.name_of(resolved)})
    df = predict_universe(mdm, universe=[resolved], top_n=1, sentiment=sentiment)
    if df.empty or resolved not in df.index:
        return {"success": False, "error": "数据不足，无法预测该股票。"}
    rec = df.loc[resolved].to_dict()
    rec.pop("feat", None)
    return {"success": True, "symbol": resolved, "name": rec.get("name", ""),
            "horizon": horizon, "prediction": {k: rec[k] for k in rec},
            "disclaimer": DISCLAIMER}


def predict_top(top_n: int = 20, universe=None, horizon: int = 5, use_sentiment: bool = False,
                config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    res = screen_stocks(strategy="predictive_ranking", top_n=top_n, universe=universe,
                        use_sentiment=use_sentiment, config=config)
    res["horizon"] = horizon
    return res


def normalize_symbol(text: str) -> Optional[str]:
    """把代码片段或中文名称标准化为带交易所后缀的代码（找不到返回 None）。

    - '600519.SH' / '300750.SZ' → 原样
    - 6 开头 6 位 → .SH；0/3 开头 → .SZ；8/4 开头 → .BJ
    - 中文名称 → 从全市场目录搜索匹配
    """
    from aqs.data import directory

    return directory.resolve(text)


def forecast_symbol(symbol: str, horizon: int = 5, config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    from aqs.ml.forecast import analyze_and_forecast
    from aqs.data import directory

    # 支持输入代码或名称（如 "贵州茅台" / "600519" / "600519.SH"）
    resolved = directory.resolve(symbol)
    if not resolved:
        return {"symbol": symbol, "error": "未找到该股票代码或名称"}

    try:
        mdm = _manager_for_symbol(resolved, config)
    except Exception as exc:  # noqa: BLE001
        return {"symbol": resolved, "error": f"数据源取数失败，请检查 Baostock/AkShare：{exc}"}
    if mdm is None:
        return {"symbol": resolved, "error": "数据源取数失败，请检查 Baostock/AkShare（示例数据模式仅支持内置标的）"}

    try:
        res = analyze_and_forecast(mdm, resolved, horizon=horizon)
    except Exception as exc:  # noqa: BLE001
        return {"symbol": resolved, "error": f"分析失败：{type(exc).__name__}: {exc}"}
    if not isinstance(res, dict):
        return {"symbol": resolved, "error": "分析失败：无结果"}
    if res.get("error"):
        return res
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


# ============================================================ 短线选股时间模式
TRADING_MODES = [
    {"key": "after_close", "name": "收盘后选股", "window": "15:10 以后",
     "desc": "用当天完整日线数据生成明日短线观察池"},
    {"key": "auction_confirm", "name": "竞价确认", "window": "9:25-9:30",
     "desc": "检查昨日观察池在集合竞价后的表现"},
    {"key": "open_confirm", "name": "开盘确认", "window": "9:30-10:00",
     "desc": "检查开盘后是否有分时承接"},
    {"key": "close_review", "name": "尾盘复核", "window": "14:30-14:50",
     "desc": "筛选全天强势且无明显回落的股票，加入次日观察池"},
]

_DISCLAIMER = "所有结果仅供研究，不构成投资建议。市场有风险，投资需谨慎。"


def current_mode() -> Dict[str, Any]:
    """根据当前系统时间给出建议运行的时间模式。"""
    now = _dt.datetime.now()
    t = now.hour * 60 + now.minute
    is_trading_day = now.weekday() < 5
    suggested = None
    if t >= 15 * 60 + 10:
        suggested = "after_close"
    elif 9 * 60 + 25 <= t < 9 * 60 + 30:
        suggested = "auction_confirm"
    elif 9 * 60 + 30 <= t < 10 * 60:
        suggested = "open_confirm"
    elif 14 * 60 + 30 <= t <= 14 * 60 + 50:
        suggested = "close_review"

    if not is_trading_day:
        suggested = None
        advice = "今日非交易日，建议仅查看研究结果。"
    elif suggested is None:
        advice = "当前非关键交易决策窗口，建议仅查看研究结果。"
    else:
        name = next(m["name"] for m in TRADING_MODES if m["key"] == suggested)
        advice = f"建议运行「{name}」。"

    return {
        "suggested": suggested,
        "advice": advice,
        "is_trading_day": is_trading_day,
        "system_time": now.strftime("%Y-%m-%d %H:%M:%S"),
        "modes": TRADING_MODES,
        "disclaimer": _DISCLAIMER,
    }


def _watch_pool_path() -> str:
    return os.path.join(_ensure_outputs(), "watch_pool.json")


def _save_watch_pool(picks: List[dict], kind: str) -> None:
    import json

    data = {
        "kind": kind,
        "saved_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbols": [{"symbol": p["symbol"], "name": p.get("name", ""), "industry": p.get("industry", ""),
                     "close": p.get("close"), "score": p.get("score"), "signal": p.get("signal")}
                    for p in picks],
    }
    with open(_watch_pool_path(), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)


def load_watch_pool() -> Dict[str, Any]:
    import json

    path = _watch_pool_path()
    if not os.path.exists(path):
        return {"symbols": [], "kind": None, "saved_at": None}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {"symbols": [], "kind": None, "saved_at": None}


def _get_auction(symbols: List[str]) -> Optional[Dict[str, Dict[str, float]]]:
    """尽力获取集合竞价快照；数据源不支持则返回 None。"""
    src = DATA_CFG["source"]
    try:
        if src == "akshare":
            from aqs.data.sources.akshare_source import AkShareDataSource
            return AkShareDataSource().get_call_auction(symbols)
        if src == "qmt":
            from aqs.data.sources.qmt import QMTDataSource
            return QMTDataSource().get_call_auction(symbols)
    except Exception as exc:  # noqa: BLE001
        print(f"[auction] 获取竞价数据失败：{exc}")
    return None


def _realtime_spot(symbols: List[str]) -> Optional[Dict[str, dict]]:
    """尽力获取实时快照(AkShare)；失败返回 None。"""
    try:
        import akshare as ak  # type: ignore

        spot = ak.stock_zh_a_spot_em()
        want = {s.split(".")[0] for s in symbols}
        out = {}
        for _, r in spot.iterrows():
            code = str(r.get("代码", ""))
            if code not in want:
                continue
            suffix = "SH" if code.startswith(("6", "5", "9")) else "SZ"
            out[f"{code}.{suffix}"] = {
                "open": r.get("今开"), "prev_close": r.get("昨收"), "last": r.get("最新价"),
                "pct": r.get("涨跌幅"), "amount": r.get("成交额"), "high": r.get("最高"), "low": r.get("最低"),
            }
        return out or None
    except Exception as exc:  # noqa: BLE001
        print(f"[realtime] 获取实时行情失败：{exc}")
        return None


def run_mode(mode: str, strategy: str = "short_strength", top_n: int = 20,
             config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """运行某个时间模式。"""
    if mode == "after_close":
        res = screen_stocks(strategy=strategy, top_n=top_n, save=True, config=config)
        _save_watch_pool(res["picks"], "明日观察池")
        res.update({"mode": mode, "title": f"明日观察池 Top {top_n}", "disclaimer": _DISCLAIMER})
        return res

    if mode == "close_review":
        res = screen_stocks(strategy=strategy, top_n=top_n * 2, save=False, config=config)
        mdm = get_data_manager(config)
        picks = []
        for p in res["picks"]:
            sym = p["symbol"]
            try:
                bar = mdm.get_price(sym, fields=["open", "high", "low", "close"]).dropna().iloc[-1]
                rng = float(bar["high"]) - float(bar["low"])
                strength = (float(bar["close"]) - float(bar["low"])) / rng if rng > 0 else 1.0
                day_ret = float(bar["close"]) / float(bar["open"]) - 1.0 if bar["open"] else 0.0
            except Exception:
                strength, day_ret = None, None
            # 全天强势且无明显回落：收盘价位于当日偏上 + 当日上涨
            if strength is not None and strength >= 0.5 and day_ret is not None and day_ret > 0:
                p["intraday_strength"] = round(strength, 2)
                p["day_return"] = round(day_ret, 4)
                picks.append(p)
            if len(picks) >= top_n:
                break
        _save_watch_pool(picks, "次日观察池")
        return {"mode": mode, "title": f"尾盘复核 → 次日观察池 ({len(picks)})", "picks": picks,
                "strategy_name": res.get("strategy_name"), "asof": res.get("asof"),
                "is_real_data": res.get("is_real_data"), "source": res.get("source"),
                "note": "用日线近似：收盘位于当日价格区间偏上且当日上涨视为全天强势无明显回落。",
                "disclaimer": _DISCLAIMER}

    if mode == "auction_confirm":
        pool = load_watch_pool()
        syms = [s["symbol"] for s in pool.get("symbols", [])]
        if not syms:
            return {"mode": mode, "supported": True, "picks": [],
                    "message": "暂无观察池，请先运行「收盘后选股」生成明日观察池。", "disclaimer": _DISCLAIMER}
        auction = _get_auction(syms)
        if not auction:
            return {"mode": mode, "supported": False,
                    "message": "当前数据源不支持竞价确认（需 AkShare 实时或券商 miniQMT 竞价数据）。",
                    "disclaimer": _DISCLAIMER}
        rows = []
        for s in pool["symbols"]:
            a = auction.get(s["symbol"])
            if not a:
                continue
            gap = a.get("gap")
            rows.append({
                "symbol": s["symbol"], "name": s.get("name", ""),
                "auction_pct": round(gap, 4) if gap is not None else None,
                "auction_amount": a.get("auction_vol_ratio"),
                "high_open_too_much": bool(gap is not None and gap > 0.05),
                "low_open_break": bool(gap is not None and gap < -0.03),
            })
        return {"mode": mode, "supported": True, "title": "竞价确认", "picks": rows, "disclaimer": _DISCLAIMER}

    if mode == "open_confirm":
        pool = load_watch_pool()
        syms = [s["symbol"] for s in pool.get("symbols", [])]
        if not syms:
            return {"mode": mode, "realtime": False, "picks": [],
                    "message": "暂无观察池，请先运行「收盘后选股」。", "disclaimer": _DISCLAIMER}
        spot = _realtime_spot(syms)
        if not spot:
            return {"mode": mode, "realtime": False,
                    "message": "无实时行情数据：仅供人工参考，不生成买入信号。",
                    "advice": "请人工观察：是否站上分时均价线、开盘是否放量承接、所属板块是否走强；"
                              "高开过多注意回落风险，低开破位注意止损。",
                    "picks": pool["symbols"], "disclaimer": _DISCLAIMER}
        rows = []
        for s in pool["symbols"]:
            q = spot.get(s["symbol"])
            if not q:
                continue
            op, prev, last = q.get("open"), q.get("prev_close"), q.get("last")
            open_pct = (op / prev - 1.0) if (op and prev) else None
            rows.append({
                "symbol": s["symbol"], "name": s.get("name", ""),
                "open_pct": round(open_pct, 4) if open_pct is not None else None,
                "now_pct": round(float(q["pct"]) / 100, 4) if q.get("pct") is not None else None,
                "amount": q.get("amount"),
                "above_open": bool(last and op and last >= op),
            })
        return {"mode": mode, "realtime": True, "title": "开盘确认", "picks": rows, "disclaimer": _DISCLAIMER}

    return {"error": f"未知模式: {mode}"}


def stock_detail(symbol: str, strategy: str = "short_strength", config: SystemConfig = DEFAULT_CONFIG) -> Dict[str, Any]:
    """单只股票的策略解读：为何被选中、关键因子、风险、近期趋势与流动性。"""
    from aqs.data import directory
    from aqs.research.screener import Screener, ScreenConfig, PROFILES

    resolved = directory.resolve(symbol)
    if not resolved:
        return {"symbol": symbol, "error": "未找到该股票代码或名称"}

    mdm = _manager_for_symbol(resolved, config)
    if mdm is None:
        return {"symbol": resolved, "error": "无法获取该股票数据（请切换到 Baostock/AkShare）"}

    profile = strategy if strategy in PROFILES else "short_strength"
    universe = mdm.symbols if resolved in mdm.symbols else [resolved]
    df = Screener(ScreenConfig(exclude_st=False), profile=profile).screen(mdm, universe=universe, top_n=len(universe))
    if df.empty or resolved not in df.index:
        return {"symbol": resolved, "error": "数据不足，无法解读"}
    row = df.loc[resolved].to_dict()

    trend = mdm.get_price(resolved, fields=["close"])["close"].dropna().tail(60)
    inst = mdm.instrument(resolved)
    factors = {k: row.get(k) for k in
               ["ret_5d", "ret_20d", "ret_60d", "vol_ratio", "rsi", "volatility",
                "max_drawdown", "pe", "pb", "roe"] if k in row}
    sent = sentiment_for(resolved, config=config)
    return {
        "symbol": resolved,
        "name": (inst.name if inst and inst.name else directory.name_of(resolved)),
        "industry": row.get("industry"),
        "strategy": profile,
        "strategy_name": PROFILES[profile].name,
        "rank": int(row["rank"]) if "rank" in row else None,
        "score": round(float(row.get("score", 0)), 4),
        "signal": row.get("signal"),
        "reason": row.get("reason"),
        "risk": row.get("risk"),
        "last_price": row.get("close"),
        "amount": row.get("amount"),
        "factors": {k: (round(float(v), 4) if v is not None and pd.notna(v) else None) for k, v in factors.items()},
        "trend": [{"date": str(i.date()), "close": round(float(v), 2)} for i, v in trend.items()],
        "sentiment": sent,
        "disclaimer": "以上为量化解读，不构成投资建议；舆情为辅助因子，舆情热度不等于投资价值。",
    }


def refresh_real_data(
    strategy: str = "predictive_ranking",
    forecast_sym: str = "600519.SH",
    top_n: int = 20,
    run_backtest_too: bool = False,
) -> Dict[str, Any]:
    """重新拉取真实数据并刷新 screen / forecast 输出（供仪表盘"刷新"按钮）。

    预测模型回测较慢，默认不在刷新里跑回测（可由前端"策略历史表现"按需运行）。
    """
    get_data_manager(refresh=True)  # 重新加载数据
    screen = screen_stocks(strategy=strategy, top_n=top_n, save=True)
    forecast = forecast_symbol(forecast_sym)
    out = {
        "status": data_status(),
        "screen": screen,
        "forecast": forecast,
        "refreshed_at": _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if run_backtest_too:
        out["backtest_metrics"] = run_backtest(strategy=strategy, save=True, monte_carlo=False)["metrics"]
    return out


# 最近一次选股的分层诊断（供 /api/universe/status 读取）
_LAST_SCREEN_DIAG: Dict[str, Any] = {}


def _screen_err(strategy: str, msg: str, diag: Dict[str, Any]) -> dict:
    global _LAST_SCREEN_DIAG
    diag.setdefault("final_count", 0)
    _LAST_SCREEN_DIAG = diag
    return {"strategy": strategy, "error": msg, "picks": [], "diagnostics": diag,
            "is_real_data": bool(_ACTUAL["is_real"]), "source": active_source()}


def _filter_diagnostics(mdm, syms: List[str], min_amount: float) -> Dict[str, Any]:
    """分层统计：基础过滤(ST/停牌/退市) -> 流动性过滤 后剩余数量。"""
    basic = 0
    liq = 0
    for s in syms:
        inst = mdm.instrument(s)
        if inst and inst.is_st:
            continue
        if not mdm.is_active(s):
            continue
        basic += 1
        try:
            amt = mdm.get_price(s, fields=["amount"])["amount"].dropna().tail(20).mean()
        except Exception:
            amt = None
        if (not min_amount) or (amt is not None and amt >= min_amount):
            liq += 1
    return {"after_basic_filter_count": basic, "after_liquidity_filter_count": liq}


def screen_stocks(
    strategy: str = "short_strength",
    top_n: int = 20,
    universe=None,
    asof: Optional[str] = None,
    min_amount: float = 0.0,
    exclude_st: bool = True,
    exclude_slow_blue_chip: bool = True,
    max_market_cap: float = 3000e8,
    use_cache: bool = True,
    use_sentiment: bool = False,
    lenient: bool = False,
    auction: Optional[dict] = None,
    save: bool = False,
    config: SystemConfig = DEFAULT_CONFIG,
) -> dict:
    """按所选策略画像筛选 Top N 候选股（含信号/选中原因/风险提示）。"""
    from aqs.research.screener import Screener, ScreenConfig, PROFILES, ShortStrengthProfile

    from aqs.data import bars_cache

    uni_key = str(universe).lower() if universe else "default"
    diag: Dict[str, Any] = {"universe": uni_key}

    # 解析股票池代码与名称
    if universe is not None and str(universe) not in ("", "default"):
        resolved = resolve_universe(universe)
        meta = dict(_LAST_UNIVERSE_META)
        uni_names = dict(_LAST_UNIVERSE_NAMES)
        _ACTUAL["universe"] = meta
        diag.update({"source": meta.get("source"), "raw_count": meta.get("size", 0),
                     "cache_path": meta.get("cache_file"), "updated_at": meta.get("updated_at"),
                     "errors": meta.get("errors", [])})
        diag["stage"] = "load_universe"
        if uni_key == "watchlist" and meta.get("size", 0) < 1:
            return _screen_err(strategy, "自选股为空，请先加入自选。", diag)
        if meta.get("error"):
            return _screen_err(strategy, meta["error"], diag)
        gate0 = _INDEX_MIN.get(uni_key)
        if gate0 and meta.get("size", 0) < gate0:
            return _screen_err(strategy, f"股票池数量异常，当前仅 {meta.get('size', 0)} 只（{uni_key} 期望≥{gate0}）。", diag)
    else:
        resolved = list(DATA_CFG["symbols"])
        uni_names = {}
        diag.update({"source": "default", "raw_count": len(resolved)})

    # 示例/演示模式：用示例数据（离线）；真实模式：仅读本地行情缓存（离线，禁止联网）
    if DATA_CFG.get("demo_mode") or DATA_CFG["source"] == "sample":
        mdm = get_data_manager(config)
        syms = [s for s in resolved if s in mdm.symbols]
        diag.update({"source": "sample", "loaded_count": len(syms), "valid_count": len(syms),
                     "missing_count": len(resolved) - len(syms), "stale_count": 0})
    else:
        diag["stage"] = "load_cache"
        st = bars_cache.status(resolved)
        diag.update({"cached_count": st["cached_count"], "valid_count": st["valid_count"],
                     "missing_count": st["missing_count"], "stale_count": st["stale_count"]})
        valid_gate = bars_cache.VALID_GATES.get(uni_key, 1 if uni_key in ("default", "custom") else 1)
        if st["valid_count"] < valid_gate:
            cmd = f"aquant data-update --universe {uni_key if uni_key not in ('default','custom') else 'hs800'}"
            diag["empty_reason"] = (f"本地有效行情仅 {st['valid_count']} 只（需≥{valid_gate}）："
                                    f"缺失 {st['missing_count']} 只、过期 {st['stale_count']} 只。请先离线更新行情。")
            return _screen_err(strategy, f"行情缓存不足，无法离线选股。{diag['empty_reason']} 运行：{cmd}", diag)
        mdm = MarketDataManager.from_cache(resolved, names=uni_names, benchmark=DATA_CFG["benchmark"], config=config)
        syms = [s for s in resolved if s in mdm.symbols and bars_cache.is_valid(s)]
        diag["loaded_count"] = len(syms)
        _ACTUAL.update({"is_real": True, "using_mock": False, "source": "cache"})

    sessions = mdm.trading_dates(end=asof) if asof else mdm.trading_dates()
    asof_date = asof or (str(sessions[-1].date()) if len(sessions) else None)

    # 预测上涨模型走独立的 ML 引擎
    if strategy == "predictive_ranking":
        from aqs.ml.predictive import predict_universe, DISCLAIMER

        sentiment = sent_meta = None
        if use_sentiment:
            names = {s: (mdm.instrument(s).name if mdm.instrument(s) else "") for s in syms}
            sentiment, sent_meta = _sentiment_records(syms, names=names, asof=asof, use_cache=use_cache)
        uni_names = _LAST_UNIVERSE_NAMES if (universe is not None and str(universe) not in ("", "default")) else {}
        from aqs.data import intraday_cache as _intra
        _intraday_fn = lambda s, amt20: _intra.compute_intraday_factors(s, amt20)  # 离线读取分钟缓存
        df = predict_universe(mdm, universe=syms or None, asof=asof, top_n=top_n, sentiment=sentiment,
                              min_amount=(1e7 if lenient else 5e7), names=uni_names, intraday_fn=_intraday_fn)
        picks = df.reset_index().to_dict(orient="records") if not df.empty else []
        _fill_names(picks, uni_names)
        diag["final_count"] = len(picks)
        if not picks:
            diag.setdefault("empty_reason", "因子/规则筛选过严，未筛出股票（可开启宽松模式或扩大股票池）")
        global _LAST_SCREEN_DIAG
        _LAST_SCREEN_DIAG = diag
        return {
            "strategy": "predictive_ranking", "strategy_name": "预测上涨模型",
            "horizon": "未来 3/5/10 个交易日",
            "asof": asof_date, "top_n": top_n,
            "universe": universe if isinstance(universe, str) else (f"custom({len(syms)})" if universe else "default"),
            "use_sentiment": bool(use_sentiment), "sentiment_meta": sent_meta,
            "lenient": bool(lenient), "diagnostics": diag,
            "is_real_data": bool(_ACTUAL["is_real"]), "source": active_source(),
            "picks": picks, "disclaimer": DISCLAIMER,
        }

    eff_min_amount = min(min_amount, 1e7) if lenient else min_amount
    cfg = ScreenConfig(exclude_st=exclude_st, min_amount=eff_min_amount)
    profile = strategy if strategy in PROFILES else "short_strength"
    # 短线强势：支持排除超大市值慢速蓝筹（尽力获取市值，取不到则按 N/A 跳过该过滤）
    market_caps = None
    prof_obj = profile
    if profile == "short_strength":
        kw = dict(exclude_slow_blue_chip=exclude_slow_blue_chip, max_market_cap=max_market_cap)
        if lenient:  # 宽松模式：放宽强势硬条件
            kw.update(ret5_min=0.0, amount_ratio_min=1.0, rsi_min=40.0, rsi_max=90.0, min_amount=1e7)
        prof_obj = ShortStrengthProfile(**kw)
        if exclude_slow_blue_chip:
            market_caps = _get_market_caps(syms)

    sentiment = None
    sent_meta = None
    if use_sentiment:
        names = {s: (mdm.instrument(s).name if mdm.instrument(s) else "") for s in syms}
        sentiment, sent_meta = _sentiment_records(syms, names=names, asof=asof, use_cache=use_cache)

    df = Screener(cfg, profile=prof_obj).screen(
        mdm, universe=syms or None, asof=asof, top_n=top_n, auction=auction,
        market_caps=market_caps, sentiment=sentiment)

    sessions = mdm.trading_dates(end=asof) if asof else mdm.trading_dates()
    asof_date = asof or (str(sessions[-1].date()) if len(sessions) else None)
    picks = df.reset_index().to_dict(orient="records") if not df.empty else []
    _fill_names(picks, _LAST_UNIVERSE_NAMES if (universe is not None and str(universe) not in ("", "default")) else {})
    diag["final_count"] = len(picks)
    if not picks:
        diag.setdefault("empty_reason", "因子/规则筛选过严，未筛出股票（可开启宽松模式或扩大股票池）")
    _LAST_SCREEN_DIAG = diag
    out = {
        "strategy": profile,
        "strategy_name": PROFILES[profile].name,
        "horizon": PROFILES[profile].horizon,
        "asof": asof_date,
        "top_n": top_n,
        "universe": universe if isinstance(universe, str) else (f"custom({len(syms)})" if universe else "default"),
        "min_amount": min_amount,
        "exclude_st": exclude_st,
        "use_sentiment": bool(use_sentiment),
        "sentiment_meta": sent_meta,
        "lenient": bool(lenient),
        "diagnostics": diag,
        "is_real_data": bool(_ACTUAL["is_real"]),
        "source": active_source(),
        "picks": picks,
        "disclaimer": "选股结果仅为量化参考，不构成投资建议；请结合风控与人工复核。"
                       + ("　舆情为辅助因子，舆情热度不等于投资价值。" if use_sentiment else ""),
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
