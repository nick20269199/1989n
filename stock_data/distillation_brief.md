# 蒸馏简报 — 2026-05-26

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (9.0KB)
- `last_error.txt` (0.6KB)
- `sentinel_status.json` (2.0KB)

共 3 个文件待蒸馏

## 今日其他产出

- `analysis_30min_20260526_1130.json` (1.9KB)
- `analysis_30min_20260526_1130.md` (0.6KB)
- `analysis_30min_20260526_1500.json` (1.7KB)
- `analysis_30min_20260526_1500.md` (0.6KB)
- `call_auction.log` (4.7KB)
- `call_auction_20260526_0926.json` (170.4KB)
- `channel_health_latest.json` (0.1KB)
- `closing_review.log` (38.7KB)
- `closing_review.md` (1.4KB)
- `cninfo_20260526_0800.json` (0.1KB)
- `cognitive_agent.log` (75.2KB)
- `decision_backtest_report.json` (10.1KB)
- `distillation_brief.md` (2.0KB)
- `distill_queue.json` (8.1KB)
- `feishu_inbox.jsonl` (0.4KB)
- `feishu_outbox.jsonl` (1.4KB)
- `feishu_sent.jsonl` (2.1KB)
- `health_check.log` (2.2KB)
- `hot_stocks.json` (9.8KB)
- `hot_stocks.log` (317.7KB)

... 还有 4196 个文件

## 队列积压 (未蒸馏)

- 2026-05-25: schemas/sentinel_status.json.schema.json
- 2026-05-25: git_push.log
- 2026-05-26: closing_review.json
- 2026-05-26: last_error.txt
- 2026-05-26: sentinel_status.json

... 还有 44 条

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

> 生成时间: 2026-05-26 15:47