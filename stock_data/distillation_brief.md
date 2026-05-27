# 蒸馏简报 — 2026-05-27

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (7.5KB)
- `last_error.txt` (0.7KB)

共 2 个文件待蒸馏

## 今日其他产出

- `analysis_30min_20260527_1130.json` (1.9KB)
- `analysis_30min_20260527_1130.md` (0.6KB)
- `analysis_30min_20260527_1500.json` (1.5KB)
- `analysis_30min_20260527_1500.md` (0.6KB)
- `call_auction.log` (6.1KB)
- `call_auction_20260527_0926.json` (85.1KB)
- `channel_health_latest.json` (0.1KB)
- `closing_review.log` (38.8KB)
- `closing_review.md` (1.3KB)
- `cninfo_20260527_0839.json` (0.1KB)
- `cognitive_agent.log` (86.8KB)
- `concept_mapping.json` (4.8KB)
- `distillation_brief.md` (2.2KB)
- `feishu_outbox.jsonl` (0.0KB)
- `health_check.log` (3.0KB)
- `hot_stocks.json` (3.0KB)
- `hot_stocks.log` (320.5KB)
- `intraday_close.log` (60.1KB)
- `intraday_midday.log` (49.3KB)
- `mitm_capture_script.py` (1.1KB)

... 还有 4468 个文件

## 队列积压 (未蒸馏)

- 2026-05-26: last_error.txt
- 2026-05-26: sentinel_status.json
- 2026-05-26: git_push.log
- 2026-05-27: closing_review.json
- 2026-05-27: last_error.txt

... 还有 47 条

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

> 生成时间: 2026-05-27 15:47