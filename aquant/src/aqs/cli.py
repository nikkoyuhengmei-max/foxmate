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
    for key, name in service.list_strategies().items():
        print(f"  {key:<14} {name}")
    return 0


def cmd_quality(_) -> int:
    rows = service.data_quality()
    print(f"{'symbol':<12}{'rows':>6}{'nan':>6}{'dup':>5}{'invalid':>9}{'ok':>5}")
    for r in rows:
        print(f"{r['symbol']:<12}{r['rows']:>6}{r['nan_rows']:>6}{r['duplicates']:>5}{r['invalid_ohlc']:>9}{str(r['ok']):>5}")
    return 0


def cmd_backtest(args) -> int:
    params = json.loads(args.params) if args.params else None
    res = service.run_backtest(strategy=args.strategy, params=params, start=args.start,
                               end=args.end, fill_mode=args.fill)
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
    print(f"启动本地仪表盘: http://{args.host}:{args.port}  (Ctrl+C 退出)")
    uvicorn.run("aqs.api.server:app", host=args.host, port=args.port, reload=args.reload)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="aquant", description="A股量化交易系统 (AQuant)")
    p.add_argument("--version", action="version", version=f"AQuant {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("strategies", help="列出策略模板").set_defaults(func=cmd_strategies)
    sub.add_parser("quality", help="数据质量报告").set_defaults(func=cmd_quality)

    bt = sub.add_parser("backtest", help="运行回测")
    bt.add_argument("--strategy", default="multi_factor")
    bt.add_argument("--params", help="JSON 参数, 如 '{\"top_n\":5}'")
    bt.add_argument("--start"); bt.add_argument("--end")
    bt.add_argument("--fill", default="next_open", choices=["next_open", "close"])
    bt.add_argument("--json", action="store_true")
    bt.set_defaults(func=cmd_backtest)

    pa = sub.add_parser("paper", help="模拟交易")
    pa.add_argument("--strategy", default="double_ma")
    pa.add_argument("--params"); pa.add_argument("--start"); pa.add_argument("--end")
    pa.set_defaults(func=cmd_paper)

    fc = sub.add_parser("forecast", help="走势分析与预测")
    fc.add_argument("--symbol", required=True)
    fc.add_argument("--horizon", type=int, default=5)
    fc.set_defaults(func=cmd_forecast)

    sv = sub.add_parser("serve", help="启动本地 Web 仪表盘")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.add_argument("--reload", action="store_true")
    sv.set_defaults(func=cmd_serve)

    return p


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
