"""本地数据缓存。

把一次取到的数据集（行情/基本面/基准/标的）存到本地，之后直接从本地读取，
**避免反复联网取数导致的限流/断连**。任何数据源（AkShare/Baostock/Wind/iFinD）
都可复用这一层。

实现上用 pickle 持久化整个 :class:`SampleDataset`，简单可靠、无额外依赖。
"""

from __future__ import annotations

import hashlib
import os
import pickle
from typing import Callable, Optional

from aqs.data.sample_data import SampleDataset


def cache_key(source: str, symbols, start: str, end: str, benchmark: str, extra: str = "") -> str:
    raw = f"{source}|{sorted(symbols)}|{start}|{end}|{benchmark}|{extra}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def dataset_path(cache_dir: str, key: str) -> str:
    return os.path.join(cache_dir, f"dataset_{key}.pkl")


def save_dataset(ds: SampleDataset, path: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as fh:
        pickle.dump(ds, fh, protocol=pickle.HIGHEST_PROTOCOL)


def load_dataset(path: str) -> SampleDataset:
    with open(path, "rb") as fh:
        return pickle.load(fh)


def cached_build(
    builder: Callable[[], SampleDataset],
    cache_dir: Optional[str],
    key: str,
    refresh: bool = False,
) -> SampleDataset:
    """有缓存且未要求刷新 -> 读本地；否则取数并写缓存。"""
    if not cache_dir:
        return builder()
    path = dataset_path(cache_dir, key)
    if os.path.exists(path) and not refresh:
        try:
            return load_dataset(path)
        except Exception:
            pass  # 缓存损坏则重新取
    ds = builder()
    try:
        save_dataset(ds, path)
    except Exception as exc:  # 写缓存失败不影响主流程
        print(f"[cache] 写入缓存失败（忽略）: {exc}")
    return ds
