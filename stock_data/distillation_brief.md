# 蒸馏简报 — 2026-05-18

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (9.0KB)
- `last_error.txt` (0.4KB)
- `morning_enhanced.json` (8.2KB)
- `sentinel_status.json` (1.3KB)

共 4 个文件待蒸馏

## 今日其他产出

- `analysis_30min_20260518_1130.json` (1.4KB)
- `analysis_30min_20260518_1130.md` (0.6KB)
- `analysis_30min_20260518_1500.json` (1.4KB)
- `analysis_30min_20260518_1500.md` (0.6KB)
- `call_auction_20260518_0926.json` (8.1KB)
- `call_auction_20260518_0956.json` (12.6KB)
- `channel_health_latest.json` (0.3KB)
- `closing_review.log` (23.4KB)
- `closing_review.md` (1.4KB)
- `concept_mapping.json` (4.0KB)
- `concept_stocks.json` (8.9KB)
- `data_guard_report.json` (1.3KB)
- `intraday_close.log` (46.6KB)
- `intraday_midday.log` (39.5KB)
- `morning_brief.log` (88.2KB)
- `morning_brief_latest.json` (0.8KB)
- `morning_brief_latest.md` (4.4KB)
- `morning_enhanced.md` (1.7KB)
- `news_intraday_20260518_0930.json` (5.0KB)
- `news_intraday_20260518_1000.json` (4.0KB)

... 还有 116 个文件

## 队列积压 (未蒸馏)

- 2026-05-14: git_push.log
- 2026-05-18: closing_review.json
- 2026-05-18: last_error.txt
- 2026-05-18: morning_enhanced.json
- 2026-05-18: sentinel_status.json

... 还有 18 条

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

> 生成时间: 2026-05-18 15:47