"""Performance metrics and reporting.

Computes the standard quant performance suite from an equity curve and a
benchmark: cumulative / annualised return, volatility, Sharpe, Sortino, Calmar,
max drawdown, win rate, profit factor, turnover, alpha/beta, information ratio,
plus monthly / yearly return tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd


def _to_returns(equity: pd.Series) -> pd.Series:
    return equity.pct_change().dropna()


def max_drawdown(equity: pd.Series) -> tuple[float, Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    if len(equity) == 0:
        return 0.0, None, None
    running_max = equity.cummax()
    dd = equity / running_max - 1.0
    trough = dd.idxmin()
    mdd = float(dd.min())
    peak = equity.loc[:trough].idxmax() if trough is not None else None
    return mdd, peak, trough


def drawdown_series(equity: pd.Series) -> pd.Series:
    if len(equity) == 0:
        return equity
    return equity / equity.cummax() - 1.0


@dataclass
class PerformanceReport:
    metrics: Dict[str, float]
    monthly_returns: pd.DataFrame
    yearly_returns: pd.Series
    drawdown: pd.Series
    equity_curve: pd.Series
    benchmark_curve: pd.Series

    def summary_text(self) -> str:
        m = self.metrics
        lines = [
            "================ 绩效报告 Performance Report ================",
            f"累计收益 Total Return       : {m['total_return']:.2%}",
            f"年化收益 Annual Return      : {m['annual_return']:.2%}",
            f"基准累计收益 Benchmark       : {m['benchmark_return']:.2%}",
            f"超额收益 Excess (Alpha cum) : {m['excess_return']:.2%}",
            f"年化波动 Volatility         : {m['volatility']:.2%}",
            f"夏普比率 Sharpe             : {m['sharpe']:.2f}",
            f"索提诺 Sortino              : {m['sortino']:.2f}",
            f"卡玛 Calmar                 : {m['calmar']:.2f}",
            f"最大回撤 Max Drawdown       : {m['max_drawdown']:.2%}",
            f"胜率 Win Rate (daily)       : {m['win_rate']:.2%}",
            f"盈亏比 Profit Factor        : {m['profit_factor']:.2f}",
            f"Alpha (annual)             : {m['alpha']:.2%}",
            f"Beta                       : {m['beta']:.2f}",
            f"信息比率 Information Ratio  : {m['information_ratio']:.2f}",
            f"最大连续亏损 Max Loss Streak: {int(m['max_loss_streak'])} 天",
            "============================================================",
        ]
        return "\n".join(lines)


def analyze(
    equity: pd.Series,
    benchmark: Optional[pd.Series] = None,
    rf: float = 0.0,
    periods: int = 252,
) -> PerformanceReport:
    equity = equity.dropna()
    rets = _to_returns(equity)
    n = len(rets)

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1) if len(equity) > 1 else 0.0
    years = n / periods if n else 0.0
    annual_return = float((1 + total_return) ** (1 / years) - 1) if years > 0 else 0.0
    vol = float(rets.std(ddof=0) * np.sqrt(periods)) if n else 0.0

    rf_daily = rf / periods
    excess = rets - rf_daily
    sharpe = float(excess.mean() / (rets.std(ddof=0) + 1e-12) * np.sqrt(periods)) if n else 0.0
    downside = rets[rets < 0]
    sortino = float(excess.mean() / (downside.std(ddof=0) + 1e-12) * np.sqrt(periods)) if len(downside) else 0.0

    mdd, _, _ = max_drawdown(equity)
    calmar = float(annual_return / abs(mdd)) if mdd < 0 else 0.0

    win_rate = float((rets > 0).mean()) if n else 0.0
    gains = rets[rets > 0].sum()
    losses = -rets[rets < 0].sum()
    profit_factor = float(gains / (losses + 1e-12)) if losses else float("inf") if gains else 0.0

    # alpha / beta / information ratio vs benchmark
    alpha = beta = info_ratio = bench_total = excess_return = 0.0
    bench_curve = pd.Series(dtype=float)
    if benchmark is not None and len(benchmark) > 1:
        bench = benchmark.reindex(equity.index).ffill().dropna()
        bench_curve = bench
        bret = bench.pct_change().dropna()
        aligned = pd.concat([rets, bret], axis=1, keys=["p", "b"]).dropna()
        if len(aligned) > 1 and aligned["b"].std(ddof=0) > 0:
            cov = np.cov(aligned["p"], aligned["b"])[0, 1]
            beta = float(cov / np.var(aligned["b"]))
            alpha = float((aligned["p"].mean() - beta * aligned["b"].mean()) * periods)
            active = aligned["p"] - aligned["b"]
            info_ratio = float(active.mean() / (active.std(ddof=0) + 1e-12) * np.sqrt(periods))
        bench_total = float(bench.iloc[-1] / bench.iloc[0] - 1)
        excess_return = total_return - bench_total

    metrics = {
        "total_return": total_return,
        "annual_return": annual_return,
        "benchmark_return": bench_total,
        "excess_return": excess_return,
        "volatility": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "max_drawdown": mdd,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "alpha": alpha,
        "beta": beta,
        "information_ratio": info_ratio,
        "max_loss_streak": _max_loss_streak(rets),
        "n_days": float(n),
    }

    return PerformanceReport(
        metrics=metrics,
        monthly_returns=_monthly_table(rets),
        yearly_returns=_yearly_returns(rets),
        drawdown=drawdown_series(equity),
        equity_curve=equity,
        benchmark_curve=bench_curve,
    )


def _max_loss_streak(rets: pd.Series) -> int:
    streak = best = 0
    for r in rets:
        if r < 0:
            streak += 1
            best = max(best, streak)
        else:
            streak = 0
    return best


def _monthly_table(rets: pd.Series) -> pd.DataFrame:
    if not len(rets):
        return pd.DataFrame()
    monthly = (1 + rets).resample("ME").prod() - 1
    df = monthly.to_frame("ret")
    df["year"] = df.index.year
    df["month"] = df.index.month
    table = df.pivot(index="year", columns="month", values="ret")
    table.columns = [f"{m:02d}月" for m in table.columns]
    return table


def _yearly_returns(rets: pd.Series) -> pd.Series:
    if not len(rets):
        return pd.Series(dtype=float)
    yearly = (1 + rets).resample("YE").prod() - 1
    yearly.index = yearly.index.year
    return yearly
