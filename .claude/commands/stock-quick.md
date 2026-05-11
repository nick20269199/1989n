---
name: stock-quick
description: 个股速查 — 实时行情+技术指标+资金流向+资讯，一键全景
allowed_tools: ["mcp__china-stock__get_realtime_data", "mcp__china-stock__get_hist_data", "mcp__china-stock__get_stock_basic_info", "mcp__china-stock__get_fund_flow", "mcp__china-stock__get_investor_sentiment", "mcp__china-stock__get_news_data"]
---

# /stock-quick <股票代码> — 个股速查全景

快速了解任何A股当前状态，适合盘中快速决策。

## 用法

```
/stock-quick 002156          # 查通富微电
/stock-quick 600519          # 查贵州茅台
```

## 执行步骤

### 第一步：并行获取5项数据

同时调用以下 MCP 工具（**所有调用必须并行，一次发出**）：

1. `mcp__china-stock__get_realtime_data` — 获取实时行情
2. `mcp__china-stock__get_hist_data` — 获取近30天日K线，含常用技术指标（SMA, EMA, RSI, MACD, BOLL, OBV, MFI）
3. `mcp__china-stock__get_stock_basic_info` — 获取基本信息（行业/市值/PE）
4. `mcp__china-stock__get_fund_flow` — 获取近100日资金流向
5. `mcp__china-stock__get_news_data` — 获取最新相关新闻

### 第二步：汇总输出

将数据整理为以下格式输出：

```markdown
## {股票名称} ({代码}) 速查 | {更新时间}

### 实时行情
| 最新价 | 涨跌幅 | 今开 | 最高 | 最低 | 成交量(手) | 成交额 |
|--------|--------|------|------|------|------------|--------|
| ... | ... | ... | ... | ... | ... | ... |

### 基本概况
- 总市值 / 流通市值 / PE / 市净率 / 行业 / 上市日期

### 技术信号（近30天日线）
- 趋势：SMA 5/10/20 多空排列
- RSI(14)：超买/超卖/中性
- MACD：金叉/死叉/方向
- BOLL：价格在布林带上/中/下轨
- OBV：量能趋势
- MFI：资金流入流出强度

### 资金流向（近5日主力动向）
| 日期 | 主力净流入 | 超大单 | 大单 | 中单 | 小单 |
|------|-----------|--------|------|------|------|
（取最近5天）

### 近期要闻
列出最近3-5条新闻标题和时间
```

### 第三步：一句话总结

根据以上数据，给出简短的综合判断（1-2句话），包含：
- 当前技术面偏多/偏空
- 主力资金态度（流入/流出/观望）
- 是否有重大消息催化
