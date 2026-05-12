# 蒸馏简报 — 2026-05-12

## 待蒸馏文件 (匹配规则)

- `closing_review.json` (9.0KB)
- `git_push.log` (230.0KB)
- `last_error.txt` (0.0KB)
- `morning_enhanced.json` (8.7KB)
- `sentinel_status.json` (1.3KB)

共 5 个文件待蒸馏

## 今日其他产出

- `adversarial_review_20260512.md` (5.9KB)
- `analysis_30min.json` (1.8KB)
- `analysis_30min_20260512_1130.json` (1.6KB)
- `analysis_30min_20260512_1130.md` (0.6KB)
- `analysis_30min_20260512_1248.md` (2.5KB)
- `analysis_30min_20260512_1500.json` (1.6KB)
- `analysis_30min_20260512_1500.md` (0.6KB)
- `analysis_overnight_20260512_0735.json` (0.5KB)
- `analysis_overnight_20260512_0735.md` (3.8KB)
- `a_stock_list.json` (339.5KB)
- `call_auction_20260512_0939.json` (13.6KB)
- `call_auction_20260512_0945.json` (5.5KB)
- `call_auction_20260512_0949.json` (11.5KB)
- `call_auction_20260512_0951.json` (13.6KB)
- `call_auction_20260512_0953.json` (13.6KB)
- `call_auction_20260512_0955.json` (13.6KB)
- `closing_quotes.json` (3.0KB)
- `closing_review.log` (18.1KB)
- `closing_review.md` (1.4KB)
- `concept_mapping.json` (5.1KB)

... 还有 4296 个文件

## 队列积压 (未蒸馏)

- 2026-05-12: closing_review.json
- 2026-05-12: last_error.txt
- 2026-05-12: morning_enhanced.json
- 2026-05-12: sentinel_status.json
- 2026-05-12: git_push.log

... 还有 6 条

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

> 生成时间: 2026-05-12 23:47