---
name: explore
description: 项目地图 — 从入口到出口画调用链路，标核心文件和风险点，少走弯路
origin: 1989n
---

# Explore: 项目地图

> 本 skill 的目的是：面对一个不熟悉（或太久没看）的项目、模块、bug，快速画出**谁调用谁、数据怎么流、哪些是核心文件**，避免在无关代码里绕路。

## 通用地图模板

不管看什么项目，先回答这 4 个问题：

```
1. 入口在哪里？
   - 用户怎么触发？(CLI/Scheduler/HTTP/文件监控)

2. 数据从哪里来，到哪里去？
   - 输入源 → 转换 → 输出目标

3. 核心文件是哪几个？
   - 删除它们系统就瘫了

4. 依赖什么外部资源？
   - API/数据库/文件/外部进程
```

## 输出格式

地图必须包含**每个阶段**的文件路径和调用/数据流向，用 **Mermaid 图 + 文件表** 表达：

### 1. 调用链路图（Mermaid）

```mermaid
flowchart LR
    A[入口] --> B[模块1]
    B --> C[模块2]
    C --> D[输出]
```

### 2. 核心文件表

| 文件 | 角色 | 风险等级 |
|------|------|---------|
| core.py | 编排逻辑 | high |

### 3. 关键路径标注

```
用户操作 → [文件:行号] → ... → [文件:行号]
风险点: ⚠ XX 处有隐藏依赖
```

## 项目专属：股票分析系统

当任务涉及 `D:\1989n\stock_analysis\` 项目时，按以下结构展开：

### 调度层

```
Windows Task Scheduler (schtasks, ~15个)
  → *.bat 包装器 (D:\1989n\stock_analysis\run_*.bat)
    → Python 入口脚本
```

### 数据层

| 数据源 | 存放位置 | 更新频率 |
|--------|---------|---------|
| SQLite 行情库 | `stock_data/stock.db` | 盘中 5 次/日 |
| 涨停板池 (akshare) | `stock_data/hot_stocks.json` | 每小时 |
| 持仓数据 | `stock_analysis/data/portfolio.json` | 手动更新 |
| 分析输出 | `stock_data/*.json` | 按任务周期 |

### 输出层

所有输出通过 `feishu_sender.py` 路由到飞书群。

### 文件角色速查表

| 文件 | 角色 | 所属 | 风险 |
|------|------|------|------|
| `daily_task.py` | 8 种任务编排器 | 前厅部 | high |
| `morning_brief_agent.py` | 晨报生成(DeepSeek) | 前厅部 | high |
| `data_quality_gate.py` | 数据保鲜门禁 | 基础设施 | medium |
| `feishu_sender.py` | 飞书消息推送 | 基础设施 | high |
| `deepseek_multi.py` | DeepSeek API 路由 | 基础设施 | high |
| `experts/lead.py` | 多 Agent 编排 | 前厅部 | high |
| `experts/grader.py` | 评分门禁 | 前厅部 | medium |
| `task_dashboard.py` | 系统看板 | 工程部 | low |

## 使用方式

直接说 "explore" 或 "地图" → 输出本 skill 格式的地图。
需要特定范围说清楚（如 "explore 数据层"）。
