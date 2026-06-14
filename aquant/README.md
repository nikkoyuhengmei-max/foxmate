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

### 选择数据源（默认 Baostock 真实数据 + 本地缓存）

所有命令默认使用 **Baostock 真实行情**并写入本地缓存 `.cache/`（取数失败自动回退内置示例数据）。
可用统一参数切换数据源/股票池/区间：

```bash
aquant screen --top 8                                   # 默认 baostock 真实数据
aquant screen --source sample                           # 用内置示例数据（离线、最快）
aquant screen --symbols 600519.SH,000333.SZ --start 2023-01-01 --end 2023-12-31
aquant backtest --source baostock --strategy multi_factor
aquant serve --source baostock                          # 仪表盘也用真实数据
```

也可用环境变量配置：`AQUANT_SOURCE`、`AQUANT_SYMBOLS`、`AQUANT_START`、`AQUANT_END`、`AQUANT_CACHE_DIR`。

### 选股 / 回测参数与导出

```bash
# 选股：时点 / 数量 / 股票池(hs300/zz500/sz50) / 最小成交额 / 排除ST / 导出
aquant screen --asof 2026-06-12 --top 20 --universe hs300 --min-amount 50000000 --save
# 回测：区间 / 股票池 / 策略 / 调仓频率 / 单只最大仓位 / 导出 csv+html
aquant backtest --strategy multi_factor --start 2024-01-01 --end 2026-06-12 --universe hs300 \
                --rebalance monthly --max-position 0.2 --save
```

导出位置：`outputs/screen_日期.csv`、`outputs/backtest_策略_日期.{csv,html}`，仪表盘会读取最新输出。

### 行业映射

数据源缺行业字段时，用本地 `data/industry_map.csv` 自动补全（命中即显示行业，未命中显示"未分类"）。
可用环境变量 `AQUANT_INDUSTRY_MAP` 指定自定义映射文件。

### 对比用基础策略

`buy_and_hold`(买入持有) / `double_ma`(双均线) / `low_volatility`(低波动) / `dividend_value`(低估值价值) /
`momentum_20_60`(20/60动量) / `multi_factor_v2`(多因子升级)，均可 `aquant backtest --strategy <名称>` 运行、输出同样指标。

### 仪表盘（真实/示例/模拟/实盘 明确区分）

`aquant serve` 后顶部状态栏显示：**数据源 / 数据日期 / 系统时间 / 是否真实数据 / 是否有成交记录**；
- 非真实数据时显示醒目「当前为示例数据(mock)」横幅；
- 「🔄 刷新真实数据」按钮一键重跑 screen+backtest+forecast 并刷新；
- 「最近成交」仅来自真实 paper/live 记录（`outputs/trades.csv`），无记录显示「暂无真实成交记录」，**不再显示任何假成交**；
- AI 预测显示训练区间与最新行情日期，数据过期(>7天)弹黄色警告；
- 系统日志使用当前系统时间。

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

## 选股器 Screener（快速筛选 5–10 支候选股）

结合**多周期历史**（1/3/5/20/120 半年/250 一年 日收益）+ **量化指标**（趋势排列、RSI、量比、波动率惩罚）
+ **（可选）集合竞价**（开盘竞价跳空、竞价量比），做横截面 z-score 加权打分，输出 Top N。

```bash
aquant screen --top 8            # 命令行选股（最新时点）
aquant screen --top 8 --asof 2023-06-30   # 指定历史时点（PIT，不偷看未来）
```

```python
from aqs.data.market_data import MarketDataManager
from aqs.research.screener import Screener

data = MarketDataManager.from_sample()           # 接入 iFinD: MarketDataManager.from_ths(...)
picks = Screener().screen(data, top_n=8)         # 返回排序后的候选股 DataFrame
```

**接入 iFinD 后用集合竞价**（开盘前/开盘时取竞价快照再筛选）：

```python
from aqs.data.sources.ths import THSDataSource
src = THSDataSource()
auction = src.get_call_auction(universe)         # {代码: {gap 跳空, auction_vol_ratio 竞价量比}}
data = MarketDataManager.from_ths(universe, "2023-01-01", "2023-12-31")
picks = Screener().screen(data, universe=universe, auction=auction, top_n=8)
```

> 因子权重在 `ScreenConfig.weights` 可调。选股结果仅为量化参考，不构成投资建议。
> 注：日线只能到上一收盘；要"过去 24 小时/分钟级"需接 iFinD 分钟(wsi)/实时数据，接上后即可扩展周期。

## 实时行情 + 集合竞价 + 实盘下单：券商 miniQMT（xtquant）

要做到**盘中实时、集合竞价、真正下单**，用券商的 **miniQMT**（开一个普通证券账户、向券商申请 QMT 权限即可，免数据费）。
需在装有并登录 QMT/miniQMT 客户端的机器上运行，并安装 `xtquant`。

- 行情：`MarketDataManager.from_qmt(...)`，集合竞价 `QMTDataSource().get_call_auction(...)`，实时订阅 `subscribe_realtime(...)`。
- 实盘：`QMTBroker` 实现统一 `BrokerGateway`，可直接交给 `PaperTrader(..., live=True, broker=QMTBroker(...))` 驱动，
  **复用全部风控 / 合规报备门禁 / 一键停止 / 审计日志**。

```python
from aqs.trading.qmt_broker import QMTBroker
from aqs.trading.trader import PaperTrader

broker = QMTBroker(account_id="资金账号", qmt_path=r"D:\\miniQMT\\userdata_mini", dry_run=True)  # 默认只记录不下单
broker.connect()
trader = PaperTrader(data, strategy, risk_manager=..., compliance=..., live=True, broker=broker)
trader.run()           # 盘中也可循环 trader.step(now)
# trader.stop_trading()  # 一键停止 + 全撤 + 只读
```

> ⚠️ 安全：`QMTBroker` 默认 `dry_run=True`（**只记录、不真实下单**），确认无误并完成程序化交易报备后，
> 才显式改 `dry_run=False`。实盘前系统会强制校验报备信息完整性（先报告、后交易）。完整示例 `examples/live_trading_qmt.py`。

## 接入真实数据：Baostock（免费、免注册、**稳定不限流**，首选）

`pip install baostock` 后即可用，自有数据服务器、基本不限流；一次 K 线查询即返回
**OHLCV + 复权 + PE(TTM)/PB + 是否 ST + 换手率**。配合**本地缓存**：取一次写入磁盘，之后秒读、不再联网。

```python
from aqs.data.market_data import MarketDataManager
from aqs.research.screener import Screener

data = MarketDataManager.from_baostock(
    ["600519.SH", "600036.SH", "300750.SZ", "000333.SZ"],
    start="2022-01-01", end="2023-12-31",
    cache_dir=".cache",          # 取一次后走本地缓存，避免反复联网/限流
)
print(Screener().screen(data, top_n=8))
```

> 无实时/集合竞价（要实时用 AkShare 或券商 miniQMT）。`refresh=True` 可强制重新取数。
> 完整示例 `examples/load_baostock_data.py`。

## 接入真实数据：AkShare（免费、免注册，含实时/竞价）

如果没有 Wind / iFinD 的数据 API 账号，用 **AkShare** 即可：开源免费、**无需账号**，
`pip install akshare` 后联网即可取 A 股日线、实时快照、集合竞价、PE/PB、指数等。

```python
from aqs.data.market_data import MarketDataManager
from aqs.research.screener import Screener

data = MarketDataManager.from_akshare(
    ["600519.SH", "600036.SH", "300750.SZ", "000333.SZ"],
    start="2022-01-01", end="2023-12-31", benchmark="000300.SH",
)
print(Screener().screen(data, top_n=8))          # 选股
```

集合竞价/实时快照（近似）用于盘前选股：

```python
from aqs.data.sources.akshare_source import AkShareDataSource
auction = AkShareDataSource().get_call_auction(universe)   # {代码: {gap, auction_vol_ratio}}
picks = Screener().screen(data, universe=universe, auction=auction, top_n=8)
```

完整示例见 `examples/load_akshare_data.py`。

> 注意：AkShare 抓取的是公开数据站点（东方财富/新浪/百度股市通），**建议在中国大陆网络下使用**；
> 海外/被限流的 IP 可能频繁断连。价格默认前复权（`adjust="qfq"`，可改 `hfq`/`""`）。

### 其它免费/低成本选择
- **Baostock**：免费免注册（日线/分钟/复权因子，无实时）。
- **Tushare**：免费注册取 token，部分接口需积分。
- **券商 miniQMT（xtquant）**：开普通证券账户即可，免数据费，**行情 + 实盘下单**一体（以后做实盘最划算）。

> 需要我加 Baostock / Tushare / miniQMT 适配器，告诉我即可（接口与 AkShare 同构，接上即用）。

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
