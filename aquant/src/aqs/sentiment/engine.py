"""舆情引擎：取原始舆情 → 计算关注度/情绪衍生分值 → 缓存。

缓存目录 data/cache/sentiment/，避免每次刷新都重新抓取。
"""

from __future__ import annotations

import csv
import os
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from aqs.sentiment.keywords import analyze_text
from aqs.sentiment.provider import SentimentRaw, get_provider

_CACHE_DIR = os.path.join("data", "cache", "sentiment")


def _norm(values: Dict[str, float]) -> Dict[str, float]:
    arr = np.array([v for v in values.values() if v == v], dtype=float)  # 去 NaN
    if arr.size == 0:
        return {k: 0.0 for k in values}
    lo, hi = float(arr.min()), float(arr.max())
    span = hi - lo
    out = {}
    for k, v in values.items():
        out[k] = 0.0 if (v != v or span == 0) else (v - lo) / span
    return out


class SentimentEngine:
    def __init__(self, source: str = "auto", demo_mode: bool = False, cache_dir: str = _CACHE_DIR) -> None:
        self.source = source
        self.demo_mode = demo_mode
        self.cache_dir = cache_dir

    # ------------------------------------------------------------ public
    def get_sentiment(
        self,
        symbols: Sequence[str],
        names: Optional[Dict[str, str]] = None,
        asof: Optional[str] = None,
        use_cache: bool = True,
    ) -> Tuple[Dict[str, dict], dict]:
        """返回 (records, meta)。meta 含 source / is_mock / available。"""
        asof = asof or datetime.now().strftime("%Y-%m-%d")
        provider = get_provider(self.source, demo_mode=self.demo_mode)
        pname = provider.name

        # 缓存按 provider 命名空间隔离：mock 缓存绝不会被真实模式读取
        cached = self._load_cache(asof, pname) if use_cache else {}
        need = [s for s in symbols if s not in cached]
        raws: Dict[str, SentimentRaw] = {}
        if need and provider.available():
            try:
                raws = provider.fetch(need, names=names, asof=asof)
            except Exception as exc:  # noqa: BLE001
                print(f"[sentiment] 取数失败({provider.name}): {exc}")
                raws = {}

        fresh = self._derive(raws)
        records: Dict[str, dict] = {}
        for s in symbols:
            if s in fresh:
                records[s] = fresh[s]
            elif s in cached:
                records[s] = cached[s]
        # 重新计算 hot_rank（跨当前集合）
        self._rank(records)
        if fresh:
            self._save_cache(asof, pname, fresh)

        is_mock = provider.is_mock or any(r.get("is_mock") for r in records.values())
        meta = {"source": provider.name, "is_mock": bool(is_mock),
                "available": bool(records), "asof": asof,
                "disclaimer": "舆情仅为辅助参考，舆情热度不等于投资价值，不能单独作为买入依据。"}
        return records, meta

    # ----------------------------------------------------------- derive
    def _derive(self, raws: Dict[str, SentimentRaw]) -> Dict[str, dict]:
        if not raws:
            return {}
        recs: Dict[str, dict] = {}
        for sym, r in raws.items():
            kw = analyze_text(r.headlines)
            # 关注度变化
            if r.prev_mention_1d == r.prev_mention_1d and r.prev_mention_1d:
                chg1 = (r.mention_count_1d - r.prev_mention_1d) / (r.prev_mention_1d + 1e-9)
            elif r.mention_count_3d == r.mention_count_3d and r.mention_count_3d:
                chg1 = (r.mention_count_1d - r.mention_count_3d / 3.0) / (r.mention_count_3d / 3.0 + 1e-9)
            else:
                chg1 = float("nan")
            if r.prev_mention_3d == r.prev_mention_3d and r.prev_mention_3d:
                chg3 = (r.mention_count_3d - r.prev_mention_3d) / (r.prev_mention_3d + 1e-9)
            else:
                chg3 = float("nan")
            recs[sym] = {
                "symbol": sym, "name": r.name, "date": r.date, "source": r.source, "is_mock": r.is_mock,
                "news_count_1d": r.news_count_1d, "news_count_3d": r.news_count_3d,
                "mention_count_1d": r.mention_count_1d, "mention_count_3d": r.mention_count_3d,
                "attention_change_1d": round(chg1, 4) if chg1 == chg1 else None,
                "attention_change_3d": round(chg3, 4) if chg3 == chg3 else None,
                "summary": r.headlines[:5],
                **kw,
            }
        # attention_score：组件 min-max 归一后加权
        disc = _norm({s: recs[s]["mention_count_1d"] for s in recs})
        news = _norm({s: recs[s]["news_count_1d"] for s in recs})
        chg = _norm({s: (recs[s]["attention_change_1d"] or 0.0) for s in recs})
        riskp = _norm({s: recs[s]["risk_keyword_count"] for s in recs})
        for s in recs:
            pos = (recs[s]["sentiment_score"] + 1) / 2.0
            raw = 0.30 * disc[s] + 0.20 * news[s] + 0.25 * chg[s] + 0.15 * pos - 0.10 * riskp[s]
            recs[s]["attention_score"] = round(float(min(max(raw, 0.0), 1.0)) * 100, 1)
        return recs

    def _rank(self, records: Dict[str, dict]) -> None:
        ordered = sorted(records.values(), key=lambda r: r.get("attention_score", 0), reverse=True)
        for i, r in enumerate(ordered, 1):
            r["hot_rank"] = i

    # ------------------------------------------------------------ cache
    def _cache_path(self, asof: str, provider: str) -> str:
        return os.path.join(self.cache_dir, f"sentiment_{provider}_{asof}.csv")

    def _load_cache(self, asof: str, provider: str) -> Dict[str, dict]:
        if provider == "none":
            return {}
        path = self._cache_path(asof, provider)
        if not os.path.exists(path):
            return {}
        out: Dict[str, dict] = {}
        try:
            with open(path, encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    sym = r.get("symbol")
                    if not sym:
                        continue
                    def fnum(k):
                        try:
                            return float(r[k])
                        except (TypeError, ValueError, KeyError):
                            return float("nan")
                    out[sym] = {
                        "symbol": sym, "name": r.get("name", ""), "date": r.get("date"),
                        "source": r.get("source", ""), "is_mock": r.get("is_mock") == "True",
                        "news_count_1d": fnum("news_count_1d"), "news_count_3d": fnum("news_count_3d"),
                        "mention_count_1d": fnum("mention_count_1d"), "mention_count_3d": fnum("mention_count_3d"),
                        "attention_change_1d": fnum("attention_change_1d"),
                        "attention_change_3d": fnum("attention_change_3d"),
                        "sentiment_score": fnum("sentiment_score"),
                        "positive_ratio": fnum("positive_ratio"), "negative_ratio": fnum("negative_ratio"),
                        "risk_keyword_count": fnum("risk_keyword_count"),
                        "attention_score": fnum("attention_score"),
                        "risk_keywords": [x for x in (r.get("risk_keywords", "") or "").split("|") if x],
                        "positive_keywords": [x for x in (r.get("positive_keywords", "") or "").split("|") if x],
                        "summary": [x for x in (r.get("summary", "") or "").split("|") if x],
                    }
        except Exception:
            return {}
        return out

    def _save_cache(self, asof: str, provider: str, records: Dict[str, dict]) -> None:
        if provider == "none":
            return
        os.makedirs(self.cache_dir, exist_ok=True)
        path = self._cache_path(asof, provider)
        cols = ["symbol", "name", "date", "source", "is_mock", "news_count_1d", "news_count_3d",
                "mention_count_1d", "mention_count_3d", "attention_change_1d", "attention_change_3d",
                "sentiment_score", "positive_ratio", "negative_ratio", "risk_keyword_count",
                "attention_score", "risk_keywords", "positive_keywords", "summary", "updated_at"]
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=cols)
                w.writeheader()
                for r in records.values():
                    row = {c: r.get(c) for c in cols if c not in ("risk_keywords", "positive_keywords", "summary", "updated_at")}
                    row["risk_keywords"] = "|".join(r.get("risk_keywords", []))
                    row["positive_keywords"] = "|".join(r.get("positive_keywords", []))
                    row["summary"] = "|".join(r.get("summary", []))
                    row["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    w.writerow(row)
        except Exception as exc:  # noqa: BLE001
            print(f"[sentiment] 写缓存失败: {exc}")
