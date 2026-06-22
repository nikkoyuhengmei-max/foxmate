"""舆情关键词识别：风险词 / 催化词，以及文本情绪分析。"""

from __future__ import annotations

from typing import Dict, List, Sequence

# 负面 / 风险关键词
RISK_KEYWORDS = [
    "监管", "立案", "问询函", "减持", "亏损", "暴雷", "退市", "ST", "*ST",
    "跌停", "诉讼", "造假", "处罚", "业绩下滑", "商誉减值", "违规", "调查",
    "停牌", "质押爆仓", "债务违约", "财务造假",
]

# 正面 / 催化关键词
POSITIVE_KEYWORDS = [
    "涨停", "突破", "订单", "业绩增长", "回购", "增持", "中标", "政策支持",
    "新产品", "并购", "机构调研", "资金流入", "超预期", "新高", "扩产",
    "签约", "战略合作", "提价", "龙头",
]


def analyze_text(texts: Sequence[str]) -> Dict[str, object]:
    """对一组文本（新闻标题/讨论）做关键词与情绪分析。

    返回 sentiment_score(-1..1)、正/负面比例、命中的风险/正面关键词与计数。
    """
    blob = " ".join(t for t in texts if t)
    risk_hits = sorted({k for k in RISK_KEYWORDS if k in blob})
    pos_hits = sorted({k for k in POSITIVE_KEYWORDS if k in blob})
    # 计数：按出现次数累计（更能反映强度）
    risk_count = sum(blob.count(k) for k in RISK_KEYWORDS)
    pos_count = sum(blob.count(k) for k in POSITIVE_KEYWORDS)
    total = risk_count + pos_count
    if total == 0:
        sentiment = 0.0
        positive_ratio = negative_ratio = 0.0
    else:
        sentiment = (pos_count - risk_count) / total
        positive_ratio = pos_count / total
        negative_ratio = risk_count / total
    return {
        "sentiment_score": round(sentiment, 4),
        "positive_ratio": round(positive_ratio, 4),
        "negative_ratio": round(negative_ratio, 4),
        "risk_keyword_count": int(risk_count),
        "positive_keyword_count": int(pos_count),
        "risk_keywords": risk_hits,
        "positive_keywords": pos_hits,
    }
