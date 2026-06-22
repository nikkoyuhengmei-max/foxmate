"""Command-line interface for AQuant.

Examples
--------
    aquant strategies                       # list strategy templates
    aquant quality                          # data-quality report
    aquant backtest --strategy multi_factor
    aquant paper --strategy double_ma
    aquant forecast --symbol 600519.SH
    aquant serve                            # launch local web dashboard
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from aqs import __version__, service


def _print_metrics(metrics: dict) -> None:
    order = [
        ("total_return", "累计收益", "pct"),
        ("annual_return", "年化收益", "pct"),
        ("benchmark_return", "基准收益", "pct"),
        ("excess_return", "超额收益", "pct"),
        ("volatility", "年化波动", "pct"),
        ("sharpe", "夏普", "num"),
        ("sortino", "索提诺", "num"),
        ("calmar", "卡玛", "num"),
        ("max_drawdown", "最大回撤", "pct"),
        ("win_rate", "胜率", "pct"),
        ("alpha", "Alpha(年)", "pct"),
        ("beta", "Beta", "num"),
        ("information_ratio", "信息比率", "num"),
    ]
    for key, label, kind in order:
        if key in metrics:
            v = metrics[key]
            sv = f"{v*100:.2f}%" if kind == "pct" else f"{v:.2f}"
            print(f"  {label:<10}: {sv}")


def cmd_strategies(_) -> int:
    cat = service.strategy_catalog()
    print("核心策略 (首页默认):")
    for e in cat["core"]:
        print(f"  {e['key']:<16} {e['name']}  [{e['horizon']}]")
    print("\n高级 / 实验策略:")
    for e in cat["advanced"]:
        print(f"  {e['key']:<16} {e['name']}")
    print(f"\n默认策略: {cat['default']}")
    return 0


def cmd_quality(_) -> int:
    rows = service.data_quality()
    print(f"{'symbol':<12}{'rows':>6}{'nan':>6}{'dup':>5}{'invalid':>9}{'ok':>5}")
    for r in rows:
        print(f"{r['symbol']:<12}{r['rows']:>6}{r['nan_rows']:>6}{r['duplicates']:>5}{r['invalid_ohlc']:>9}{str(r['ok']):>5}")
    return 0


def cmd_backtest(args) -> int:
    params = json.loads(args.params) if args.params else None
    res = service.run_backtest(
        strategy=args.strategy, params=params, start=args.start, end=args.end,
        fill_mode=args.fill, rebalance=getattr(args, "rebalance", None),
        max_position=getattr(args, "max_position", None), save=getattr(args, "save", False),
    )
    print(f"\n策略: {res['strategy_name']} ({res['strategy']})  数据版本: {res['data_version']}")
    print("-" * 50)
    _print_metrics(res["metrics"])
    print("-" * 50)
    rr = res["risk_review"]; co = res["compliance"]
    print(f"  成交笔数    : {res['n_trades']}  (订单 {res['n_orders']})")
    print(f"  换手率      : {rr.get('turnover', 0):.2f}")
    print(f"  交易成本    : {rr.get('total_cost', 0):,.0f}")
    print(f"  风控停机    : {rr.get('halted')}")
    print(f"  撤单比例    : {co.get('cancel_ratio', 0):.2%}  高频认定: {co.get('hft_flagged')}")
    print(f"  审计链有效  : {co.get('audit_valid')}  审计事件: {co.get('audit_events')}")
    if res.get("monte_carlo"):
        mc = res["monte_carlo"]
        print(f"  MC中位回撤  : {mc.get('mc_median_max_drawdown', 0):.2%}  亏损概率: {mc.get('mc_prob_loss', 0):.2%}")
    if res.get("saved"):
        print(f"  已导出      : {res['saved'].get('csv')} , {res['saved'].get('html')}")
    if args.json:
        print("\n" + json.dumps(res["metrics"], ensure_ascii=False, indent=2))
    return 0


def cmd_paper(args) -> int:
    params = json.loads(args.params) if args.params else None
    res = service.run_paper(strategy=args.strategy, params=params, start=args.start, end=args.end)
    print(f"\n模拟交易 (paper): {res['strategy']}")
    print("-" * 50)
    _print_metrics(res["metrics"])
    print(f"  成交笔数    : {res['n_trades']}")
    print(f"  合规摘要    : {json.dumps(res['compliance'], ensure_ascii=False)}")
    return 0


def cmd_screen(args) -> int:
    strat = getattr(args, "strategy", "short_strength")
    if strat not in service.list_strategies():
        print(f"当前策略未实现: {strat}。可用: {', '.join(service.list_strategies())}", file=sys.stderr)
        return 1
    import time as _t
    t0 = _t.time()
    res = service.screen_stocks(
        strategy=strat,
        top_n=args.top, asof=args.asof, min_amount=getattr(args, "min_amount", 0.0),
        exclude_st=getattr(args, "exclude_st", True),
        exclude_slow_blue_chip=getattr(args, "exclude_slow_blue_chip", True),
        max_market_cap=getattr(args, "max_market_cap", 3000e8),
        use_cache=getattr(args, "use_cache", True),
        use_sentiment=getattr(args, "use_sentiment", False),
        save=getattr(args, "save", False),
    )
    flag = "真实数据" if res.get("is_real_data") else "示例数据(回退)"
    if res.get("error"):
        print(f"\n选股失败: {res['error']}")
        if res.get("diagnostics"):
            print("诊断:", res["diagnostics"])
        return 1
    print(f"\n【{res.get('strategy_name')}】Top {res['top_n']} (asof={res['asof']}, 数据源={res.get('source')}/{flag}):")
    print("-" * 110)
    predictive = strat == "predictive_ranking"
    if predictive:
        print(f"{'#':<3}{'代码':<11}{'名称':<9}{'最新价':>9}{'3日':>6}{'5日':>6}{'10日':>6}{'RSI':>5}{'量比':>6}{'5日↑':>6}{'综合':>6}  {'信号':<7}{'原因'}")
        for p in res["picks"]:
            print(f"{p.get('rank',''):<3}{p.get('symbol',''):<11}{str(p.get('name','')):<9}{p.get('close',0):>9.2f}"
                  f"{(p.get('ret_3') or 0)*100:>5.1f}%{(p.get('ret_5') or 0)*100:>5.1f}%{(p.get('ret_10') or 0)*100:>5.1f}%"
                  f"{p.get('rsi',0):>5.0f}{(p.get('vol_ratio') or 0):>5.1f}x{(p.get('prob_up_5d') or 0)*100:>5.0f}%"
                  f"{(p.get('final_score') or 0):>6.1f}  {str(p.get('signal','')):<7}{str(p.get('reason',''))}")
    else:
        print(f"{'#':<3}{'代码':<11}{'名称':<10}{'行业':<7}{'最新价':>8}{'3日':>6}{'5日':>6}{'10日':>6}{'量比':>6}{'RSI':>5}{'评分':>7}  {'信号':<8}{'原因'}")
        for p in res["picks"]:
            bo = "▲" if p.get("breakout_20d") else " "
            print(f"{p.get('rank',''):<3}{p.get('symbol',''):<11}{str(p.get('name','')):<10}{str(p.get('industry','')):<7}"
                  f"{p.get('close',0):>8.2f}{(p.get('ret_3d') or 0)*100:>5.1f}%{(p.get('ret_5d') or 0)*100:>5.1f}%"
                  f"{(p.get('ret_10d') or 0)*100:>5.1f}%{(p.get('amount_ratio') or 0):>5.1f}x{p.get('rsi',0):>5.0f}"
                  f"{p.get('score',0):>7.2f}  {str(p.get('signal','')):<8}{bo}{str(p.get('reason',''))}")
    print("-" * 110)
    if not res["picks"]:
        print("没有筛选出符合条件的股票，请降低筛选条件或扩大股票池。")
    if res.get("saved"):
        print(f"已导出: {res['saved']}")
    print(f"选股完成，用时 {_t.time()-t0:.1f} 秒")
    print(res["disclaimer"])
    return 0


def cmd_universe(args) -> int:
    name = getattr(args, "universe", None) or "hs300"
    src = getattr(args, "source", None)
    info = service.load_universe(name, source=src, refresh=getattr(args, "refresh", False))
    print(f"\n股票池: {info['name']}  来源: {info['source']}  数量: {info['size']}")
    if info.get("cache_file"):
        print(f"缓存文件: {info['cache_file']}  更新时间: {info.get('updated_at') or '-'}")
    if info.get("error"):
        print(f"错误: {info['error']}")
    if info["size"] and info["size"] < 50 and name.lower() in ("hs300", "zz500", "sz50", "all"):
        print(f"⚠️ 股票池数量异常，当前仅 {info['size']} 只，请检查数据源或股票池配置。")
    print("前 10 只:", ", ".join(info["symbols"][:10]) or "(空)")
    return 0


def cmd_predict(args) -> int:
    if getattr(args, "symbol", None):
        r = service.predict_symbol(args.symbol, horizon=args.horizon, use_sentiment=getattr(args, "use_sentiment", False))
        if not r.get("success"):
            print("预测失败：" + r.get("error", "")); return 1
        p = r["prediction"]
        print(f"\n{r['symbol']} {r.get('name','')} 预测上涨模型:")
        print(f"  3日上涨概率: {p.get('prob_up_3d',0)*100:.0f}%  5日: {p.get('prob_up_5d',0)*100:.0f}%  10日: {p.get('prob_up_10d',0)*100:.0f}%")
        print(f"  预期5日收益: {p.get('expected_return_5d',0)*100:.1f}%  综合评分: {p.get('final_score')}  信号: {p.get('signal')}")
        print(f"  推荐理由: {p.get('reason')}")
        print(f"  风险提示: {p.get('risk')}")
        print(f"\n{r.get('disclaimer','')}")
        return 0
    import time as _t
    t0 = _t.time()
    res = service.predict_top(top_n=args.top, horizon=args.horizon, use_sentiment=getattr(args, "use_sentiment", False))
    flag = "真实数据" if res.get("is_real_data") else "示例数据(回退)"
    print(f"\n未来可能上涨股票 Top {res['top_n']} (asof={res.get('asof')}, {res.get('source')}/{flag}):")
    print("-" * 104)
    print(f"{'#':<3}{'代码':<11}{'名称':<10}{'3日↑':>6}{'5日↑':>6}{'10日↑':>6}{'预期5日':>8}{'综合':>7}  {'信号':<8}{'理由'}")
    for p in res.get("picks", []):
        print(f"{p.get('rank',''):<3}{p.get('symbol',''):<11}{str(p.get('name','')):<10}"
              f"{(p.get('prob_up_3d') or 0)*100:>5.0f}%{(p.get('prob_up_5d') or 0)*100:>5.0f}%{(p.get('prob_up_10d') or 0)*100:>5.0f}%"
              f"{(p.get('expected_return_5d') or 0)*100:>7.1f}%{p.get('final_score',0):>7.1f}  {str(p.get('signal','')):<8}{str(p.get('reason',''))[:40]}")
    print("-" * 104)
    if not res.get("picks"):
        print("无结果。")
    print(f"用时 {_t.time()-t0:.1f} 秒")
    print(res.get("disclaimer", ""))
    return 0


def cmd_sentiment(args) -> int:
    if getattr(args, "symbol", None):
        res = service.sentiment_for(args.symbol)
        if not res.get("available"):
            print(f"{res.get('symbol')} {res.get('name','')}: {res.get('message','无舆情数据')}")
        else:
            s = res["sentiment"]
            tag = "（示例舆情数据）" if res.get("is_mock") else ""
            print(f"\n{res['symbol']} {res.get('name','')} 舆情{tag}:")
            print(f"  关注度评分: {s.get('attention_score')}  热度排名: {s.get('hot_rank')}")
            print(f"  情绪分数: {s.get('sentiment_score')}  正面/负面比例: {s.get('positive_ratio')}/{s.get('negative_ratio')}")
            print(f"  新闻(1d/3d): {s.get('news_count_1d')}/{s.get('news_count_3d')}  讨论(1d): {s.get('mention_count_1d')}")
            print(f"  风险词: {', '.join(s.get('risk_keywords') or []) or '无'}")
            print(f"  正面词: {', '.join(s.get('positive_keywords') or []) or '无'}")
        print(f"\n{res.get('disclaimer','')}")
        return 0
    res = service.sentiment_top(top_n=args.top)
    if not res.get("available"):
        print("暂无舆情数据（未接入真实舆情源；演示模式下可用示例舆情）。")
        print(res.get("disclaimer", ""))
        return 0
    tag = "（示例舆情数据）" if res.get("is_mock") else ""
    print(f"\n舆情热度 Top {res['top_n']}{tag}:")
    print(f"{'#':<3}{'代码':<11}{'名称':<10}{'关注度':>7}{'情绪':>7}{'新闻1d':>7}  风险词")
    for i, s in enumerate(res["results"], 1):
        print(f"{i:<3}{s.get('symbol',''):<11}{str(s.get('name','')):<10}{s.get('attention_score',0):>7.1f}"
              f"{s.get('sentiment_score',0):>7.2f}{int(s.get('news_count_1d') or 0):>7}  {', '.join(s.get('risk_keywords') or [])}")
    print(f"\n{res.get('disclaimer','')}")
    return 0


def cmd_timing(args) -> int:
    if not getattr(args, "mode", None):
        cm = service.current_mode()
        print(f"\n系统时间: {cm['system_time']}  (交易日: {cm['is_trading_day']})")
        print(f"建议: {cm['advice']}")
        print("\n可用时间模式:")
        for m in cm["modes"]:
            star = " ←建议" if m["key"] == cm["suggested"] else ""
            print(f"  {m['key']:<16}{m['name']}  [{m['window']}]  {m['desc']}{star}")
        print(f"\n{cm['disclaimer']}")
        return 0

    res = service.run_mode(args.mode, strategy=getattr(args, "strategy", "short_strength"), top_n=args.top)
    print(f"\n【{res.get('title', args.mode)}】")
    if res.get("supported") is False or res.get("realtime") is False or res.get("message"):
        if res.get("message"):
            print("  " + res["message"])
        if res.get("advice"):
            print("  操作建议: " + res["advice"])
    for p in res.get("picks", [])[: args.top]:
        if args.mode in ("after_close", "close_review"):
            print(f"  {p.get('rank','-')} {p.get('symbol','')} {p.get('name','')} "
                  f"5日{(p.get('ret_5d') or 0)*100:.1f}% 评分{p.get('score',0):.2f} {p.get('signal','')}")
        elif args.mode == "auction_confirm":
            print(f"  {p.get('symbol','')} {p.get('name','')} 竞价{(p.get('auction_pct') or 0)*100:.1f}% "
                  f"高开过多={p.get('high_open_too_much')} 低开破位={p.get('low_open_break')}")
        elif args.mode == "open_confirm":
            print(f"  {p.get('symbol','')} {p.get('name','')} 开盘{(p.get('open_pct') or 0)*100:.1f}% "
                  f"当前{(p.get('now_pct') or 0)*100:.1f}% 站上开盘={p.get('above_open')}")
    print(f"\n{res.get('disclaimer','')}")
    return 0


def cmd_forecast(args) -> int:
    res = service.forecast_symbol(args.symbol, horizon=args.horizon)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args) -> int:
    try:
        import uvicorn
    except Exception:
        print("需要安装 web 依赖: pip install -e '.[web]'", file=sys.stderr)
        return 1
    import os
    # 通过环境变量把数据源配置传给（可能 reload 的）服务进程
    cfg = service.DATA_CFG
    os.environ["AQUANT_SOURCE"] = cfg["source"]
    os.environ["AQUANT_SYMBOLS"] = ",".join(cfg["symbols"])
    os.environ["AQUANT_START"] = cfg["start"]
    os.environ["AQUANT_END"] = cfg["end"]
    os.environ["AQUANT_BENCHMARK"] = cfg["benchmark"]
    os.environ["AQUANT_CACHE_DIR"] = cfg["cache_dir"]
    print(f"数据源: {cfg['source']}  股票池: {len(cfg['symbols'])} 只  区间: {cfg['start']}~{cfg['end']}")
    print(f"启动本地仪表盘: http://{args.host}:{args.port}  (Ctrl+C 退出)")
    uvicorn.run("aqs.api.server:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aquant", description="A股量化交易系统 (AQuant)")
    p.add_argument("--version", action="version", version=f"AQuant {__version__}")
    # 公共数据源选项（各子命令共享）
    data = argparse.ArgumentParser(add_help=False)
    data.add_argument("--source", choices=["baostock", "akshare", "sample"],
                      help="数据源 (默认 baostock，取数失败自动回退 sample)")
    data.add_argument("--symbols", help="逗号分隔股票池, 如 600519.SH,000333.SZ")
    data.add_argument("--universe", help="股票池预设: hs300 / zz500 / sz50 / custom")
    data.add_argument("--start", help="数据起始日期 YYYY-MM-DD")
    data.add_argument("--end", help="数据结束日期 YYYY-MM-DD")
    data.add_argument("--benchmark", help="基准指数, 默认 000300.SH")
    data.add_argument("--cache-dir", dest="cache_dir", help="本地缓存目录, 默认 .cache")
    data.add_argument("--refresh", action="store_true", help="强制重新取数(忽略缓存)")

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("strategies", help="列出策略模板").set_defaults(func=cmd_strategies)
    sub.add_parser("quality", help="数据质量报告", parents=[data]).set_defaults(func=cmd_quality)

    bt = sub.add_parser("backtest", help="运行回测", parents=[data])
    bt.add_argument("--strategy", default="predictive_ranking")
    bt.add_argument("--params", help="JSON 参数, 如 '{\"top_n\":5}'")
    bt.add_argument("--fill", default="next_open", choices=["next_open", "close"])
    bt.add_argument("--rebalance", choices=["daily", "weekly", "monthly"], help="调仓频率")
    bt.add_argument("--max-position", dest="max_position", type=float, help="单只最大仓位, 如 0.2")
    bt.add_argument("--save", action="store_true", help="导出结果到 outputs/")
    bt.add_argument("--json", action="store_true")
    bt.set_defaults(func=cmd_backtest)

    pa = sub.add_parser("paper", help="模拟交易", parents=[data])
    pa.add_argument("--strategy", default="double_ma")
    pa.add_argument("--params")
    pa.set_defaults(func=cmd_paper)

    sc = sub.add_parser("screen", help="快速筛选 Top N 候选股", parents=[data])
    sc.add_argument("--strategy", default="short_strength",
                    help="选股策略: short_strength/trend_quality/quality_value")
    sc.add_argument("--top", type=int, default=20)
    sc.add_argument("--asof", help="筛选时点 (YYYY-MM-DD)，默认最新")
    sc.add_argument("--min-amount", dest="min_amount", type=float, default=0.0, help="最小近20日日均成交额(元)")
    sc.add_argument("--exclude-st", dest="exclude_st", action="store_true", default=True, help="排除 ST (默认开)")
    sc.add_argument("--include-st", dest="exclude_st", action="store_false", help="包含 ST")
    sc.add_argument("--max-market-cap", dest="max_market_cap", type=float, default=3000e8,
                    help="超大市值阈值(元), 与低涨幅共同判定慢速蓝筹, 默认3000亿")
    sc.add_argument("--keep-blue-chip", dest="exclude_slow_blue_chip", action="store_false",
                    default=True, help="不排除超大市值慢速蓝筹")
    sc.add_argument("--use-cache", dest="use_cache", action="store_true", default=True, help="使用本地缓存(默认开)")
    sc.add_argument("--no-cache", dest="use_cache", action="store_false", help="忽略缓存重新取数")
    sc.add_argument("--use-sentiment", dest="use_sentiment", action="store_true", default=False,
                    help="加入舆情/关注度因子(辅助)")
    sc.add_argument("--save", action="store_true", help="导出结果到 outputs/")
    sc.set_defaults(func=cmd_screen)

    un = sub.add_parser("universe", help="检查股票池数量与前10只", parents=[data])
    un.set_defaults(func=cmd_universe)

    pr = sub.add_parser("predict", help="预测上涨模型(未来3/5/10日)", parents=[data])
    pr.add_argument("--symbol", help="单只股票预测；不指定则看 Top")
    pr.add_argument("--horizon", type=int, default=5, choices=[3, 5, 10])
    pr.add_argument("--top", type=int, default=20)
    pr.add_argument("--use-sentiment", dest="use_sentiment", action="store_true", default=False)
    pr.set_defaults(func=cmd_predict)

    se = sub.add_parser("sentiment", help="舆情/关注度因子", parents=[data])
    se.add_argument("--symbol", help="查看单只股票舆情；不指定则看 Top")
    se.add_argument("--top", type=int, default=20)
    se.set_defaults(func=cmd_sentiment)

    tm = sub.add_parser("timing", help="短线选股时间模式", parents=[data])
    tm.add_argument("--mode", choices=["after_close", "auction_confirm", "open_confirm", "close_review"],
                    help="不指定则显示当前建议模式")
    tm.add_argument("--strategy", default="short_strength")
    tm.add_argument("--top", type=int, default=20)
    tm.set_defaults(func=cmd_timing)

    fc = sub.add_parser("forecast", help="走势分析与预测", parents=[data])
    fc.add_argument("--symbol", required=True)
    fc.add_argument("--horizon", type=int, default=5)
    fc.set_defaults(func=cmd_forecast)

    sv = sub.add_parser("serve", help="启动本地 Web 仪表盘", parents=[data])
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
    sv.set_defaults(func=cmd_serve)

    return p


def _apply_data_config(args) -> None:
    """把命令行数据源参数应用到 service 全局配置。"""
    symbols = None
    if getattr(args, "symbols", None):
        symbols = [s.strip() for s in args.symbols.split(",")]
    elif getattr(args, "universe", None):
        # 预设股票池（hs300/zz500/sz50）解析为具体代码
        symbols = service.resolve_universe(args.universe)
    service.configure_data(
        source=getattr(args, "source", None),
        symbols=symbols,
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        benchmark=getattr(args, "benchmark", None),
        cache_dir=getattr(args, "cache_dir", None),
        refresh=getattr(args, "refresh", None),
    )


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if hasattr(args, "source"):  # 命令带数据源选项
        _apply_data_config(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
