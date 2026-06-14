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
        return {
            "status": "ok",
            "version": __version__,
            "source": service.DATA_CFG["source"],
            "n_symbols": len(service.DATA_CFG["symbols"]),
        }

    @app.get("/api/strategies")
    def strategies() -> Dict[str, str]:
        return service.list_strategies()

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

    @app.get("/api/screen")
    def screen(top_n: int = 8, asof: Optional[str] = None) -> Dict[str, Any]:
        return service.screen_stocks(top_n=top_n, asof=asof)

    return app


app = None
try:  # allow `uvicorn aqs.api.server:app`
    app = create_app()
except Exception:  # pragma: no cover
    pass
