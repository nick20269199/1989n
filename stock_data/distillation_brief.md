# 蒸馏简报 — 2026-05-23

## 待蒸馏文件 (匹配规则)

- `last_error.txt` (0.5KB)

共 1 个文件待蒸馏

## 今日其他产出

- `call_auction.log` (1.6KB)
- `cognitive_agent.log` (51.4KB)
- `decision_backtest_report.json` (0.3KB)
- `distillation_brief.md` (2.0KB)
- `distill_queue.json` (4.5KB)
- `dreamer_report.json` (1.1KB)
- `health_check.log` (0.6KB)
- `hot_stocks.json` (14.9KB)
- `hot_stocks.log` (307.5KB)
- `intraday_midday.log` (43.6KB)
- `morning_brief_agent_latest.json` (0.2KB)
- `morning_brief_agent_latest.md` (7.4KB)
- `news_manual_20260523_0800.json` (29.1KB)
- `nightly_health.log` (7.9KB)
- `recon_report_20260523.md` (5.3KB)
- `task_dashboard.md` (2.9KB)
- `vv_radar.log` (5.4KB)
- `cognitive_output/morning_brief_20260523_0838.md` (7.4KB)
- `intel/intel_deduce_2026-05-23.json` (0.6KB)
- `intel/intel_deduce_2026-05-23.md` (0.3KB)

... 还有 5309 个文件

## 队列积压 (未蒸馏)

- 2026-05-21: closing_review.json
- 2026-05-21: git_push.log
- 2026-05-22: closing_review.json
- 2026-05-22: git_push.log
- 2026-05-23: last_error.txt

... 还有 31 条

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

> 生成时间: 2026-05-23 14:58