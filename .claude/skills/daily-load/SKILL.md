---
name: daily-load
description: 晨间认知加载 v2 — 开盘前加载昨日压缩摘要/周期阶段/规则库状态/比率警报/今日问题。Cron 08:07 触发。
---

# 晨间认知加载 v2 (Daily Load)

> 不只是"告诉我有这些文件"，是让我接下来全天的思考默认带着：当前周期阶段、昨日凝练规则、活跃比率警报。

## 执行步骤

### Step 1: 加载昨日压缩摘要

```bash
ls -t D:/1989n/stock_data/learning/daily_digest_*.json 2>/dev/null | head -1
```

读最新的 v2 日摘要，提取 5 段信息：

**Tier 1 — 周期阶段**
- 当前处于哪个周期阶段？置信度多少？
- 什么信号支持这个判断？
- 策略提示是什么？（冰点=极值反转 / 启动=追强 / 主升=跟随 / 高潮=警惕 / 衰退=空仓）
- 下一阶段风险是什么？

**Tier 2 — 比率警报**
- 昨日哪些比率触发了警报（z-score ≥ 2）？
- 今日碰撞关注方向是什么？（由周期阶段决定）
- 数据质量如何？（from_closing / from_intraday / estimated）

**Tier 3 — 预期差**
- 昨日识别了哪些市场共识与现实之间的偏差？
- 今日需要验证什么？

**Tier 4 — 凝练规则**
- 昨日凝练了哪些新规则？
- 哪些旧规则被触发？被验证？
- 今日应该执行哪些规则？

**Tier 5 — 自检**
- 昨日犯了什么错误？根因是什么？
- ego_challenge：有没有挑战核心假设的证据？
- discipline_breach：是否做了模式外操作？

### Step 2: 加载规则库状态（含回测结果）

```bash
cd D:/1989n/stock_analysis && python -c "
from daily_compress import load_json, RULES_FILE
from rule_verifier import verify_rule, load_ratio_history
rules = load_json(RULES_FILE).get('rules', [])
active = [r for r in rules if r.get('is_condensed')]
retired = [r for r in rules if r.get('status') in ('retired', 'stale')]
print(f'活跃规则: {len(active)} 条, 退役: {len(retired)} 条')
for r in active[-5:]:
    verified = r.get('verified_count', 0)
    accuracy = r.get('verification_result', {}).get('accuracy', 'N/A')
    print(f'  [{r[\"cycle_stage\"]}] {r[\"condition\"][:60]} → 验证:{verified}次 准确:{accuracy}')
"
```

### Step 3: 加载今日研究问题

读 `stock_data/learning/open_questions.json`：
- 取优先级最高且状态为 open 的问题
- 该问题应在当前周期阶段的背景下被研究
- 优先级会随周期阶段变化：冰点时重点研究"错杀识别"，主升时重点研究"龙头持续性"

### Step 4: 比率基线检查

```bash
cd D:/1989n/stock_analysis && python -c "
from daily_compress import load_json, RATIO_BASELINES_FILE
import json
data = load_json(RATIO_BASELINES_FILE)
entries = data.get('entries', [])
if entries:
    latest = entries[-1]
    print(f'最近快照: {latest[\"date\"]}')
    for name, info in latest.get('ratios', {}).items():
        alert = info.get('alert', 'normal')
        if alert == 'triggered':
            print(f'  [ALERT] {name}: z_score={info.get(\"z_score\", 0)}')
"
```

### Step 5: 预测追踪状态（v3 新增）

```bash
cd D:/1989n/stock_analysis && python forecast_closer.py --report 2>&1 | head -15
```

关注：
- 准确率是否在下降（系统性的研究质量退化？）
- 到期待验证的预测数量（是否需要手动验证？）

### Step 6: 检查收件箱 (v5 新增)

**先拉取远程更新** (用户可能从手机/GitHub 加了东西):
```bash
cd D:/1989n && git pull --rebase 2>&1
```

读 `inbox/` 目录下所有 `.md` 文件:
- `ideas.md` — 逐条读取未标记 `[processed]` 的条目 → 有价值的纳入当日分析/知识库
- `links.md` — 逐个读取链接 → 判断是否值得深入研究 → 有价值的内容提取到 `knowledge/`
- `questions.md` — 逐个读取问题 → 能马上回答的直接回答 → 需要研究的加入 `open_questions.json`
- `inbox/images/` — 有新图片 → 用 vision.py 分析 → 纳入 context

处理完的条目标记 `[processed]`，提交推送。

### Step 7: 蒸馏简报处理 (v4)

检查 `stock_data/distillation_brief.md`:
- 如果文件存在且「待蒸馏文件」非空:
  - 读取每个待蒸馏文件内容
  - 判断是否产生可复用知识 → 更新 rules/skills/memory
  - 更新 `distill_queue.json` 中对应条目状态 (done/skipped)
- 如果无新知识待蒸馏 → 跳过

蒸馏产出落点规则:
| 发现类型 | 落点 |
|---------|------|
| 新错误模式/修复方式 | `memory/feedback/` |
| 被验证的市场规律 | `memory/knowledge/stocks/` |
| 交易决策中的认知偏差 | `rules/` 或对应 skill |
| API/数据源变化 | `memory/knowledge/tools/` |
| 新交易规则/策略 | `stock_data/trading_rules.json` |

### Step 7: 注入上下文

以结构化格式输出到当前会话：

```
=== 今日认知加载 v3 ===
周期阶段: [冰点/启动/主升/高潮/衰退/混沌] (置信度: X%)
策略提示: [基于阶段的策略建议]
下阶段风险: [可能转变的方向]

昨日凝练规则(N条):
  - [条件] → [动作] (失效: [信号])

比率警报(N个):
  - [比率名]: z_score = X.X (偏离方向)

预期差关注:
  - [维度]: 共识认为X，但实际可能是Y

预测追踪:
  - 总预测: N条, 准确率: X%
  - 到期待验证: N条

规则回测:
  - 活跃规则: N条, 退役/失效: M条
  - 本周触发回测: K条, 平均准确率: X%

今日追踪问题: [问题文本]
今日碰撞方向: [阶段决定的碰撞焦点]
昨日错误避免: [错误+根因]
Ego Check: [昨日是否有挑战核心假设的证据]
===
```

这个信息应作为我全天所有分析的默认视角。每次分析前，先问：在当前周期阶段，这个分析有意义吗？

## 约束

- 不占用超过 30 秒
- 如果 digest 文件不存在，跳过往期加载，只做周期判定和碰撞方向确定
- 如果是周一，额外加载上周六的周审计结果
- 如果周期阶段置信度 < 0.4，标注"信号不明确，以混沌模式运行"
