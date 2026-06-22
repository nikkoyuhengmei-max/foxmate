"""舆情 / 关注度因子子系统。

把市场关注度、新闻热度、社交讨论度转成量化评分，作为短线强势策略的**辅助因子**。

重要声明：
- 舆情只是辅助因子，**不能单独作为买入依据**；舆情热度不等于投资价值。
- 真实舆情数据源（东方财富股吧/雪球/同花顺/新闻/指数）以可扩展接口接入；
  未接入或抓取受限时，相关字段显示 N/A，并自动降低该因子权重。
- 示例(mock)舆情**仅在演示模式可用**，且会明确标注"示例舆情数据"，不得当作真实数据。
"""

from aqs.sentiment.keywords import RISK_KEYWORDS, POSITIVE_KEYWORDS, analyze_text
from aqs.sentiment.engine import SentimentEngine

__all__ = ["RISK_KEYWORDS", "POSITIVE_KEYWORDS", "analyze_text", "SentimentEngine"]
