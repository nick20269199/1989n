---
name: stock-analysis
description: 项目专属股票分析 — 教 Claude 怎么用本地 stock_data/ 数据做分析，覆盖 5 维度分析框架 + 止损检查 + 交叉验证
origin: 1989n
---

# 股票分析技能 (项目专属)

> 这不是通用股票分析。这是教 Claude 怎么操作 1989n 项目本地的数据基础设施。

## 数据在哪

| 数据类型 | 路径 | 格式 |
|---------|------|------|
| 盘中分析 | `stock_data/analysis_30min_*.json` | JSON |
| 集合竞价 | `stock_data/call_auction_*.json` | JSON |
| 新闻汇总 | `stock_data/morning_enhanced.json` | JSON |
| 收盘复盘 | `stock_data/closing_review.json` | JSON |
| 行情数据库 | `stock_data/stock.db` | SQLite |
| 持仓数据 | `stock_analysis/data/portfolio.json` | JSON |

## 分析框架（5 维度，缺一不可）

每次分析一只票，必须覆盖：

1. **技术面** — 价格/均线/MACD/RSI/成交量，引用具体数值
2. **资金面** — 主力资金净流入/流出，超大单/大单分布
3. **题材面** — 所属板块涨跌幅、板块资金流向、板块内排名
4. **消息面** — 最近 24h 相关新闻，标注来源和时间
5. **情绪面** — 全市场涨跌比、涨停/跌停数、恐慌/贪婪指标

## 分析输出格式

每份报告三段式：

```
## [股票代码] [股票名称] — [分析时间]

### 数据
[5 维度具体数据，每项标注来源]

### 分析
[交叉对比，发现矛盾或一致信号]
[置信度评级: 高(>80%) / 中(60-80%) / 低(<60%)]

### 建议
[具体操作建议或观望理由]
[如涉及开仓/加仓/调仓 → 必须先跑 adversarial-review]
```

## 硬约束（执行前检查）

- 当前价触及或跌破止损线 → 第一个字就报告
- 分析中不得出现"走势尚可""表现不错"等模糊描述，必须引用数字
- 涉及交易决策 → 必须先跑 `adversarial-review` skill
- 数据缺失 → 明确说"XX 数据缺失，以下分析缺少 XX 维度"
- 数据源有矛盾 → 标注矛盾，不选边站

## 全仓扫描（并行 Subagent）

当用户要求"分析全仓"或"扫一遍持仓"，必须用并行 Subagent，不得串行：

```
对 portfolio.json 里的每只票，同时启动 5 个 code-explorer Subagent：
  - 每个 Subagent 读对应股票的最新 JSON 数据
  - 每个 Subagent 按 5 维度框架输出摘要
  - 主会话汇总 5 份摘要，交叉对比，找出最强/最弱信号
```

**为什么不串行**：串行读 5 只票的数据会把对话窗口撑爆，前后矛盾的信息会被遗忘。

**什么时候用 Agent Team**：如果任务需要 3+ 个独立 Claude 会话互相协调（比如一队盯盘、一队分析新闻、一队做风控），用 Agent Team。单次全仓扫描用并行 Subagent 就够了。

## 三线数据打通

项目有三条独立运行的分析线，结果互相不通。读取数据时注意：

1. 早间新闻 (`morning_enhanced.json`) → 盘中分析应引用早间提到的题材/个股
2. 盘中情报 (`intel_report_*.json` / `analysis_30min_*.json`) → 收盘复盘应对比盘中的异动是否持续
3. 收盘复盘 (`closing_review.json`) → 隔夜分析应基于复盘的结论

当分析结果跨越时间段，主动检查前序 JSON 文件，不靠猜测。

## 知识库查询

项目有 SQLite 索引层 `knowledge_db.py`，可以用它快速查历史分析结果：

```bash
cd d:/1989n/stock_analysis && python knowledge_db.py query "<关键词>"
```
