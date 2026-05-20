# 蒸馏简报 — 2026-05-20

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (8.8KB)
- `git_push.log` (561.3KB)
- `last_error.txt` (0.2KB)

共 3 个文件待蒸馏

## 今日其他产出

- `analysis_30min_20260520_1130.json` (1.6KB)
- `analysis_30min_20260520_1130.md` (0.6KB)
- `analysis_30min_20260520_1500.json` (1.6KB)
- `analysis_30min_20260520_1500.md` (0.6KB)
- `analysis_overnight_20260520_2330.json` (0.6KB)
- `analysis_overnight_20260520_2330.md` (0.2KB)
- `call_auction_20260520_0926.json` (1.8KB)
- `closing_review.log` (25.7KB)
- `closing_review.md` (1.3KB)
- `cognitive_agent.log` (11.1KB)
- `concept_mapping.json` (5.3KB)
- `distillation_brief.md` (2.0KB)
- `distill_queue.json` (3.9KB)
- `evening.log` (1.4KB)
- `hot_stocks.json` (14.8KB)
- `hot_stocks.log` (281.1KB)
- `intraday_close.log` (48.6KB)
- `intraday_midday.log` (41.4KB)
- `morning_brief_latest.json` (0.2KB)
- `morning_brief_latest.md` (7.7KB)

... 还有 1127 个文件

## 队列积压 (未蒸馏)

- 2026-05-19: sentinel_status.json
- 2026-05-19: git_push.log
- 2026-05-20: closing_review.json
- 2026-05-20: last_error.txt
- 2026-05-20: git_push.log

... 还有 26 条

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

> 生成时间: 2026-05-20 23:47