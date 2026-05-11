---
name: harness-audit
description: 诊断 Harness 六大模块健康度，给出评分和改进建议
allowed_tools: ["Read", "Grep", "Glob", "Bash"]
---

# /harness-audit — Harness 六大模块健康诊断

调用 Harness 健康检查脚本，对六大模块评分并给出改进建议。

## 执行

```bash
python ~/.claude/scripts/harness-check.py
```

根据输出分析短板，给出 1-2 条具体改进步骤。

## 六大模块

| 模块 | 检查项 |
|------|--------|
| 上下文工程 | settings/rules/memory 完整度 |
| 工具编排 | ToolSearch + MCP + 权限白名单 |
| 验证机制 | PostToolUse lint + Stop hook |
| 状态管理 | git 状态 + agent/规则数量 |
| 可观测性 | Stop 日志 + 诊断输出 |
| 人类接管 | 权限模式 + 白名单覆盖 |

## 输出

评分 + 最短板 + 具体改进步骤
