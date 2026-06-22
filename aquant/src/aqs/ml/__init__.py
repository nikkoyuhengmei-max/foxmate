"""Machine-learning / forecasting subsystem.

IMPORTANT DISCLAIMER (重要风险提示)
--------------------------------------------------------------------------
Stock prices are noisy and largely unpredictable. The models here estimate a
*probability* / *expected drift* from historical patterns; they are NOT a
guarantee of future performance. No model can reliably "predict" future prices.
Outputs must be combined with risk control and treated as one weak signal among
many. Past performance does not indicate future results. 模型预测仅供研究参考，
不构成任何投资建议，市场有风险，投资需谨慎。
"""

from aqs.ml.features import make_features
from aqs.ml.forecast import TrendForecaster, analyze_and_forecast

__all__ = ["make_features", "TrendForecaster", "analyze_and_forecast"]
