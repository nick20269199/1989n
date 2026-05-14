# 蒸馏简报 — 2026-05-14

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (9.0KB)
- `git_push.log` (512.8KB)
- `morning_enhanced.json` (8.6KB)
- `sentinel_status.json` (1.3KB)

共 4 个文件待蒸馏

## 今日其他产出

- `analysis_30min_20260514_1130.json` (1.6KB)
- `analysis_30min_20260514_1130.md` (0.6KB)
- `analysis_30min_20260514_1500.json` (1.6KB)
- `analysis_30min_20260514_1500.md` (0.6KB)
- `analysis_overnight_20260514_2330.json` (0.6KB)
- `analysis_overnight_20260514_2330.md` (0.2KB)
- `call_auction_20260514_0956.json` (13.6KB)
- `closing_review.log` (19.2KB)
- `closing_review.md` (1.4KB)
- `distillation_brief.md` (2.0KB)
- `distill_queue.json` (2.4KB)
- `intraday_close.log` (43.0KB)
- `intraday_midday.log` (35.9KB)
- `intraday_report_latest.md` (0.6KB)
- `morning_enhanced.md` (1.7KB)
- `news_evening_20260514_2200.json` (8.4KB)
- `news_intraday_20260514_1000.json` (7.3KB)
- `news_intraday_20260514_1030.json` (2.0KB)
- `news_intraday_20260514_1100.json` (2.0KB)
- `news_intraday_20260514_1300.json` (7.7KB)

... 还有 78 个文件

## 队列积压 (未蒸馏)

- 2026-05-13: git_push.log
- 2026-05-14: closing_review.json
- 2026-05-14: morning_enhanced.json
- 2026-05-14: sentinel_status.json
- 2026-05-14: git_push.log

... 还有 14 条

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

> 生成时间: 2026-05-14 23:47