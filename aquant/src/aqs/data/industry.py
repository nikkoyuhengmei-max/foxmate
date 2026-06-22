"""本地行业映射。

当数据源未返回行业字段时，用本地 CSV（``data/industry_map.csv``）补全行业。
查找顺序：
1. 环境变量 ``AQUANT_INDUSTRY_MAP`` 指定的路径
2. 当前工作目录下 ``data/industry_map.csv``
3. 包内自带的 ``aqs/data/industry_map.csv``
"""

from __future__ import annotations

import csv
import os
from functools import lru_cache
from typing import Dict, Optional

_PACKAGED = os.path.join(os.path.dirname(__file__), "industry_map.csv")


def _candidate_paths() -> list[str]:
    paths = []
    env = os.getenv("AQUANT_INDUSTRY_MAP")
    if env:
        paths.append(env)
    paths.append(os.path.join(os.getcwd(), "data", "industry_map.csv"))
    paths.append(_PACKAGED)
    return paths


@lru_cache(maxsize=1)
def load_industry_map() -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for path in _candidate_paths():
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    sym = (row.get("symbol") or "").strip()
                    ind = (row.get("industry") or "").strip()
                    if sym and ind:
                        mapping[sym] = ind
        except Exception:
            continue
    return mapping


def industry_of(symbol: str, default: str = "未分类") -> str:
    return load_industry_map().get(symbol, default)


def fill_missing(industry: Optional[str], symbol: str) -> str:
    """若行业为空/未分类，则用本地映射补全。"""
    if industry and industry not in ("", "未分类", "None", "nan"):
        return industry
    return industry_of(symbol)
