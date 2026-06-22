"""研究工具：选股器(Screener)等。

提供"结合多周期历史数据 + 量化指标 + （可选）集合竞价"快速筛选候选股的能力。
"""

from aqs.research.screener import Screener, ScreenConfig

__all__ = ["Screener", "ScreenConfig"]
