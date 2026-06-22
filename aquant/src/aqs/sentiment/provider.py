"""舆情数据提供方（可扩展接口）。

抽象 :class:`SentimentProvider`，内置：
- ``NullProvider``    无数据（默认；相关字段 N/A）
- ``CSVProvider``     从本地 CSV 导入舆情原始数据
- ``MockProvider``    示例舆情（**仅演示模式可用**，明确标注示例）
- 东方财富/雪球/同花顺等真实源以 stub 形式预留，``available()`` 返回 False，
  后续实现 ``fetch`` 即可接入，不写死抓取逻辑。
"""

from __future__ import annotations

import abc
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np


@dataclass
class SentimentRaw:
    """单只股票的舆情原始数据（由 provider 提供，引擎据此计算衍生分值）。"""

    symbol: str
    name: str = ""
    date: Optional[str] = None
    source: str = ""
    news_count_1d: float = float("nan")
    news_count_3d: float = float("nan")
    mention_count_1d: float = float("nan")
    mention_count_3d: float = float("nan")
    prev_mention_1d: float = float("nan")   # 用于计算关注度变化
    prev_mention_3d: float = float("nan")
    headlines: List[str] = field(default_factory=list)   # 新闻/讨论标题
    is_mock: bool = False


class SentimentProvider(abc.ABC):
    name = "base"
    is_mock = False

    @abc.abstractmethod
    def available(self) -> bool: ...

    @abc.abstractmethod
    def fetch(self, symbols: Sequence[str], names: Optional[Dict[str, str]] = None,
              asof: Optional[str] = None) -> Dict[str, SentimentRaw]: ...


class NullProvider(SentimentProvider):
    name = "none"

    def available(self) -> bool:
        return False

    def fetch(self, symbols, names=None, asof=None) -> Dict[str, SentimentRaw]:
        return {}


class CSVProvider(SentimentProvider):
    """从 CSV 读取舆情原始数据。

    CSV 列：symbol[,name,date,source,news_count_1d,news_count_3d,
    mention_count_1d,mention_count_3d,headlines]，headlines 用 ``|`` 分隔多条。
    """

    name = "csv"

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path or os.getenv("AQUANT_SENTIMENT_CSV", os.path.join("data", "sentiment.csv"))

    def available(self) -> bool:
        return bool(self.path and os.path.exists(self.path))

    def fetch(self, symbols, names=None, asof=None) -> Dict[str, SentimentRaw]:
        import csv

        out: Dict[str, SentimentRaw] = {}
        want = set(symbols)
        try:
            with open(self.path, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    sym = (r.get("symbol") or "").strip()
                    if not sym or (want and sym not in want):
                        continue
                    def num(k):
                        v = r.get(k)
                        try:
                            return float(v)
                        except (TypeError, ValueError):
                            return float("nan")
                    out[sym] = SentimentRaw(
                        symbol=sym, name=r.get("name", ""), date=r.get("date"),
                        source=r.get("source", "csv"),
                        news_count_1d=num("news_count_1d"), news_count_3d=num("news_count_3d"),
                        mention_count_1d=num("mention_count_1d"), mention_count_3d=num("mention_count_3d"),
                        prev_mention_1d=num("prev_mention_1d"), prev_mention_3d=num("prev_mention_3d"),
                        headlines=[h for h in (r.get("headlines", "") or "").split("|") if h],
                        is_mock=False,
                    )
        except Exception as exc:  # noqa: BLE001
            print(f"[sentiment] CSV 读取失败: {exc}")
        return out


class MockProvider(SentimentProvider):
    """示例舆情（仅演示模式）。确定性生成，便于演示，**非真实数据**。"""

    name = "mock"
    is_mock = True

    _POS = ["公司发布回购方案", "获大额订单中标", "机构密集调研", "新产品发布超预期", "资金流入明显"]
    _NEG = ["收到交易所问询函", "股东拟减持", "业绩下滑亏损", "涉及诉讼", "面临监管处罚"]
    _NEU = ["公司发布日常公告", "参加行业展会", "高管变动", "披露经营数据"]

    def available(self) -> bool:
        return True

    def fetch(self, symbols, names=None, asof=None) -> Dict[str, SentimentRaw]:
        out: Dict[str, SentimentRaw] = {}
        for sym in symbols:
            seed = abs(hash((sym, asof or ""))) % (2 ** 32)
            rng = np.random.default_rng(seed)
            news1 = int(rng.integers(0, 40))
            news3 = news1 + int(rng.integers(0, 80))
            men1 = int(rng.integers(0, 5000))
            men3 = men1 + int(rng.integers(0, 9000))
            prev1 = int(men1 * float(rng.uniform(0.5, 1.5)))
            pool = []
            pool += list(rng.choice(self._POS, size=int(rng.integers(0, 4)), replace=True))
            pool += list(rng.choice(self._NEG, size=int(rng.integers(0, 3)), replace=True))
            pool += list(rng.choice(self._NEU, size=int(rng.integers(0, 3)), replace=True))
            out[sym] = SentimentRaw(
                symbol=sym, name=(names or {}).get(sym, ""), date=asof, source="mock",
                news_count_1d=news1, news_count_3d=news3,
                mention_count_1d=men1, mention_count_3d=men3,
                prev_mention_1d=prev1, prev_mention_3d=int(men3 * float(rng.uniform(0.5, 1.5))),
                headlines=pool, is_mock=True,
            )
        return out


# 真实源 stub（预留，available=False；后续实现 fetch 即可接入）
class _StubProvider(SentimentProvider):
    def available(self) -> bool:
        return False

    def fetch(self, symbols, names=None, asof=None) -> Dict[str, SentimentRaw]:
        return {}


class EastmoneyGubaProvider(_StubProvider):
    name = "eastmoney_guba"


class XueqiuProvider(_StubProvider):
    name = "xueqiu"


class THSConceptProvider(_StubProvider):
    name = "ths"


def get_provider(source: str, demo_mode: bool = False) -> SentimentProvider:
    """按配置选择 provider。real 源不可用时返回 NullProvider（N/A），mock 仅演示模式。"""
    source = (source or "auto").lower()
    if source == "mock":
        return MockProvider() if demo_mode else NullProvider()
    if source == "csv":
        p = CSVProvider()
        return p if p.available() else NullProvider()
    if source == "none":
        return NullProvider()
    # auto: 优先 CSV -> 真实源(暂未实现) -> 演示模式回退 mock -> Null
    csv = CSVProvider()
    if csv.available():
        return csv
    for prov in (EastmoneyGubaProvider(), XueqiuProvider(), THSConceptProvider()):
        if prov.available():
            return prov
    if demo_mode:
        return MockProvider()
    return NullProvider()
