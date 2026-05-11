---
name: stock-a
description: 大A财经数据框架 - 4大稳定数据源(mootdx+腾讯财经+akshare+iwencai)、5大模块(行情/研报/新闻/财务/公告)、13个接口
allowed_tools: ["Bash"]
---

# /stock-a - 大A财经数据框架

## 用法

```bash
/stock-a market                    # 实时行情快照
/stock-a kline 600519              # 个股K线
/stock-a sector                    # 板块排行
/stock-a news                      # 财经快讯(多源融合)
/stock-a stock_news 300750         # 个股新闻
/stock-a research 000858           # 个股研报
/stock-a industry                  # 行业研报
/stock-a macro                     # 宏观研报
/stock-a financials 002594         # 三大财报(利润+资产+现金)
/stock-a announcements 002594      # 个股公告
/stock-a regulatory                # 监管公告
/stock-a daily                     # 每日全量采集(5模块全覆盖)
/stock-a report                    # 生成日报摘要
```

## 执行方式

```bash
python stock_analysis/stock_skill.py ${ARG1}
python stock_analysis/stock_skill.py ${ARG1} ${ARG2}
```
