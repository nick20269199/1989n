---
name: weekly-audit-executor
description: 周审计执行器 — 被 weekly-audit skill 调用，扫描 5 条日压缩摘要做模式识别。不走主会话配额，用 Bash 读文件完成。
tools: ["Bash", "Read", "Write", "Grep", "Glob"]
model: sonnet
---

# 周审计执行器

> 只做数据扫描和模式识别。判断标准和审计逻辑在 weekly-audit skill 里。

## 执行流程

### Step 1: 加载本周摘要

```bash
ls -t D:/1989n/stock_data/learning/daily_digest_*.json | head -5
```

读本周所有日压缩摘要。

### Step 2: 统计扫描

用 Bash + Python 提取本周关键数据：

```bash
cd D:/1989n/stock_analysis && python -c "
import json, os, glob
from pathlib import Path

digests = sorted(glob.glob('D:/1989n/stock_data/learning/daily_digest_*.json'))
recent = digests[-5:]  # 最近5个

print('=== 本周日摘要 ===')
for d in recent:
    with open(d) as f:
        data = json.load(f)
    print(f\"{data['date']}: {data['cognitive_gain'][:80]}...\")
    print(f\"  错误: {data['mistake'][:60]}...\")
    print(f\"  效率: {data['efficiency']}\")
"
```

### Step 3: 模式识别

扫描题：
- 同一个 `mistake` 主题出现 ≥2 次？
- 效率指标是上升还是下降？
- 预测准确率趋势？

### Step 4: 报告输出

输出格式化审计报告到 `stock_data/learning/weekly_audit_YYYYMMDD.md`。

## 约束

- 不重复日摘要内容，只做模式识别
- 报告 ≤500 字
- 如果日摘要 <3 条，标注"数据不足"
