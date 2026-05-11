# 蒸馏简报 — 2026-05-11

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (7.4KB)
- `git_push.log` (0.0KB)
- `last_error.txt` (1.1KB)
- `morning_enhanced.json` (7.9KB)
- `sentinel_status.json` (1.3KB)
- `trading_rules.json` (3.1KB)

共 6 个文件待蒸馏

## 今日其他产出

- `analysis_30min_20260511_1130.json` (1.3KB)
- `analysis_30min_20260511_1130.md` (0.5KB)
- `analysis_30min_20260511_1500.json` (1.3KB)
- `analysis_30min_20260511_1500.md` (0.5KB)
- `analysis_overnight_20260511_2330.json` (0.2KB)
- `analysis_overnight_20260511_2330.md` (0.1KB)
- `backtest_results.json` (0.3KB)
- `bs_full_analysis.json` (2.5KB)
- `call_auction_20260511_0956.json` (13.4KB)
- `closing_review.log` (17.0KB)
- `closing_review.md` (1.4KB)
- `concept_mapping.json` (3.7KB)
- `data_guard_report.json` (1.7KB)
- `hot_stocks.json` (0.1KB)
- `hot_stocks.log` (260.4KB)
- `intraday_close.log` (40.3KB)
- `intraday_midday.log` (33.2KB)
- `morning_brief.log` (38.0KB)
- `morning_brief_latest.json` (2.7KB)
- `morning_brief_latest.md` (1.6KB)

... 还有 439 个文件

## 队列积压 (未蒸馏)

- 2026-05-11: git_push.log
- 2026-05-11: last_error.txt
- 2026-05-11: morning_enhanced.json
- 2026-05-11: sentinel_status.json
- 2026-05-11: trading_rules.json

... 还有 1 条

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

> 生成时间: 2026-05-11 23:47