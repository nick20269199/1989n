# 每日技术侦查系统 (Daily Tech Scout)

## 目标

每天从公共区域（GitHub、论文、博客、Hacker News、工具发布）扫描对交易系统有用的新东西，按分类归档到 `D:/1989n/stock_data/scout/`。

## 四大侦查方向

| 方向 | 关键词 | 优先级 |
|------|--------|--------|
| 交易策略 | quantitative-trading, algorithmic-trading, factor-research, backtesting | HIGH |
| AI 智能体 | claude-code, ai-agents, MCP, LLM-tools, agent-architecture | HIGH |
| 交易软件/工具 | trading-tools, financial-data, market-data-api, backtest-framework | HIGH |
| 前沿探索 | new AI model, paper breakthrough, new framework, innovative tool | MEDIUM |

## 输出规范

每天生成一份 `YYYY-MM-DD_scout_report.md`，格式：

```markdown
# 技术侦查日报 YYYY-MM-DD

## 交易策略 (N items)
### [名称] — 来源: [URL]
- **做什么**: 一句话
- **对我们的作用**: 具体用在哪个模块/策略
- **风险评估**: 成熟度/维护状态/许可证

## AI 智能体 (N items)
### [名称] — 来源: [URL]
...

## 交易软件/工具 (N items)
...

## 前沿探索 (N items)
...
```

同时更新 `scout_registry.json` 的 items 数组，每条记录格式：
```json
{
  "id": "YYYYMMDD-NNN",
  "date": "YYYY-MM-DD",
  "category": "trading_strategy",
  "name": "...",
  "source_url": "...",
  "one_liner": "...",
  "use_for": "...",
  "status": "new|evaluated|integrated|rejected",
  "evaluated_at": null
}
```

## 扫描策略

1. GitHub Search API：搜 trending repos + topic 搜索
2. WebSearch：搜 "new AI agent framework 2026"、 "quantitative trading new" 等
3. Hacker News / Product Hunt：前沿工具
4. arXiv：q-fin + cs.AI 新论文

## 评估标准

- 必须有公开可访问的 URL
- 必须说明对我们的具体作用（不能只说"有用"）
- 如果找不出作用 → 不入库
- 许可证必须允许商用（MIT/Apache/BSD）或公开论文
