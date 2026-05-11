---
name: morning-brief
description: 盘前晨报生成 — 美股收盘+CLS新闻+板块龙头→持仓映射。8:37自动产出，也可手动触发 /morning-brief
type: skill
---

# Morning Brief v1.0

每天 8:37 自动产出盘前晨报，包含：
1. 美股收盘（道琼斯/纳斯达克/标普500）
2. 板块龙头涨跌（AMD/英特尔/英伟达/美光/阿斯麦/特斯拉/Rocket Lab）→ 持仓映射
3. 重要政策/行业新闻
4. 公告精选（合同/减持/解禁）
5. 风险提示
6. 今日关注日历

## 数据来源
- CLS 新闻: news_scheduler.py morning (8:00 产出)
- 美股数据: akshare (新浪财经接口)
- 概念映射: stock_data/concept_mapping.json

## 输出
- `stock_data/morning_brief_latest.md` — 可读 Markdown
- `stock_data/morning_brief_latest.json` — 结构化数据

## 手动触发
```
python stock_analysis/morning_brief.py
```

## Cron
- 8:37 weekdays — 在集合竞价(9:15)前产出
- 依赖: news_scheduler.py morning 在 8:00 先跑完
