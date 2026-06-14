# AQuant · A 股量化交易系统

> 面向中国 A 股市场的本地化（个人 PC 部署）量化交易系统，覆盖从
> **策略想法 → 数据研究 → 回测验证 → 模拟交易 → 实盘执行 → 风险控制 → 合规管理 → 绩效复盘 → 可视化监控**
> 的完整闭环。

本项目是一套可运行的工程骨架 + 核心引擎实现：开箱即用（内置合成示例数据，无需任何付费数据源即可跑通全流程），
模块化设计，核心引擎仅依赖 `numpy` / `pandas`，Web 仪表盘与机器学习为可选扩展。

> ⚠️ **重要声明**
> 本系统默认使用**合成示例数据**用于演示与测试，回测/预测结果**不代表任何真实业绩**。
> 股价高度随机，任何模型都**无法可靠预测**未来价格；"判断未来走势"功能只输出概率/趋势参考，**不构成投资建议**。
> 程序化交易须遵守中国证监会《证券市场程序化交易管理规定（试行）》及沪深北交易所实施细则（自 2025-07-07 起施行），
> 投资者须履行 **"先报告、后交易"**。**市场有风险，投资需谨慎。**

---

## 12 个核心模块与代码映射

| # | 模块 | 说明 | 代码位置 |
|---|------|------|----------|
| 1 | 数据管理 Market Data | 多频率行情/基本面、复权、停牌、退市、交易日历、**时间点数据库(PIT)**、数据质量控制、数据版本 | `aqs/data/` |
| 2 | 策略研发 Strategy | 统一 API（`order_target_percent`/`get_price`/`schedule_function`…）、策略基类、模板库 | `aqs/strategy/` |
| 3 | 因子研究 Factor | 多因子打分、IC/截面、中性化（`MultiFactor` 模板 + ML 特征工程） | `aqs/strategy/templates.py`, `aqs/ml/features.py` |
| 4 | 回测引擎 Backtest | 事件驱动；T+1、涨跌停、停牌、一手=100、佣金/印花税/过户费/滑点、撮合与部分成交 | `aqs/backtest/` |
| 5 | 模拟交易 Paper | 用（回放/实时）行情跑策略、不下真实单、与回测同一 Context 契约 | `aqs/trading/trader.py` |
| 6 | 实盘交易 Live | 券商网关抽象 `BrokerGateway` + 模拟券商 `SimulatedBroker` | `aqs/trading/broker.py` |
| 7 | 订单管理 OMS | 订单生命周期、重复下单保护、对账、**一键停止/只读/全局撤单** | `aqs/trading/oms.py` |
| 8 | 执行管理 EMS | TWAP / VWAP / 冰山 / 分批下单 | `aqs/trading/ems.py` |
| 9 | 风控管理 RMS | 事前（仓位/集中度/流动性/ST）、事中（回撤/当日亏损自动停机）、事后（成交质量/换手） | `aqs/risk/` |
| 10 | 合规管理 Compliance | 程序化交易**报备信息管理**、监管阈值**参数化**、高频/撤单比例**异常监控**、**哈希链审计日志** | `aqs/compliance/` |
| 11 | 绩效分析 Performance | 收益/回撤/夏普/索提诺/卡玛/胜率/Alpha-Beta/信息比率/月度热力图 + 反过拟合（MC/Walk-forward/参数敏感性） | `aqs/performance/` |
| 12 | 可视化监控 Dashboard | 本地 Web 仪表盘（FastAPI + 原生 JS Canvas，无外网依赖） | `aqs/api/` |

附加：**机器学习/AI 走势分析** `aqs/ml/`（特征工程 + 趋势概率预测，含数据泄露防护与风险提示）。

---

## 快速开始

```bash
cd aquant

# 1) 安装核心依赖（仅 numpy + pandas 即可跑回测）
pip install -e .
#   可选：Web 仪表盘 + 机器学习
pip install -e ".[web,ml]"

# 2) 命令行
aquant strategies                       # 列出策略模板
aquant quality                          # 数据质量报告
aquant backtest --strategy multi_factor # 运行回测
aquant paper --strategy double_ma       # 模拟交易
aquant forecast --symbol 600519.SH      # 走势分析与预测
aquant serve                            # 启动本地 Web 仪表盘 (http://127.0.0.1:8000)
```

> 未安装也可直接运行：`PYTHONPATH=src python -m aqs.cli backtest`。

### 仪表盘
`aquant serve` 后浏览器打开 http://127.0.0.1:8000 ，可在线运行回测、查看净值/回撤曲线、月度收益热力图、
风控与合规面板、最近成交、系统日志，以及"AI 走势分析/预测"。所有计算均在本地完成，数据不出本机。

---

## 代码示例

```python
from aqs.data.market_data import MarketDataManager
from aqs.strategy.templates import MultiFactor
from aqs.backtest.engine import BacktestEngine
from aqs.risk.manager import RiskManager
from aqs.compliance.monitor import ComplianceMonitor
from aqs.performance.metrics import analyze

data = MarketDataManager.from_sample()          # 内置合成 A 股数据
engine = BacktestEngine(
    data, MultiFactor(top_n=4, rebalance="monthly"),
    risk_manager=RiskManager(), compliance=ComplianceMonitor(),
    fill_mode="next_open",                        # 次日开盘成交，避免未来函数
)
result = engine.run()
print(analyze(result.equity_curve, result.benchmark).summary_text())
```

自定义策略只需继承 `Strategy` 并使用统一 Context API（回测/模拟/实盘代码完全一致）：

```python
from aqs.strategy.api import Strategy

class MyStrategy(Strategy):
    name = "我的策略"
    def initialize(self, ctx):
        ctx.schedule_function(self.rebalance, "weekly")
    def rebalance(self, ctx):
        for sym in ctx.universe:
            if ctx.can_trade(sym):
                closes = ctx.history(sym, "close", 20)
                if len(closes) == 20 and closes.iloc[-1] > closes.mean():
                    ctx.order_target_percent(sym, 0.1, tag="trend")
```

---

## 接入真实数据：Wind（万得）

系统内置合成示例数据用于演示；接入真实行情只需一个数据源适配器。已提供 **Wind 适配器** `aqs/data/sources/wind.py`。

> 前提：必须在**安装并登录了 Wind 金融终端**、且装好 WindPy 的机器上运行（WindPy 通过本地终端取数，
> 账号登录在终端完成，代码里不放密码）。账号需开通相应数据/行情权限。

```python
from aqs.data.market_data import MarketDataManager
from aqs.backtest.engine import BacktestEngine
from aqs.strategy.templates import MultiFactor

data = MarketDataManager.from_wind(
    symbols=["600519.SH", "300750.SZ", "688981.SH"],
    start="2021-01-01", end="2023-12-31",
    benchmark="000300.SH",
)
res = BacktestEngine(data, MultiFactor(top_n=4)).run()
```

适配器自动拉取：日线 OHLCV、复权因子 `adjfactor`、停牌 `trade_status`、ST 标记 `riskwarning`、
行业 `industry_sw`、上市/退市日、基本面 `pe_ttm/pb_lf/roe/同比`（按可知日期做 PIT），以及基准指数。
字段做成可配置，缺权限的字段会自动跳过并告警。完整示例见 `examples/load_wind_data.py`。
实时行情订阅（需 wsq 权限）见 `WindDataSource.subscribe_realtime`。

## 接入真实数据：同花顺 iFinD

也提供 **同花顺 iFinD 适配器** `aqs/data/sources/ths.py`（基于 `iFinDPy`）。

> 仅支持 **iFinD 专业数据终端 + 数据 API 权限**；普通免费版同花顺没有官方数据 API。
> 账号用环境变量提供，不要写进代码：`export THS_USERNAME=...`，`export THS_PASSWORD=...`。

```python
from aqs.data.market_data import MarketDataManager
data = MarketDataManager.from_ths(
    symbols=["600519.SH", "300750.SZ", "688981.SH"],
    start="2021-01-01", end="2023-12-31", benchmark="000300.SH",
)
```

iFinD 的指标代码（`ths_*`）与参数串随版本/权限略有差异，已集中在 `ths.py` 顶部、可配置；
缺权限的字段会自动跳过并告警。完整示例见 `examples/load_ths_data.py`。

## 设计要点（为什么回测可信）

- **避免未来函数（look-ahead）**：`MarketDataManager` 内置时间点时钟（PIT），`get_price` 不会返回 `as_of` 之后的数据；
  基本面按**真实披露日期**而非报告期入库（`get_fundamentals` 按 `disclosure_date` 过滤）。
- **避免幸存者偏差**：示例数据保留退市股、ST 股，回测可见但按规则不可交易。
- **真实交易规则**：T+1 结算、按板块/ST 区分的涨跌停、停牌、一手=100、佣金（含最低 5 元）、印花税（卖出）、过户费、滑点、成交量参与率导致的部分成交、涨停买不进/跌停卖不出。
- **反过拟合**：Monte-Carlo 回撤分布、Walk-forward 窗口、参数敏感性网格。
- **数据版本**：每次回测记录所用数据版本号（内容哈希），便于复现。

## 风控 / 合规（A 股必备）

- **事前**：单票/单行业仓位、单笔金额、总仓位、持仓数量、流动性（占近期日均成交额比例）、禁买 ST、黑名单。
- **事中**：最大回撤、当日亏损触发**自动停机**。
- **事后**：成交质量、换手率、成本占比复盘。
- **合规**：程序化交易**报备信息**完整性校验（实盘前强制 "先报告、后交易"）；高频认定阈值**参数化**
  （默认：每秒申报+撤单 ≥ 300，或全日 ≥ 20000；接近阈值预警）；撤单比例监控；**哈希链审计日志**（可校验防篡改）。

> 所有监管阈值均在 `aqs/config.py` 中**参数化**，不写死在代码里，便于按交易所/板块/日期调整与后续监管更新。

---

## 本地部署架构

- 前端：本地浏览器访问的 Web 仪表盘（原生 JS，无 CDN 依赖）。
- 后端：Python + FastAPI；策略引擎：Python。
- 数据库（建议，可扩展）：轻量 SQLite / 标准 PostgreSQL / 大数据回测 DuckDB·ClickHouse；缓存 Redis（可选）。
- 任务调度：APScheduler / Celery（可选）。

**建议最低硬件**：CPU 8 核+，内存 16GB（推荐 32GB），SSD ≥ 1TB（存 Tick 数据更大），稳定宽带 + 断线保护。

> 现实提示：个人 PC 适合普通量化、中低频与部分准高频策略；**真正的高频交易**对网络延迟、券商通道、机房托管与监管要求极高，并非"家用电脑跑得快"即可，请谨慎评估并依法合规。

---

## 测试

```bash
cd aquant && PYTHONPATH=src python -m pytest -q
```

覆盖：PIT 防未来函数、基本面披露日、涨跌停、数据质量、T+1、成本模型、一手约束、风控拦截与停机、
审计链防篡改、高频阈值、报备门禁、OMS 重复下单/一键停止、EMS 切单、模拟交易、绩效指标、ML 无泄露等。

## 路线图（高级版可扩展）

两融/期货/期权账户、可视化拖拽策略构建器、Jupyter 研究环境模板、深度模型（LSTM/Transformer）、AutoML、
NLP 新闻/研报情绪、多账户与组合管理（PMS）、移动端监控、云端备份、Windows 一键安装包 / Docker Compose。

## 许可证
MIT
