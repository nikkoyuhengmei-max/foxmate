"""同花顺 iFinD 数据源适配器（基于 iFinDPy SDK）。

REQUIREMENTS / 使用前提
--------------------------------------------------------------------------
1. 必须是 **同花顺 iFinD（专业数据终端）** 账号，并开通 **数据 API 权限**
   （普通免费版同花顺没有官方 Python 数据接口，无法用本适配器）。
2. 安装 iFinD 数据接口 SDK（iFinDPy）。
3. 用账号密码登录：建议把账号放到环境变量 `THS_USERNAME` / `THS_PASSWORD`，
   不要硬编码到代码里。

本适配器把 iFinD 行情/复权/停牌/ST/基本面拉成 :class:`SampleDataset`，再交给
:class:`MarketDataManager` 使用，回测/风控/合规/仪表盘逻辑完全不变。

注意：iFinD 的指标代码（indicator）与参数串在不同版本/不同权限下可能略有差异。
本文件按 iFinDPy 公开用法编写，指标清单集中在文件顶部、可配置；首次在你的机器上跑
若有字段报错，把报错贴给我，我按你的权限调整指标名。
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from aqs.data.calendar import TradingCalendar
from aqs.data.instruments import AssetType, Instrument, classify_board
from aqs.data.sample_data import SampleDataset


# ---- 指标映射（如与你的权限/版本不符，改这里即可） ----
# 历史行情指标 -> 系统内部列名
_HQ_INDICATORS = {
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "volume": "volume",
    "amount": "amount",
}
# 历史行情参数串（CPS:1 不复权；如需后复权改为对应参数）
_HQ_PARAMS = "Interval:D,CPS:1,baseDate:1900-01-01,Fill:Original"

# 基础数据指标 -> 内部字段
_BASIC_INDICATORS = {
    "ths_stock_short_name_stock": "name",
    "ths_the_sw_industry_stock": "industry",
    "ths_ipo_date_stock": "list_date",
    "ths_delist_date_stock": "delist_date",
    "ths_st_stock": "is_st",
}
# 复权因子指标（如无权限将自动跳过，按不复权处理）
_ADJ_INDICATOR = "ths_adjust_factor_stock"
# 停牌状态指标
_STATUS_INDICATOR = "ths_trade_status_stock"

# 基本面（日期序列）指标 -> 内部字段
_FUND_INDICATORS = {
    "ths_pe_ttm_stock": "pe",
    "ths_pb_stock": "pb",
    "ths_roe_ttm_stock": "roe",
    "ths_or_yoy_stock": "revenue_yoy",
    "ths_np_yoy_stock": "net_profit_yoy",
}


class THSDataSource:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None) -> None:
        try:
            import iFinDPy as ths  # type: ignore
        except Exception as exc:  # pragma: no cover - depends on local install
            raise ImportError(
                "未找到 iFinDPy。请安装同花顺 iFinD 数据接口 SDK 后重试（需 iFinD 专业版 + 数据 API 权限）。"
            ) from exc
        self.ths = ths
        user = username or os.getenv("THS_USERNAME")
        pwd = password or os.getenv("THS_PASSWORD")
        if not user or not pwd:
            raise ValueError("缺少 iFinD 账号。请设置环境变量 THS_USERNAME / THS_PASSWORD，或传入 username/password。")
        code = ths.THS_iFinDLogin(user, pwd)
        # 0 成功；-201 表示已登录，亦视为成功
        if code not in (0, -201):
            raise RuntimeError(f"iFinD 登录失败 code={code}。请检查账号/密码与 API 权限。")

    # ------------------------------------------------------------- helpers
    def _to_df(self, result) -> pd.DataFrame:
        """把 iFinD 返回结果转成 DataFrame（兼容 .data 为 DataFrame 或需转换）。"""
        if getattr(result, "errorcode", 0) not in (0, None):
            raise RuntimeError(f"iFinD errorcode={result.errorcode}: {getattr(result, 'errmsg', '')}")
        data = getattr(result, "data", None)
        if isinstance(data, pd.DataFrame):
            return data
        # 退回到官方转换函数
        try:
            return self.ths.THS_Trans2DataFrame(result)
        except Exception:
            return pd.DataFrame(data if data is not None else [])

    # --------------------------------------------------------------- public
    def trading_calendar(self, start: str, end: str) -> TradingCalendar:
        try:
            res = self.ths.THS_DateQuery("SSE", "dateType:0,period:D,dateFormat:0", start, end)
            df = self._to_df(res)
            col = "time" if "time" in df.columns else df.columns[-1]
            days = pd.to_datetime(df[col]) if len(df) else pd.DatetimeIndex([])
            if len(days):
                return TradingCalendar.from_index(pd.DatetimeIndex(days))
        except Exception as exc:
            print(f"[THS] 交易日历获取失败，回退到工作日历: {exc}")
        return TradingCalendar()

    def get_bars(self, symbols: Sequence[str], start: str, end: str) -> tuple[Dict[str, pd.DataFrame], Dict[str, pd.Series]]:
        bars: Dict[str, pd.DataFrame] = {}
        adj: Dict[str, pd.Series] = {}
        inds = ";".join(_HQ_INDICATORS.keys())
        for sym in symbols:
            try:
                res = self.ths.THS_HistoryQuotes(sym, inds, _HQ_PARAMS, start, end)
                df = self._to_df(res)
            except Exception as exc:
                print(f"[THS] 行情跳过 {sym}: {exc}")
                continue
            if df.empty:
                continue
            tcol = "time" if "time" in df.columns else df.columns[0]
            df = df.copy()
            df.index = pd.to_datetime(df[tcol])
            out = pd.DataFrame(index=df.index)
            for ind, col in _HQ_INDICATORS.items():
                if ind in df.columns:
                    out[col] = pd.to_numeric(df[ind], errors="coerce")
            out["suspended"] = out.get("volume", pd.Series(index=out.index)).fillna(0).le(0)
            bars[sym] = out
            adj[sym] = self._get_adjfactor(sym, start, end, out.index)
        return bars, adj

    def _get_adjfactor(self, sym: str, start: str, end: str, index: pd.DatetimeIndex) -> pd.Series:
        try:
            res = self.ths.THS_DateSerial(sym, _ADJ_INDICATOR, "", "Days:Tradedays,Fill:Previous,Interval:D", start, end)
            df = self._to_df(res)
            if not df.empty:
                tcol = "time" if "time" in df.columns else df.columns[0]
                s = pd.Series(pd.to_numeric(df.iloc[:, -1], errors="coerce").values,
                              index=pd.to_datetime(df[tcol]))
                return s.reindex(index).ffill().fillna(1.0)
        except Exception as exc:
            print(f"[THS] 复权因子缺失 {sym}（按不复权处理）: {exc}")
        return pd.Series(1.0, index=index)

    def get_instruments(self, symbols: Sequence[str]) -> Dict[str, Instrument]:
        out: Dict[str, Instrument] = {}
        inds = ";".join(_BASIC_INDICATORS.keys())
        for sym in symbols:
            meta = {}
            try:
                res = self.ths.THS_BasicData(sym, inds, ";" * (len(_BASIC_INDICATORS) - 1))
                df = self._to_df(res)
                if not df.empty:
                    row = df.iloc[0]
                    for ind, field in _BASIC_INDICATORS.items():
                        if ind in df.columns:
                            meta[field] = row[ind]
            except Exception as exc:
                print(f"[THS] 基础数据缺失 {sym}: {exc}")
            st_raw = meta.get("is_st")
            is_st = bool(st_raw) and str(st_raw) not in ("0", "否", "无", "None", "nan", "")
            delist = meta.get("delist_date")
            out[sym] = Instrument(
                symbol=sym,
                name=str(meta.get("name", "") or ""),
                asset_type=AssetType.STOCK,
                board=classify_board(sym),
                industry=str(meta.get("industry", "未分类") or "未分类"),
                list_date=str(meta["list_date"]) if meta.get("list_date") else None,
                delist_date=str(delist) if delist and str(delist) not in ("", "nan", "None") else None,
                is_st=is_st,
            )
        return out

    def get_fundamentals(self, symbols: Sequence[str], start: str, end: str) -> pd.DataFrame:
        rows = []
        inds = ";".join(_FUND_INDICATORS.keys())
        for sym in symbols:
            try:
                res = self.ths.THS_DateSerial(sym, inds, "", "Days:Tradedays,Fill:Previous,Interval:M", start, end)
                df = self._to_df(res)
            except Exception as exc:
                print(f"[THS] 基本面跳过 {sym}: {exc}")
                continue
            if df.empty:
                continue
            tcol = "time" if "time" in df.columns else df.columns[0]
            df = df.copy()
            df.index = pd.to_datetime(df[tcol])
            ren = {ind: field for ind, field in _FUND_INDICATORS.items() if ind in df.columns}
            df = df.rename(columns=ren)
            for ts, r in df.iterrows():
                rows.append(
                    {
                        "symbol": sym,
                        "report_period": ts,
                        "disclosure_date": ts,  # PIT：以可知日期为准
                        **{f: (float(r[f]) if f in r and pd.notna(r[f]) else np.nan) for f in _FUND_INDICATORS.values()},
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

        bench_bars, _ = self.get_bars([benchmark], start, end)
        bench = bench_bars.get(benchmark, pd.DataFrame())

        fundamentals = self.get_fundamentals(symbols, start, end) if with_fundamentals else pd.DataFrame()
        return SampleDataset(
            instruments=instruments,
            bars=bars,
            benchmark=bench,
            benchmark_symbol=benchmark,
            adj_factors=adj,
            fundamentals=fundamentals,
            calendar=cal,
        )

    def get_call_auction(self, symbols: Sequence[str]) -> Dict[str, Dict[str, float]]:
        """获取开盘集合竞价快照，供选股器使用（实验性，需实时/竞价权限）。

        返回 {symbol: {"gap": 竞价相对昨收涨跌幅, "auction_vol_ratio": 竞价量比}}。
        说明：不同 iFinD 版本的实时/竞价指标名可能不同（如 open / preClose / 竞价量 等），
        若字段报错把报错发我，我据你的权限调整。
        """
        out: Dict[str, Dict[str, float]] = {}
        for sym in symbols:
            try:
                res = self.ths.THS_RealtimeQuotes(sym, "open,preClose,openVolume", "")
                df = self._to_df(res)
                if df.empty:
                    continue
                r = df.iloc[0]
                op = float(r.get("open", np.nan))
                prev = float(r.get("preClose", np.nan))
                openvol = float(r.get("openVolume", np.nan))
                gap = (op / prev - 1.0) if prev else np.nan
                out[sym] = {"gap": gap, "auction_vol_ratio": openvol}
            except Exception as exc:
                print(f"[THS] 竞价快照跳过 {sym}: {exc}")
        return out

    def logout(self) -> None:
        try:
            self.ths.THS_iFinDLogout()
        except Exception:
            pass
