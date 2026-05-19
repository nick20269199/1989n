# 蒸馏简报 — 2026-05-19

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (9.0KB)
- `morning_enhanced.json` (8.7KB)
- `sentinel_status.json` (1.3KB)

共 3 个文件待蒸馏

## 今日其他产出

- `analysis_30min_20260519_1130.json` (1.6KB)
- `analysis_30min_20260519_1130.md` (0.6KB)
- `analysis_30min_20260519_1500.json` (1.6KB)
- `analysis_30min_20260519_1500.md` (0.6KB)
- `call_auction_20260519_0926.json` (4.4KB)
- `call_auction_20260519_0956.json` (9.9KB)
- `channel_health_latest.json` (0.3KB)
- `closing_review.log` (24.5KB)
- `closing_review.md` (1.4KB)
- `data_guard_report.json` (1.9KB)
- `intraday_close.log` (47.5KB)
- `intraday_midday.log` (40.3KB)
- `morning_brief.log` (93.0KB)
- `morning_brief_latest.json` (0.9KB)
- `morning_brief_latest.md` (2.2KB)
- `morning_enhanced.md` (1.8KB)
- `news_intraday_20260519_0930.json` (18.4KB)
- `news_intraday_20260519_1000.json` (10.4KB)
- `news_intraday_20260519_1030.json` (14.3KB)
- `news_intraday_20260519_1100.json` (7.2KB)

... 还有 184 个文件

## 队列积压 (未蒸馏)

- 2026-05-18: sentinel_status.json
- 2026-05-18: git_push.log
- 2026-05-19: closing_review.json
- 2026-05-19: morning_enhanced.json
- 2026-05-19: sentinel_status.json

... 还有 22 条

---

## Claude 处理指令

读取本简报后，按以下步骤蒸馏:

1. 读取每个「待蒸馏文件」的内容
2. 判断是否产生可复用知识:
   - **错误模式**: 新的报错类型/根因/修复方式 → 更新 rules/ 或 memory/feedback/
   - **市场规律**: 被验证的技术形态/板块轮动规律 → 更新 knowledge/stocks/
   - **决策优化**: 交易决策中暴露的认知偏差 → 更新 rules/ 或 skills/
   - **数据发现**: API 变化/新数据源/数据质量问题 → 更新 knowledge/tools/
3. 如产生新知识 → 更新对应的 rules/skills/memory 文件 → 标记队列条目为 done
4. 如无新知识 → 标记队列条目为 skipped
5. 推送更新到 GitHub (git_auto_push.py)

> 生成时间: 2026-05-19 15:47