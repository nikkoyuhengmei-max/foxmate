"""Performance & attribution analytics."""

from aqs.performance.metrics import PerformanceReport, analyze
from aqs.performance.robustness import (
    monte_carlo_drawdown,
    parameter_sensitivity,
    walk_forward_windows,
)

__all__ = [
    "PerformanceReport",
    "analyze",
    "monte_carlo_drawdown",
    "parameter_sensitivity",
    "walk_forward_windows",
]
