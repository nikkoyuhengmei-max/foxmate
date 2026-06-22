"""Wind (万得) data-source adapter built on the WindPy API.

REQUIREMENTS / 使用前提
--------------------------------------------------------------------------
1. 必须在**安装并登录了 Wind 金融终端**的机器上运行（WindPy 通过本地终端取数）。
2. 安装 WindPy（随 Wind 终端附带的 Python 插件，或终端内的"修复/安装插件"）。
3. Wind 账号需开通对应权限（数据 API；实时行情 wsq / 分钟 wsi / tick wst 视需要）。
4. 账号登录在本地 Wind 终端完成，**代码里不需要也不应该保存账号密码**。

本适配器把 Wind 行情/复权/停牌/ST/基本面拉成 :class:`SampleDataset`，再交给
:class:`MarketDataManager` 使用，因此回测/风控/合规/仪表盘逻辑完全不变。

注意：本文件按 WindPy 公开 API 编写，但需要在你的 Wind 机器上实跑验证；不同账号的
字段权限不同，缺失字段会自动跳过并打印告警。如遇字段报错，请把报错贴给我，我按你的
权限调整字段清单。
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from aqs.data.calendar import TradingCalendar
from aqs.data.instruments import AssetType, Instrument, classify_board
from aqs.data.sample_data import SampleDataset


# Wind 字段 -> 系统内部列名
_BAR_FIELDS = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amt": "amount",          # 成交额
    "adjfactor": "adjfactor", # 复权因子
    "trade_status": "trade_status",  # 交易状态（交易/停牌）
}

_FUND_FIELDS = {
    "pe_ttm": "pe",
    "pb_lf": "pb",
    "roe_ttm2": "roe",
    "yoy_or": "revenue_yoy",      # 营收同比
    "yoynetprofit": "net_profit_yoy",  # 净利润同比
}


class WindDataSource:
    def __init__(self, auto_start: bool = True) -> None:
        try:
            from WindPy import w  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local install
            raise ImportError(
                "未找到 WindPy。请在安装并登录 Wind 金融终端的机器上安装 WindPy 后重试。"
            ) from exc
        self.w = w
        if auto_start and not w.isconnected():
            res = w.start()
            if getattr(res, "ErrorCode", 0) != 0:
                raise RuntimeError(f"WindPy 启动失败 ErrorCode={res.ErrorCode}. 请确认 Wind 终端已登录。")

    # ------------------------------------------------------------- helpers
    def _check(self, res, what: str):
        if getattr(res, "ErrorCode", 0) != 0:
            raise RuntimeError(f"Wind {what} 失败 ErrorCode={res.ErrorCode}: {getattr(res, 'Data', None)}")
        return res

    def _wsd_frame(self, code: str, fields: Sequence[str], start: str, end: str, options: str = "") -> pd.DataFrame:
        """单只标的、多字段的时间序列 -> DataFrame(index=日期, columns=字段)。"""
        res = self.w.wsd(code, ",".join(fields), start, end, options)
        if getattr(res, "ErrorCode", 0) != 0:
            raise RuntimeError(f"wsd {code} 失败 ErrorCode={res.ErrorCode}")
        idx = pd.DatetimeIndex([pd.Timestamp(t) for t in res.Times])
        data = np.array(res.Data, dtype="object").T  # rows=dates, cols=fields
        cols = [f.lower() for f in res.Fields]
        df = pd.DataFrame(data, index=idx, columns=cols)
        return df.apply(pd.to_numeric, errors="ignore")

    # --------------------------------------------------------------- public
    def trading_calendar(self, start: str, end: str) -> TradingCalendar:
        res = self._check(self.w.tdays(start, end, ""), "tdays")
        days = [pd.Timestamp(t) for t in res.Times]
        return TradingCalendar.from_index(pd.DatetimeIndex(days))

    def get_instruments(self, symbols: Sequence[str]) -> Dict[str, Instrument]:
        out: Dict[str, Instrument] = {}
        fields = "sec_name,ipo_date,industry_sw,riskwarning,delist_date"
        res = self.w.wss(list(symbols), fields, "industryType=1")
        if getattr(res, "ErrorCode", 0) != 0:
            # fall back to code-only metadata
            for s in symbols:
                out[s] = Instrument(symbol=s, board=classify_board(s))
            return out
        codes = res.Codes
        data = {f.lower(): res.Data[i] for i, f in enumerate(res.Fields)}
        for j, code in enumerate(codes):
            name = str(data.get("sec_name", [""] * len(codes))[j] or "")
            ipo = data.get("ipo_date", [None] * len(codes))[j]
            delist = data.get("delist_date", [None] * len(codes))[j]
            industry = str(data.get("industry_sw", ["未分类"] * len(codes))[j] or "未分类")
            rw = data.get("riskwarning", [""] * len(codes))[j]
            is_st = bool(rw) and str(rw) not in ("0", "否", "无", "None", "nan")
            out[code] = Instrument(
                symbol=code,
                name=name,
                asset_type=AssetType.STOCK,
                board=classify_board(code),
                industry=industry,
                list_date=str(pd.Timestamp(ipo).date()) if ipo else None,
                delist_date=str(pd.Timestamp(delist).date()) if delist and not pd.isna(delist) else None,
                is_st=is_st,
            )
        return out

    def get_bars(self, symbols: Sequence[str], start: str, end: str) -> tuple[Dict[str, pd.DataFrame], Dict[str, pd.Series]]:
        """日线行情 + 复权因子。返回 (bars, adj_factors)。"""
        bars: Dict[str, pd.DataFrame] = {}
        adj: Dict[str, pd.Series] = {}
        wind_fields = list(_BAR_FIELDS.keys())
        for sym in symbols:
            try:
                raw = self._wsd_frame(sym, wind_fields, start, end, "PriceAdj=U")  # 不复权原始价
            except RuntimeError as exc:
                print(f"[Wind] 跳过 {sym}: {exc}")
                continue
            df = pd.DataFrame(index=raw.index)
            for wf, col in _BAR_FIELDS.items():
                if wf in raw.columns and col not in ("adjfactor", "trade_status"):
                    df[col] = pd.to_numeric(raw[wf], errors="coerce")
            # 停牌：trade_status 非"交易" 或 成交量为 0/缺失
            status = raw["trade_status"] if "trade_status" in raw.columns else None
            suspended = pd.Series(False, index=raw.index)
            if status is not None:
                suspended = ~status.astype(str).str.contains("交易", na=False)
            if "volume" in df.columns:
                suspended = suspended | df["volume"].fillna(0).le(0)
            df["suspended"] = suspended.fillna(True)
            bars[sym] = df
            if "adjfactor" in raw.columns:
                adj[sym] = pd.to_numeric(raw["adjfactor"], errors="coerce").ffill().fillna(1.0)
        return bars, adj

    def get_fundamentals(self, symbols: Sequence[str], start: str, end: str, sample: str = "ME") -> pd.DataFrame:
        """PIT 基本面：按 Wind 日度数值（已是当日可知）月末抽样。

        Wind 的 pe_ttm/pb_lf 等为每日计算的时点值；报告类指标（roe、同比）在 Wind 日序中
        只在披露后才更新，因此用"采样日"作为 disclosure_date 即满足 PIT（不偷看未来）。
        """
        rows = []
        wind_fields = list(_FUND_FIELDS.keys())
        for sym in symbols:
            try:
                raw = self._wsd_frame(sym, wind_fields, start, end, "")
            except RuntimeError as exc:
                print(f"[Wind] 基本面跳过 {sym}: {exc}")
                continue
            raw = raw.rename(columns={k: v for k, v in _FUND_FIELDS.items()})
            monthly = raw.resample(sample).last().dropna(how="all")
            for ts, r in monthly.iterrows():
                rows.append(
                    {
                        "symbol": sym,
                        "report_period": ts,       # 采样日近似报告期
                        "disclosure_date": ts,     # PIT：以采样日为可知日期
                        **{c: (float(r[c]) if c in r and pd.notna(r[c]) else np.nan) for c in _FUND_FIELDS.values()},
                    }
                )
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows).sort_values(["symbol", "disclosure_date"]).reset_index(drop=True)

    def build_dataset(
        self,
        symbols: Sequence[str],
        start: str,
        end: str,
        benchmark: str = "000300.SH",
        with_fundamentals: bool = True,
    ) -> SampleDataset:
        cal = self.trading_calendar(start, end)
        instruments = self.get_instruments(symbols)
        bars, adj = self.get_bars(symbols, start, end)

        bench_raw = self._wsd_frame(benchmark, ["open", "high", "low", "close", "volume", "amt"], start, end, "")
        bench = bench_raw.rename(columns={"amt": "amount"})
        bench["suspended"] = False

        fundamentals = (
            self.get_fundamentals(symbols, start, end) if with_fundamentals else pd.DataFrame()
        )
        return SampleDataset(
            instruments=instruments,
            bars=bars,
            benchmark=bench,
            benchmark_symbol=benchmark,
            adj_factors=adj,
            fundamentals=fundamentals,
            calendar=cal,
        )

    # ------------------------------------------------- realtime (实验性)
    def subscribe_realtime(self, symbols: Sequence[str], callback, fields: str = "rt_last,rt_vol,rt_amt"):
        """订阅实时行情（需 wsq 权限）。callback(WindData) 在每次推送时被调用。

        说明：实时下单/盘中策略应在本机长驻进程中运行，并接入 PaperTrader / 实盘网关。
        """
        return self.w.wsq(list(symbols), fields, func=callback)
