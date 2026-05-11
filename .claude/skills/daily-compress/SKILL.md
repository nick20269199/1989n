---
name: daily-compress
description: 每日复盘压缩 v2 — 收盘后将今日对话+市场数据压缩为高维→低维 5 段认知摘要。Cron 15:37 触发。
---

# 每日复盘压缩 v2 (Daily Compress)

> 收盘后 15:37 执行。5 段结构：天时定位 → 比率异常 → 预期差 → 凝练规则 → 自检。

## 执行步骤

### Step 1: 回顾今日对话

从当前会话中提取：
- 今天讨论了哪些交易/分析话题？
- 我做了什么判断？哪次判断被纠正了？
- 读了哪些文件？哪些读了但没用上？
- 用户给了什么反馈（纠正/确认/新偏好）？

### Step 2: 运行 v2 日压缩管道

```bash
cd D:/1989n/stock_analysis && python daily_compress.py full \
  --date "$(date +%Y%m%d)" \
  --mistake "今日犯的核心错误及根因" \
  --feedback "用户今日纠正/确认的内容" \
  --ego-challenge "今日证据是否挑战了核心假设"
```

这会自动执行：
1. **天时定位**：读取市场数据 → 判定周期阶段（冰点/启动/主升/高潮/衰退/混沌）
2. **比率快照**：记录 8 个关键比率的当日值，计算 z-score，触发偏离警报
3. **预期差分析**：基于周期阶段，判断市场共识与现实之间可能存在的偏差
4. **凝练规则**：认知增益被强制转化为 适用条件+执行动作+失效信号
5. **写摘要**：产出 v2 格式的 5 段日摘要

### Step 3: 手动填补充字段

Python 脚本完成数据层面的压缩后，我需要补充需要主观判断的字段：

1. **凝练规则**：今天的认知增益中，哪些可以凝练为可执行规则？
   - 适用条件必须明确（什么周期阶段？什么市场环境？）
   - 执行动作必须可操作（具体做什么？）
   - 失效信号必须可检测（什么情况下这条规则不再适用？）

2. **自检字段**：
   - `ego_challenge`：今天有什么证据挑战了我的核心假设？
   - `discipline_breach`：是否做了模式外操作？
   - `mistake_root_cause`：知识盲区/逻辑跳跃/惯性输出/数据缺失/情绪干扰？

### Step 4: 写规则

对每条已凝练的规则：
```bash
cd D:/1989n/stock_analysis && python -c "
from daily_compress import condense_rule, commit_rule
import json
rule = condense_rule(
    insight_text='...',
    cycle_stage='...',
    source_data='...'
)
rule['condition'] = '当XX环境下，XX指标出现XX变化时'
rule['action'] = '执行XX操作'
rule['failure_signal'] = '如果XX条件不满足，或出现XX信号，则规则失效'
rule['is_condensed'] = True
rid = commit_rule(rule)
print(f'规则已提交: {rid}')
"
```

### Step 5: 更新日索引

`daily_digest_index.json` 由 `write_digest_v2()` 自动更新。

## 输出格式 (v2)

```json
{
  "version": 2,
  "date": "YYYY-MM-DD",
  "cycle_stage": {"stage": "主升", "confidence": 0.8, "signals": [...], "strategy_hint": "...", "next_stage_risk": "..."},
  "ratio_alerts": {"triggered": {"炸板率": {"value": 0.35, "z_score": 2.3}}, "collision_focus": "..."},
  "expectation_gaps": [{"dimension": "...", "consensus": "...", "potential_gap": "..."}],
  "rules_today": [{"condition": "...", "action": "...", "failure_signal": "...", "is_condensed": true}],
  "self_check": {"mistake": "...", "mistake_root_cause": "...", "ego_challenge": "...", "discipline_breach": "..."}
}
```

## 约束

- 每条凝练规则必须三元组填满才标记 `is_condensed: true`
- 未凝练的规则不写入规则库（但记录在日摘要中供周审计追踪）
- 如果用户在 15:37 正在使用 → 延迟到用户空闲时执行
- 管道执行不超 2 分钟
- 周末/非交易日不执行
