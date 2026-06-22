"""Robustness / anti-overfitting analysis.

Tools to stress-test a strategy beyond a single backtest run:
* walk-forward window generation (out-of-sample discipline),
* parameter-sensitivity grids,
* Monte-Carlo resampling of the daily return stream to gauge drawdown risk.
"""

from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


def walk_forward_windows(
    sessions: pd.DatetimeIndex,
    train: int = 252,
    test: int = 63,
    step: int = 63,
) -> List[Dict[str, pd.Timestamp]]:
    """Generate rolling train/test windows for walk-forward analysis."""
    windows = []
    n = len(sessions)
    start = 0
    while start + train + test <= n:
        windows.append(
            {
                "train_start": sessions[start],
                "train_end": sessions[start + train - 1],
                "test_start": sessions[start + train],
                "test_end": sessions[start + train + test - 1],
            }
        )
        start += step
    return windows


def parameter_sensitivity(
    run_fn: Callable[[dict], float],
    grid: Dict[str, Iterable],
) -> pd.DataFrame:
    """Evaluate ``run_fn`` over a parameter grid.

    ``run_fn`` receives a params dict and returns a scalar score (e.g. Sharpe).
    A strategy whose score collapses with tiny parameter changes is likely
    overfit.
    """
    import itertools

    keys = list(grid)
    rows = []
    for combo in itertools.product(*(list(grid[k]) for k in keys)):
        params = dict(zip(keys, combo))
        score = run_fn(params)
        rows.append({**params, "score": score})
    return pd.DataFrame(rows)


def monte_carlo_drawdown(
    returns: pd.Series,
    n_paths: int = 1000,
    seed: int = 0,
) -> Dict[str, float]:
    """Bootstrap the daily return series to estimate drawdown distribution."""
    r = returns.dropna().values
    if len(r) == 0:
        return {}
    rng = np.random.default_rng(seed)
    max_dds = np.empty(n_paths)
    final_rets = np.empty(n_paths)
    for i in range(n_paths):
        sample = rng.choice(r, size=len(r), replace=True)
        curve = np.cumprod(1 + sample)
        running_max = np.maximum.accumulate(curve)
        dd = curve / running_max - 1.0
        max_dds[i] = dd.min()
        final_rets[i] = curve[-1] - 1.0
    return {
        "mc_median_max_drawdown": float(np.median(max_dds)),
        "mc_p95_max_drawdown": float(np.percentile(max_dds, 5)),  # 5th pct = worst 95%
        "mc_median_return": float(np.median(final_rets)),
        "mc_p05_return": float(np.percentile(final_rets, 5)),
        "mc_prob_loss": float((final_rets < 0).mean()),
    }
