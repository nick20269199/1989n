# 蒸馏简报 — 2026-05-25

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (7.2KB)
- `git_push.log` (577.2KB)
- `last_error.txt` (3.8KB)
- `sentinel_status.json` (2.0KB)
- `schemas/closing_review.json.schema.json` (0.4KB)
- `schemas/sentinel_status.json.schema.json` (0.3KB)

共 6 个文件待蒸馏

## 今日其他产出

- `analysis_30min_20260525_1130.json` (1.4KB)
- `analysis_30min_20260525_1130.md` (0.5KB)
- `analysis_30min_20260525_1500.json` (1.3KB)
- `analysis_30min_20260525_1500.md` (0.5KB)
- `analysis_overnight_20260525_2337.json` (0.6KB)
- `analysis_overnight_20260525_2337.md` (0.2KB)
- `call_auction.log` (3.6KB)
- `call_auction_20260525_0926.json` (8.6KB)
- `channel_health_latest.json` (0.1KB)
- `closing_review.log` (36.7KB)
- `closing_review.md` (1.2KB)
- `cninfo_20260525_0800.json` (0.1KB)
- `cognitive_agent.log` (72.0KB)
- `decision_backtest_report.json` (0.3KB)
- `distillation_brief.md` (2.1KB)
- `distill_queue.json` (7.7KB)
- `dreamer_report.json` (1.1KB)
- `evening.log` (15.1KB)
- `feishu_inbox.jsonl` (0.4KB)
- `feishu_outbox.jsonl` (0.4KB)

... 还有 4228 个文件

## 队列积压 (未蒸馏)

- 2026-05-25: last_error.txt
- 2026-05-25: sentinel_status.json
- 2026-05-25: schemas/closing_review.json.schema.json
- 2026-05-25: schemas/sentinel_status.json.schema.json
- 2026-05-25: git_push.log

... 还有 41 条

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

> 生成时间: 2026-05-25 23:47