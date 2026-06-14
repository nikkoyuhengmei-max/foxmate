"""FastAPI application exposing the system over a local web API + dashboard.

Run with::

    aquant serve            # or: uvicorn aqs.api.server:app --reload

Then open http://127.0.0.1:8000 in a browser. Everything runs locally; no data
leaves the machine.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    from fastapi import FastAPI, Query
    from fastapi.responses import HTMLResponse, JSONResponse
except Exception as exc:  # pragma: no cover
    raise ImportError(
        "FastAPI is required for the web API. Install with `pip install -e .[web]`."
    ) from exc

from aqs import __version__
from aqs import service

_HERE = os.path.dirname(__file__)
_DASHBOARD = os.path.join(_HERE, "static", "dashboard.html")


def create_app() -> "FastAPI":
    app = FastAPI(title="AQuant - A股量化交易系统", version=__version__)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        with open(_DASHBOARD, "r", encoding="utf-8") as fh:
            return fh.read()

    @app.get("/api/health")
    def health() -> Dict[str, Any]:
        routes = sorted({getattr(r, "path", "") for r in app.routes if getattr(r, "path", "").startswith("/api")})
        return {
            "status": "ok",
            "version": __version__,
            "data_source": service.DATA_CFG["source"],
            "available_routes": routes,
        }

    @app.get("/api/status")
    def status() -> Dict[str, Any]:
        st = service.data_status()
        st["version"] = __version__
        st["has_trade_records"] = service.recent_trades(limit=1)["has_records"]
        return st

    @app.get("/api/trades")
    def trades() -> Dict[str, Any]:
        return service.recent_trades()

    @app.post("/api/refresh")
    def refresh(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        return service.refresh_real_data(
            strategy=payload.get("strategy", "multi_factor"),
            forecast_sym=payload.get("symbol", "600519.SH"),
            top_n=payload.get("top_n", 8),
        )

    @app.get("/api/strategies")
    def strategies() -> Dict[str, str]:
        return service.list_strategies()

    @app.get("/api/strategies/catalog")
    def strategies_catalog() -> Dict[str, Any]:
        return service.strategy_catalog()

    @app.get("/api/timing/mode")
    def timing_mode() -> Dict[str, Any]:
        return service.current_mode()

    @app.post("/api/timing/run")
    def timing_run(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        return service.run_mode(
            payload.get("mode", "after_close"),
            strategy=payload.get("strategy", "short_strength"),
            top_n=payload.get("top_n", 20),
        )

    @app.get("/api/stock/detail")
    def stock_detail(symbol: str = Query(...), strategy: str = "short_strength") -> Dict[str, Any]:
        return service.stock_detail(symbol, strategy=strategy)

    @app.get("/api/symbols")
    def symbols() -> List[dict]:
        return service.list_symbols()

    @app.get("/api/quality")
    def quality() -> List[dict]:
        return service.data_quality()

    @app.post("/api/backtest")
    def backtest(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        payload = payload or {}
        return service.run_backtest(
            strategy=payload.get("strategy", "multi_factor"),
            params=payload.get("params"),
            start=payload.get("start"),
            end=payload.get("end"),
            fill_mode=payload.get("fill_mode", "next_open"),
        )

    @app.get("/api/backtest")
    def backtest_get(strategy: str = "multi_factor", fill_mode: str = "next_open") -> Dict[str, Any]:
        return service.run_backtest(strategy=strategy, fill_mode=fill_mode)

    @app.get("/api/paper")
    def paper(strategy: str = "double_ma") -> Dict[str, Any]:
        return service.run_paper(strategy=strategy)

    @app.get("/api/forecast")
    def forecast(symbol: str = Query(...), horizon: int = 5) -> Dict[str, Any]:
        return service.forecast_symbol(symbol, horizon=horizon)

    @app.post("/api/forecast/run")
    def forecast_run(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """运行走势分析与预测（前端「分析并预测」按钮调用）。"""
        import datetime as _dt

        payload = payload or {}
        raw = str(payload.get("symbol", "")).strip()
        if not raw:
            return {"success": False, "error": "请输入股票代码或名称。"}
        resolved = service.normalize_symbol(raw)
        if not resolved:
            return {"success": False, "error": "未找到该股票代码或名称。"}
        try:
            res = service.forecast_symbol(resolved, horizon=int(payload.get("horizon", 5)))
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"分析失败：{type(exc).__name__}: {exc}"}
        if res.get("error"):
            err = res["error"]
            if "未找到" in err:
                err = "未找到该股票代码或名称。"
            elif "取数失败" in err or "无法获取" in err:
                err = "数据源取数失败，请检查 Baostock/AkShare。"
            return {"success": False, "error": err, "symbol": resolved}

        now = _dt.datetime.now()
        trading = now.weekday() < 5 and (9 * 60 + 30) <= (now.hour * 60 + now.minute) <= (15 * 60)
        note = "" if trading else "当前为非交易时间，使用最近一个交易日数据。"
        return {
            "success": True,
            "symbol": resolved,
            "name": res.get("name", ""),
            "latest_trade_date": (res.get("data") or {}).get("latest_data_date"),
            "note": note,
            "forecast": res,
        }

    @app.get("/api/stocks/search")
    def stocks_search(q: str = "", limit: int = 20) -> List[dict]:
        return service.search_stocks(q, limit=limit)

    @app.get("/api/watchlist")
    def get_watchlist() -> List[dict]:
        return service.watchlist()

    @app.post("/api/watchlist")
    def add_watchlist(payload: Dict[str, Any]) -> Dict[str, Any]:
        return service.add_to_watchlist(payload.get("symbol", ""))

    @app.delete("/api/watchlist")
    def del_watchlist(symbol: str = Query(...)) -> Dict[str, Any]:
        return service.remove_from_watchlist(symbol)

    @app.post("/api/screen/run")
    def screen_run(payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """运行选股（前端「运行选股」按钮调用）。等价于 aquant screen。"""
        import time

        payload = payload or {}
        strategy = payload.get("strategy", "short_strength")
        if strategy not in service.list_strategies():
            return {"success": False, "error": f"当前策略未实现: {strategy}"}
        try:
            t0 = time.time()
            res = service.screen_stocks(
                strategy=strategy,
                top_n=int(payload.get("top", payload.get("top_n", 20))),
                universe=payload.get("universe"),
                asof=payload.get("asof"),
                exclude_slow_blue_chip=bool(payload.get("exclude_large_cap", payload.get("exclude_slow_blue_chip", True))),
                use_cache=bool(payload.get("use_cache", True)),
            )
            if not res.get("picks"):
                return {"success": True, "strategy": res["strategy"], "strategy_name": res["strategy_name"],
                        "asof_date": res["asof"], "data_source": res["source"], "is_real_data": res["is_real_data"],
                        "elapsed_seconds": round(time.time() - t0, 2), "results": [],
                        "message": "没有筛选出符合条件的股票，请降低筛选条件或扩大股票池。",
                        "disclaimer": res["disclaimer"]}
            return {
                "success": True,
                "strategy": res["strategy"],
                "strategy_name": res["strategy_name"],
                "asof_date": res["asof"],
                "data_source": res["source"],
                "is_real_data": res["is_real_data"],
                "elapsed_seconds": round(time.time() - t0, 2),
                "results": res["picks"],
                "disclaimer": res["disclaimer"],
            }
        except Exception as exc:  # noqa: BLE001
            return {"success": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.get("/api/screen")
    def screen(strategy: str = "short_strength", top_n: int = 20, asof: Optional[str] = None,
               universe: Optional[str] = None, min_amount: float = 0.0,
               exclude_slow_blue_chip: bool = True, max_market_cap: float = 3000e8,
               use_cache: bool = True, timeout: int = 30) -> Dict[str, Any]:
        if strategy not in service.list_strategies():
            return {"error": "当前策略未实现", "strategy": strategy, "picks": []}
        return service.screen_stocks(strategy=strategy, top_n=top_n, asof=asof, universe=universe,
                                     min_amount=min_amount, exclude_slow_blue_chip=exclude_slow_blue_chip,
                                     max_market_cap=max_market_cap, use_cache=use_cache)

    return app


app = None
try:  # allow `uvicorn aqs.api.server:app`
    app = create_app()
except Exception:  # pragma: no cover
    pass
