# 五部+枢部 运营规范 v1

> 最后更新: 2026-05-28
> 此文档为各部门工作的权威参考标准，所有部门执行必须按此规范。
> 中介声明: 基于代码审计和运行时配置分析，反映系统当前实际状态。

---

## 一、枢部（中心协调层）

枢部不是独立部门，而是嵌入在 Claude Code 运行时和自动化脚本中的**协调机制**。任何部门的工作都在枢部的门禁和调度下执行。

### 1.1 通信协议

| 项目 | 内容 |
|------|------|
| **协议文件** | `stock_analysis/dept_status_protocol.py` |
| **通信方式** | JSON 文件协议（无服务、无外部依赖） |
| **状态目录** | `stock_data/status/{dept}_status.json` |
| **依赖定义** | `stock_data/status/dependencies.json` |
| **状态发布函数** | `publish_status(dept_name, status_dict)` → 自动注入 timestamp |
| **状态读取函数** | `read_status(dept_name)` → 读自身状态 / `read_other_dept(dept_name)` → 读别的部门 |
| **新鲜度检查** | `is_status_fresh(status, max_hours=24)` |
| **设计原则** | 软依赖：状态缺失时 advisory 继续，不阻塞 |

### 1.2 部门注册表

| 部门名 | 系统名 | 依赖 |
|--------|--------|------|
| 前厅部 | front-office | engineering |
| 情报部 | intelligence | front-office, engineering |
| 工程部 | engineering | （无） |
| 研发部 | rd | engineering, front-office |
| 读书郎 | reader | （无） |

### 1.3 消息路由

| 项目 | 内容 |
|------|------|
| **路由实现** | `stock_analysis/dept_handlers.py` → `route_message()` |
| **第1层（精确）** | `@部门名` in 消息 → 直接路由到对应 handler |
| **第2层（模糊）** | 关键词命中≥2个 → 得分最高部门推测路由 |
| **第3层（兜底）** | 都不匹配 → DeepSeek Agent 通用问答 |
| **部门关键词** | 见下方各部门「触发关键词」 |

### 1.4 操作门禁（OpsGate）

| 门禁 | 实现 | 触发点 | 作用 |
|------|------|--------|------|
| **预检门禁** | `dept_ops.py` → `preflight()` | 每次部门输出前 | 检查依赖部门状态是否健康，不健康→降级/阻塞 |
| **交叉门禁** | `dept_ops.py` → `crosscheck_all_deps()` | 每次部门输出前 | 读取依赖部门最新状态，报告健康度/新鲜度/issues |
| **来源声明** | `dept_ops.py` → `source_footer()` | 每次部门输出后 | 强制携带数据源+新鲜度+交叉校验状态（U4中介声明） |
| **Excel交叉验证** | `dept_ops.py` → `crosscheck_excel_vs_portfolio()` | 前厅部输出 | 逐笔成交 vs portfolio.json 持仓比对 |

### 1.5 门禁／挂钩自动化（settings.json）

| 钩子点 | 触发条件 | 执行命令 | 门禁类型 |
|--------|----------|----------|----------|
| **SessionStart** | 会话开始 | `session_hook.py start` | 会话追踪 |
| **SessionEnd** | 会话结束 | `session_hook.py stop` | 会话关闭 |
| **PostToolUseFailure** | Bash 执行失败 | `tools/failure_analyzer.py --from-file` | 失败自动分析 |
| **PostToolUse** | Edit/Write | `tools/import_gate.py --changed-only --json` | Gate 1: 语法门禁 |
| **PostToolUse** | Edit/Write | `tools/auto_verify.py` | Gate 3: 交付自验 |
| **PostToolUse** | Edit/Write | 内联验证提醒 | 验证提醒 |

### 1.6 质量门禁工具

| 门禁 | 文件 | 功能 | 触发条件 |
|------|------|------|----------|
| **Gate 1: 语法门禁** | `tools/import_gate.py` | `compile()` 检查 .py 语法 + 路径拼接扫描 | 每次 Edit/Write |
| **Gate 2: Schema门禁** | `tools/schema_gate.py` | 校验 JSON 字段类型/必需字段/保鲜时长 | 可选（手动） |
| **Gate 3: 交付自验** | `tools/auto_verify.py` | 改代码后自动跑文件→测试映射表中关联测试 | 每次 Edit/Write |
| **数据保鲜门禁** | `data_quality_gate.py` | 输出前检查 freshness，过期→改发 STALE 告警 | 所有输出 |
| **部门预检** | `dept_preflight.py` | 跨部门依赖检查+数据新鲜度+循环依赖检测 | 部门操作前 |

### 1.7 任务队列（B类任务）

| 项目 | 内容 |
|------|------|
| **队列文件** | `stock_data/task_queue.json` |
| **用途** | 需要 Claude 深度参与的任务（非自动化脚本可处理） |
| **格式** | `{"id":"TK-时间戳", "dept":"部门", "task":"任务", "raw":"原文", "created":"时间", "status":"pending"}` |
| **入队机制** | `_enqueue_task(dept, task, raw_text)` |

### 1.8 飞书消息路由（7路群路由）

| 路由名 | chat_id | 用途 |
|--------|---------|------|
| main | `oc_983693a765e4284d1dc7bbeaf56cf1a9` | 主群（默认） |
| book | `oc_7884ad241159d9b39fb855592e19bb6d` | 书虫群 |
| news | `oc_879207bdeaee695505d45a85afb9bca8` | 新闻群 |
| midday | `oc_2683bbadb9721aea6e6ed585c24a3cf4` | 午盘数据群 |
| closing | `oc_afc63ec9893d4f3393bfe5cb64203e72` | 收盘数据群 |
| alerts | `oc_2c82fb2d0b3c326a3edd0e413dcb5089` | 问题组告警群 |
| overnight | `oc_fc5afbd06d624257b621f9bbad3e3bf7` | 背调小队 |

### 1.9 部门预检 CLI

| 命令 | 用途 | 退出码 |
|------|------|--------|
| `python dept_preflight.py --dept front-office` | 检查前厅部可否运行 | 0=OK / 1=注意事项 / 2=阻塞 |
| `python dept_preflight.py --dept engineering` | 检查工程部可否运行 | 同上 |
| `python dept_preflight.py --all` | 检查全部部门 | 同上 |

---

## 二、前厅部（front-office）

### 2.1 基础信息

| 项目 | 内容 |
|------|------|
| **系统名** | front-office |
| **Skill** | `.claude/skills/dept-front-office/SKILL.md` |
| **Manifest** | `.claude/memory/project/session-front-office-manifest.md` |
| **处理器** | `dept_handlers.py` → `handle_front_office()` |
| **主执行器** | `daily_task.py`（每日任务编排器） |
| **子模块规则** | `stock_analysis/CLAUDE.md` |
| **依赖部门** | engineering |
| **触发关键词** | 前厅, front, 行情, 持仓, 盈亏, 成本, 收益, 清仓, 结算, 收盘, 复盘, 盘前, 晨报, 盘中, 财务, fin, 赚, 亏 |

### 2.2 输入标准

| 数据源 | 文件路径 | 用途 | 保鲜要求 |
|--------|----------|------|----------|
| 持仓数据 | `stock_analysis/data/portfolio.json` | 当前持仓/已清仓 | ≤24h |
| 收盘复盘 | `stock_data/closing_review.json` | 上次收盘数据 | ≤24h |
| 通道健康 | `stock_data/channel_health_latest.json` | 数据通道状态 | 实时 |
| 任务哨兵 | `stock_data/sentinel_status.json` | 定时任务执行状态 | 实时 |
| 逐笔成交 | `D:/1989n/Table.xlsx` | 实际成交核对 | 手动导入 |
| 实时行情 | 多通道自动回退 → `data_source_router.py` | 盘中最新的量价/均线/资金 | 实时(≤5min) |
| 热门股票 | `stock_data/hot_stocks.json` | 市场热点 | ≤30min |
| 情报信号 | `stock_data/intel/intel_latest.json` | 情报融合信号 | ≤1h |

### 2.3 输出标准

| 输出 | 文件路径 | 触发条件 | 飞书路由 |
|------|----------|----------|----------|
| **部门状态** | `stock_data/status/front_office_status.json` | 每次操作后 | — |
| **盘前晨报** | `stock_data/morning_brief_agent_latest.json` / `.md` | 交易日 08:37 | main |
| **盘中快照** | `stock_data/analysis_30min_*.json` / `.md` | 交易日 09:03-15:03 每30分钟 | midday |
| **午盘快照** | `stock_data/analysis_30min_*.json` / `.md` | 交易日 11:30 | midday |
| **收盘复盘** | `stock_data/closing_review.json` / `.md` | 交易日 15:15 | closing |
| **技术形态扫描** | `stock_data/scan_vcp_default.json` / `scan_watchlist_tech_default.json` | 交易日 15:33 | — |
| **热门股票** | `stock_data/hot_stocks.json` | 09:35, 13:00 | main |
| **隔夜分析** | `stock_data/analysis_overnight_*.json` / `.md` | 交易日 23:37 | overnight |
| **交易计划** | `stock_data/trade_plans/plan_*.json` | 交易日 15:40 | — |
| **晚间报告** | `stock_data/report_evening_*.md` | 22:00 | — |
| **预测闭环** | `stock_data/report_forecast_closer_*.md` | 交易日 17:05 | — |
| **T+5回测** | `stock_data/report_backtest_*.md` | 交易日 16:30 | — |
| **梦境推演** | `stock_data/report_dreamer_*.md` | 交易日 17:00 | — |

### 2.4 分析维度（每次必须覆盖）

| 维度 | 内容 | 数据来源 |
|------|------|----------|
| **技术面** | 价格趋势、均线、MACD、RSI、成交量 | 实时行情 |
| **资金面** | 主力资金流向、大小单分布 | 实时行情 |
| **题材面** | 概念板块表现 | intel 信号 |
| **消息面** | 多源新闻 | intel 信号 |
| **情绪面** | 市场情绪指标 | 情绪数据 |

### 2.5 定时任务

| 任务名 | 时间 | 脚本 | 模式 |
|--------|------|------|------|
| StockAnalysis_CallAuction | 交易日 09:26 | `call_auction.py` | 集合竞价 |
| Cognitive_MorningBrief | 交易日 08:37 | `morning_brief_agent.py` | AI晨报v2 |
| StockAnalysis_HotStocks | 09:35, 13:00 | `daily_task.py hot_stocks` + `vv_radar.py` | 热门股票 |
| StockAnalysis_IntradayMidday | 交易日 11:30 | `daily_task.py intraday midday` | 午盘快照 |
| StockAnalysis_IntradayClose | 交易日 15:00 | `daily_task.py intraday close` | 收盘快照 |
| StockAnalysis_ClosingReview | 交易日 15:15 | `daily_task.py closing_review` | 收盘复盘 |
| StockAnalysis_TechScan | 交易日 15:33 | `daily_task.py tech_scan` | 技术形态扫描 |
| StockAnalysis_NightlyPlan | 交易日 15:40 | `nightly_plan.py auto` | 隔夜计划 |
| StockForecastCloser | 交易日 17:05 | `forecast_closer.py --report` | 预测闭环 |
| StockAnalysis_Evening | 22:00 | multi_step 晚间总结 | 晚间总结 |
| StockAnalysis_Overnight | 交易日 23:37 | `daily_task.py overnight` | 隔夜分析 |
| StockAnalysis_DecisionBacktest | 交易日 16:30 | `daily_task.py backtest` | T+5回测 |
| StockAnalysis_SectorCollect | 交易日 15:20 | `daily_task.py sector_collect` | 板块采集 |
| StockAnalysis_Dreamer | 交易日 17:00 | `experts/dreamer.py` | 梦境推演 |
| StockAnalysis_VVRadar | 09:35, 13:00 | `vv_radar.py fetch` | 大V雷达 |
| StockAnalysis_VVDaily | 交易日 13:10 | `vv_daily.py` | 大V日报 |

### 2.6 回调/门禁

| 触发点 | 回调动作 | 说明 |
|--------|----------|------|
| 部门输出前 | OpsGate.preflight() | 依赖部门状态预检 |
| 部门输出前 | OpsGate.crosscheck_all_deps() | 依赖部门交叉验证 |
| 部门输出后 | OpsGate.source_footer() | 来源声明（强制） |
| 涉及持仓/盈亏 | 自动注入 Excel 交叉验证 | `excel_bs_summary()` |
| 数据发送前 | `feishu_sender.py` 限流 | 15条/分钟 |

### 2.7 Agent 使用规范

前厅部的 Agent 主要用于**交易决策辅助**。当涉及以下场景时，必须调用对应 Agent：

| 场景 | Agent | 调用方式 | 说明 |
|------|-------|----------|------|
| **交易前安全审查** | `security-reviewer` | `Agent({subagent_type: "security-reviewer", prompt: "..."})` | 开仓/加仓/调仓前必须跑，审查不通过不执行 |
| **策略代码审查** | `code-reviewer` | `Agent({subagent_type: "code-reviewer", prompt: "..."})` | 修改交易逻辑/策略代码后立即审查 |
| **性能优化** | `performance-optimizer` | `Agent({subagent_type: "performance-optimizer", prompt: "..."})` | 实时行情/分析管线变慢时优化 |
| **数据断链排查** | `code-explorer` | `Agent({subagent_type: "code-explorer", prompt: "..."})` | 数据不对→追踪到数据源链源头 |

**执行规则：**
- P0: 开仓/加仓/调仓前 **必须** 先跑 adversarial-review（内置在 `/stock-deep` 等技能中）
- P0: -7% 硬止损不经过任何 Agent 审查，直接执行
- P1: 策略代码改完后必须跑 `code-reviewer`
- P2: 管线性能下降时用 `performance-optimizer` 诊断
- 涉及数据溯源的任务，优先用 `code-explorer` 查入口→路径→消费者全链

### 2.8 职责边界

| 负责 | 不负责 |
|------|--------|
| 所有交易决策相关的输出 | 数据原始采集（情报部负责） |
| 持仓管理和盈亏计算 | 基础设施维护（工程部负责） |
| 盘前/盘中/盘后全流程 | 知识管理和读书（读书郎负责） |
| 风控（硬止损-7%执行） | 新工具/脚本开发（研发部负责） |
| 2级管线（轻量/深度） | 通道故障恢复（工程部负责） |

---

## 三、情报部（intelligence）

### 3.1 基础信息

| 项目 | 内容 |
|------|------|
| **系统名** | intelligence |
| **Skill** | `.claude/skills/dept-intelligence/SKILL.md` |
| **处理器** | `dept_handlers.py` → `handle_intelligence()` |
| **核心引擎** | `intelligence_service.py` |
| **依赖部门** | front-office, engineering |
| **触发关键词** | 情报, intel, 新闻, 大V, 涨停, 情绪, 雷达 |

### 3.2 输入标准

| 数据源 | 文件路径 | 用途 | 保鲜要求 |
|--------|----------|------|----------|
| 新闻数据 | `stock_data/news_*.json` | 多源新闻（财联社/东方财富/新浪） | ≤30min |
| 概念→成分股映射 | `stock_data/concept_stocks.json` | 概念关联股票 | ≤24h |
| 概念映射 | `stock_data/concept_mapping.json` | 概念标准化 | ≤24h |
| 市场资金流向 | `stock_data/market_fund_flow_cache.json` | 全市场资金 | 实时 |
| VCP扫描结果 | `stock_data/scan_vcp_default.json` | 前厅部产出 | ≤1h |
| 持仓数据 | `stock_analysis/data/portfolio.json` | 用于关联分析 | ≤24h |
| 板块日数据 | `stock_data/sector_daily/*.json` | 板块表现 | 收盘后 |

### 3.3 输出标准

| 输出 | 文件路径 | 触发条件 | 飞书路由 |
|------|----------|----------|----------|
| **部门状态** | `stock_data/status/intelligence_status.json` | 每次操作后 | — |
| **最新情报** | `stock_data/intel/intel_latest.json` | 采集/分析后 | — |
| **盘前侦察** | `stock_data/intel/intel_recon_*.json` / `.md` | 交易日 08:32 | main |
| **收盘推演** | `stock_data/intel/intel_deduce_*.json` / `.md` | 交易日 15:35 | closing |
| **通道健康** | `stock_data/channel_health_latest.json` | 实时更新 | — |
| **新闻流** | `stock_data/news_*.json` | 采集后 | news |

### 3.4 引擎工作模式

| 模式 | CLI | 时间 | 逻辑 |
|------|-----|------|------|
| 盘前侦察 recon | `python intelligence_service.py recon` | 08:50 定时 | 新闻→概念词频→概念成分股VCP形态→持仓关联→信号产出 |
| 收盘推演 deduce | `python intelligence_service.py deduce` | 15:45 定时 | 资金流向验证新闻方向+板块表现+VCP后续潜力 |
| 状态更新 status | `python intelligence_service.py status` | 操作后 | 更新部门状态 |

### 3.5 定时任务

| 任务名 | 时间 | 脚本 | 模式 |
|--------|------|------|------|
| StockNews_Morning | 08:00 | `news_scheduler.py morning` | 早间新闻 |
| StockNews_Intraday | 09:30起每30分钟 | `news_scheduler.py intraday` | 盘中新闻 |
| StockNews_Evening | 21:55 | `news_scheduler.py evening` | 晚间新闻 |
| Intel_Recon | 交易日 08:32 | `intelligence_service.py recon` | 盘前侦察 |
| Intel_Deduce | 交易日 15:35 | `intelligence_service.py deduce` | 收盘推演 |

### 3.6 侦察逻辑（信号产出流程）

```
新闻采集 → 概念词频统计 → 概念成分股VCP形态匹配 → 持仓关联打分 → 信号分级产出
```
**输出标准**: 有信号→healthy / 无信号→degraded

### 3.7 职责边界

| 负责 | 不负责 |
|------|--------|
| 多源新闻采集（早/中/晚） | 交易决策（前厅部负责） |
| 概念→股票映射维护 | 技术形态分析（前厅部负责） |
| 市场资金流向监控 | 读书知识管理（读书郎负责） |
| 数据通道健康监测 | 基础设施/门禁（工程部负责） |
| 盘前侦察信号产出 | 新工具开发（研发部负责） |
| 收盘推演信号产出 | |

### 3.8 Agent 使用规范

情报部的 Agent 主要用于**数据源探索和采集性能优化**。当涉及以下场景时，必须调用对应 Agent：

| 场景 | Agent | 调用方式 | 说明 |
|------|-------|----------|------|
| **新数据源接入** | `code-explorer` | `Agent({subagent_type: "code-explorer", prompt: "..."})` | 接入新数据源→先探索现有接入模式再实现 |
| **采集性能问题** | `performance-optimizer` | `Agent({subagent_type: "performance-optimizer", prompt: "..."})` | 采集变慢/超时→分析瓶颈并优化 |
| **通道故障排查** | `code-explorer` | `Agent({subagent_type: "code-explorer", prompt: "..."})` | 通道挂掉→追踪路由器回退逻辑 |
| **情报代码审查** | `code-reviewer` | `Agent({subagent_type: "code-reviewer", prompt: "..."})` | 修改采集/加工逻辑后审查 |

**执行规则：**
- P1: 新数据源接入前必须用 `code-explorer` 探索已有模式
- P1: 采集代码改完后跑 `code-reviewer`
- P2: 通道回退逻辑异常时用 `code-explorer` 追踪路由树

---

## 四、工程部（engineering）

### 4.1 基础信息

| 项目 | 内容 |
|------|------|
| **系统名** | engineering |
| **Skill** | `.claude/skills/dept-engineering/SKILL.md` |
| **Manifest** | `.claude/memory/project/session-engineering-manifest.md` |
| **处理器** | `dept_handlers.py` → `handle_engineering()` |
| **Lint包装器** | `lint_wrapper.py` |
| **健康检查** | `health_check.py` |
| **依赖部门** | （无） |
| **触发关键词** | 工程, eng, 健康, lint, 错误, error, 测试, SEL, bug, 故障, pattern, pending |

### 4.2 输入标准

| 数据源 | 文件路径 | 用途 | 保鲜要求 |
|--------|----------|------|----------|
| Lint历史 | `_lint_history.json` | 递归自检历史 | 实时 |
| 最新错误 | `stock_data/last_error.txt` | 错误追踪 | 实时 |
| 通道健康 | `stock_data/channel_health_latest.json` | 通道状态 | 实时 |

### 4.3 输出标准

| 输出 | 文件路径 | 触发条件 |
|------|----------|----------|
| **部门状态** | `stock_data/status/engineering_status.json` | 每次维护/检查后 |
| **lint报告** | 内联输出 | lint时 |
| **健康检查报告** | 内联输出 + 飞书推送 | 定时检查 |

### 4.4 执行标准

| 优先级 | 标准 | 说明 |
|--------|------|------|
| **P0** | 管道可靠性 | 所有数据传输通道必须稳定 |
| **P0** | 通道监控 | 多通道自动回退（eastmoney→sina→tencent→tdx） |
| **P0** | 质量门禁 | import_gate/schema_gate/consistency_gate |
| **P0** | 错误修复 | last_error.txt 驱动修复 |
| **P1** | SEL维护 | Lint→Digest→Connect→Maintain→Prune |
| **P1** | 数据保鲜自动化 | 构建数据链并标注生态影响 |
| **P2** | 测试覆盖 | >80% |
| **P2** | 性能优化 | 瓶颈识别+优化 |

### 4.5 SEL 自进化循环

| 步骤 | 时间 | 脚本 | 说明 |
|------|------|------|------|
| Lint | 08:30 | `lint_wrapper.py` → sel_lint 6项检测 | 腐烂/draft/幽灵引用/规则脱节/Ingest未完成/缺失连接 |
| Digest | 09:00 | `sel_digest.py` | 知识消化 |
| Maintain | 09:05 | `sel_maintain.py` | 知识维护 |
| Connect | 09:10 | `sel_connect.py` | 知识连接 |
| Prune | 09:15 | `sel_prune.py` | 知识裁剪 |
| Evolve Read | 12:00 | `sel_evolve_read.py` | 进化阅读 |
| Evolve Op | 12:15 | `sel_evolve_op.py` | 进化操作化 |
| Distill Queue | 15:45, 23:45 | `distill_queue.py` | 蒸馏队列 |

### 4.6 子Agent集成

| Agent | 触发条件 | 说明 |
|-------|----------|------|
| 构建排错 | 测试失败/Lint报错/编译错误 | 修复构建问题 |
| 故障猎人 | 代码修改后/新脚本交付前/重构后 | 扫描静默失败 |
| 规划师 | 架构变更/跨文件重构/新功能设计 | 输出实施步骤 |
| 会话分析 | SEL维护周期/交互模式档案更新 | 分析对话模式 |

### 4.7 定时任务

| 任务名 | 时间 | 脚本 | 说明 |
|--------|------|------|------|
| StockAnalysis_HealthCheck | 07:03 | `health_check.py` | 系统健康检查 |
| SEL_MorningLint | 08:30 | `lint_wrapper.py` | 晨间Lint |
| SEL_Digest | 09:00 | `sel_digest.py` | 知识消化 |
| SEL_Maintain | 09:05 | `sel_maintain.py` | 知识维护 |
| SEL_Connect | 09:10 | `sel_connect.py` | 知识连接 |
| SEL_Prune | 09:15 | `sel_prune.py` | 知识裁剪 |
| SEL_EvolveRead | 12:00 | `sel_evolve_read.py` | 进化阅读 |
| SEL_EvolveOp | 12:15 | `sel_evolve_op.py` | 进化操作化 |
| SEL_TaskSentinel | 10:00 | `task_sentinel.py` | 任务哨兵 |
| StockNightlyHealth | 00:30 | `nightly_health_check.py` | 夜间健康检查 |
| Cognitive_TaskDashboard | 20:00 | `task_dashboard.py` | 任务仪表盘 |
| Cognitive_ConversationMiner | 22:30 | `conversation_miner.py` | 对话挖掘 |
| StockAnalysis_DailyCompress | 23:00 | `daily_compress_agent.py` | 每日压缩 |

### 4.8 健康检查覆盖范围

| 检查项 | 函数 | 说明 |
|--------|------|------|
| Windows 计划任务存在性 | `check_windows_tasks()` | 检查 tasks.json 中任务是否存在 |
| D盘空间 | `check_disk()` | 磁盘空间告警 |
| 飞书推送连通性 | `check_feishu_push()` | 飞书 API 可达 |
| 语法门禁 | `check_import_gate()` | Gate 1 可用 |
| Schema门禁 | `check_schema_gate()` | Gate 2 可用 |
| 部门晨间就绪 | `check_department_readiness()` | 三部（前厅/情报/读书郎） |

### 4.10 Agent 使用规范

工程部是所有部门中 Agent 使用密度最高的。每个场景有专用 Agent，且部分 Agent 已通过 PostToolUse hook 自动触发：

| 场景 | Agent | 调用方式 | 说明 |
|------|-------|----------|------|
| **构建/类型错误** | `build-error-resolver` | `Agent({subagent_type: "build-error-resolver", prompt: "..."})` | 测试失败/Lint报错/编译错误→自动修复，不改架构 |
| **静默失败扫描** | `silent-failure-hunter` | `Agent({subagent_type: "silent-failure-hunter", prompt: "..."})` | 代码修改后/新脚本交付前/重构后→扫描吞错误/坏后备 |
| **代码质量审查** | `code-reviewer` | `Agent({subagent_type: "code-reviewer", prompt: "..."})` | 所有代码改动后必须审查（已通过 hooks 自动触发？需确认） |
| **代码简化** | `code-simplifier` | `Agent({subagent_type: "code-simplifier", prompt: "..."})` | 代码冗余/复杂→简化，保留行为不变 |
| **深度代码分析** | `code-explorer` | `Agent({subagent_type: "code-explorer", prompt: "..."})` | 追踪执行路径/映射架构层/理解依赖关系 |
| **安全检查** | `security-reviewer` | `Agent({subagent_type: "security-reviewer", prompt: "..."})` | 涉及敏感数据/API密钥/外部输入的代码 |
| **架构变更规划** | `planner` | `Agent({subagent_type: "planner", prompt: "..."})` | 架构变更/跨文件重构/新功能设计→输出实施步骤 |
| **Session 分析** | `conversation-analyzer` | `Agent({subagent_type: "conversation-analyzer", prompt: "..."})` | SEL维护周期/交互模式档案更新时分析对话模式 |
| **配置优化** | `harness-optimizer` | `Agent({subagent_type: "harness-optimizer", prompt: "..."})` | 优化 harness 配置（hooks/evals/routing/context） |

**自动触发 vs 手动调用：**
- 由 PostToolUse hook 自动触发：`build-error-resolver`（Bash失败时通过 failure_analyzer）、`code-reviewer`
- 需手动调用：`silent-failure-hunter`、`planner`、`conversation-analyzer`、`harness-optimizer`

**执行规则：**
- P0: 改代码后必须走质量门禁（import_gate + auto_verify hooks 已自动执行）
- P0: 错误修复后必须用 `silent-failure-hunter` 扫描一次
- P1: 架构变更前必须用 `planner` 出方案
- P1: SEL周期中用 `conversation-analyzer` 分析对话模式
- P2: 测试覆盖率达标后用 `code-simplifier` 清理冗余代码

### 4.11 职责边界

| 负责 | 不负责 |
|------|--------|
| 所有基础设施的可用性和可靠性 | 交易决策和持仓管理（前厅部负责） |
| 质量门禁的维护和执行 | 数据采集和情报分析（情报部负责） |
| 错误追踪和自动修复 | 新交易策略开发（研发部负责） |
| SEL自进化循环 | 读书笔记和知识穿透（读书郎负责） |
| 测试覆盖和质量标准 | |
| 定时任务调度和监控 | |
| 通道健康和数据保鲜 | |

---

## 五、研发部（rd）

### 5.1 基础信息

| 项目 | 内容 |
|------|------|
| **系统名** | rd |
| **Skill** | `.claude/skills/dept-rd/SKILL.md` |
| **处理器** | `dept_handlers.py` → `handle_rd()` |
| **依赖部门** | engineering, front-office |
| **触发关键词** | 研发, rd, 想法, 规则, 优化, 策略, 实验, 工具, 管道, 待办, pipeline |

### 5.2 输入标准

| 数据源 | 文件路径 | 用途 | 保鲜要求 |
|--------|----------|------|----------|
| 想法管道 | `stock_data/status/rd_ideas.json` | 用户和各部门提交的想法 | 实时 |
| 交易规则 | `stock_analysis/data/trading_rules.json` | 已操作化的交易规则 | ≤24h |
| 缺口登记 | `stock_data/gap_registry/` | 知识缺口清单 | 实时 |

### 5.3 输出标准

| 输出 | 文件路径 | 触发条件 |
|------|----------|----------|
| **部门状态** | `stock_data/status/rd_status.json` | 每次操作后 |
| **新工具/脚本** | `stock_analysis/tools/` 或对应目录 | 想法落地完成 |
| **规则更新** | `stock_analysis/data/trading_rules.json` | 策略操作化完成 |
| **门禁更新** | `stock_analysis/tools/` | 新约束落地 |

### 5.4 工作流程

```
用户/部门提出想法
  → 研发部评估可行性
    → 转化为规则 (写入 trading_rules.json / 部门配置)
    → 转化为工具 (新脚本/新看板)
    → 转化为约束 (质量门禁/风控条件)
    → 转化为优化 (流程改进/数据源增强)
  → 通知关联部门
  → 更新部门状态
```

### 5.5 知识缺口驱动的发现（汲智系统 KAE Phase1）

| 步骤 | 说明 |
|------|------|
| 1. 缺口登记 | 从对话/审计中发现的知识盲区 |
| 2. 主动搜索 | 基于缺口搜索外部资源 |
| 3. 吸收 | 将新知识结构化吸收 |
| 4. 提案 | 形成可落地的提案 |
| 5. 执行 | 落地到代码/规则/流程 |

### 5.6 Agent 使用规范

研发部的 Agent 使用面最广，从架构设计到代码审查全覆盖：

| 场景 | Agent | 调用方式 | 说明 |
|------|-------|----------|------|
| **架构设计** | `code-architect` | `Agent({subagent_type: "code-architect", prompt: "..."})` | 新功能/新模块上线前→分析现有模式+输出蓝图 |
| **实现规划** | `planner` | `Agent({subagent_type: "planner", prompt: "..."})` | 复杂功能→分步实施计划+风险评估 |
| **深度代码分析** | `code-explorer` | `Agent({subagent_type: "code-explorer", prompt: "..."})` | 理解现有代码结构→追踪执行路径 |
| **代码审查** | `code-reviewer` | `Agent({subagent_type: "code-reviewer", prompt: "..."})` | 所有新代码/改动后必须审查 |
| **代码简化** | `code-simplifier` | `Agent({subagent_type: "code-simplifier", prompt: "..."})` | 复杂逻辑→简化，保留行为 |
| **构建修复** | `build-error-resolver` | `Agent({subagent_type: "build-error-resolver", prompt: "..."})` | 构建/类型错误 |
| **性能优化** | `performance-optimizer` | `Agent({subagent_type: "performance-optimizer", prompt: "..."})` | 新工具性能未达标 |
| **安全检查** | `security-reviewer` | `Agent({subagent_type: "security-reviewer", prompt: "..."})` | 涉及外部输入/API密钥的代码 |
| **静默失败扫描** | `silent-failure-hunter` | `Agent({subagent_type: "silent-failure-hunter", prompt: "..."})` | 新脚本交付前务必扫描 |

**执行规则：**
- P0: 新功能实现前必须用 `planner` 出方案
- P0: 代码交付前必须过 `code-reviewer` + `silent-failure-hunter`
- P1: 架构级变更必须用 `code-architect` 输出蓝图
- P1: 性能敏感的新工具必须用 `performance-optimizer` 验证

### 5.7 职责边界

| 负责 | 不负责 |
|------|--------|
| 将想法转化为可运行的代码/规则 | 日常运维（工程部负责） |
| 知识缺口弥补 | 常规交易决策（前厅部负责） |
| 新工具/脚本开发 | 数据采集（情报部负责） |
| 流程优化和改进 | 读书笔记（读书郎负责） |
| 汲智系统（KAE）运行 | |
| 质量门禁增强 | |
| 交易规则操作化 | |

---

## 六、读书郎（reader）

### 6.1 基础信息

| 项目 | 内容 |
|------|------|
| **系统名** | reader |
| **Skill** | `.claude/skills/dept-reading/SKILL.md` |
| **处理器** | `dept_handlers.py` → `handle_reader()` |
| **依赖部门** | （无） |
| **触发关键词** | 读书, read, 书单, 穿透, 笔记 |

### 6.2 输入标准

| 数据源 | 文件路径 | 用途 | 保鲜要求 |
|--------|----------|------|----------|
| 读书笔记 | `stock_data/reading_notes/*.md` | 已完成的读书产出 | 持续更新 |
| 读书索引 | `stock_data/status/reading_index.json` | 读书进度索引 | 实时 |

### 6.3 输出标准

| 输出 | 文件路径 | 触发条件 |
|------|----------|----------|
| **部门状态** | `stock_data/status/reading_status.json` | 每次读书/维护后 |
| **读书笔记** | `stock_data/reading_notes/书名.md` | 读完一本书 |
| **每日复盘压缩** | 内联输出 | 15:37 daily-compress |
| **晨间认知加载** | 内联输出 | 08:07 daily-load |

### 6.4 读书规范

| 标准 | 内容 |
|------|------|
| **格式** | 文本→交易穿透（原文摘录 → 逐段穿透到交易动作） |
| **Frontmatter** | 四字段必带: title / date / tags / type |
| **类型标签** | 精读 / 穿透 / 逐字读（必须与实际方法一致） |
| **不能做的事** | P2/P3 级别分析（只做直接穿透到交易动作） |

### 6.5 认知飞轮定时链条

| 时间 | 任务 | 内容 |
|------|------|------|
| 08:07 | `daily-load` | 晨间认知加载 — 注入认知上下文 |
| 15:37 | `daily-compress` | 每日复盘压缩 — 对话→5段认知摘要 |
| 22:00 | 晚间日常 | 知识库健康检查+复盘+明日计划 |

### 6.6 定时任务（Claude Code 调度器）

| 时间 | 任务 | 说明 |
|------|------|------|
| 22:03 每日 | 晚间日常 | 读对话记录→知识库健康→复盘→明日计划 |
| 08:07 工作日 | `/daily-load` | 晨间认知加载 |
| 15:37 工作日 | `/daily-compress` | 每日复盘压缩 |

### 6.7 Agent 使用规范

读书郎的 Agent 主要用于**知识管理和认知优化**：

| 场景 | Agent | 调用方式 | 说明 |
|------|-------|----------|------|
| **知识库探索** | `code-explorer` | `Agent({subagent_type: "code-explorer", prompt: "..."})` | 追溯知识库结构/查找关联笔记 |
| **笔记整理简化** | `code-simplifier` | `Agent({subagent_type: "code-simplifier", prompt: "..."})` | 复杂认知内容→简明明了的结构 |
| **深度研究** | `deep-research` | `Agent({subagent_type: "deep-research", prompt: "..."})` | 缺口知识→后台深度研究（DeepSeek Ch2 配额） |

**执行规则：**
- P1: 知识库膨胀时用 `code-simplifier` 整理
- P1: 遇到知识盲区时用 `deep-research` 深挖
- P2: 月度知识库审计用 `code-explorer` 追踪引用链

### 6.8 职责边界

| 负责 | 不负责 |
|------|--------|
| 读书→交易穿透笔记 | 数据采集（情报部负责） |
| 晨间认知加载 | 交易决策（前厅部负责） |
| 每日复盘压缩 | 基础设施/门禁（工程部负责） |
| 知识库维护 | 新工具开发（研发部负责） |
| 知识路由支持 | |
| 知识健康审计 | |

---

## 七、部门间对接/数据流总图

### 7.1 数据流向

```
情报部（采集）
  │
  ├──→ news_*.json ───────────────────────→ 前厅部（盘中/题材）
  ├──→ intel/intel_latest.json ───────────→ 前厅部（信号）
  ├──→ market_fund_flow_cache.json ───────→ 前厅部（资金面）
  │
工程部（基础设施）
  │
  ├──→ channel_health_latest.json ────────→ 情报部 + 前厅部
  ├──→ last_error.txt ───────────────────→ 所有部门
  ├──→ quality gates ────────────────────→ 所有代码改动
  │
前厅部（决策）
  │
  ├──→ portfolio.json ───────────────────→ 情报部（关联分析）
  ├──→ closing_review.json ──────────────→ 情报部（推演输入）
  ├──→ scan_vcp_default.json ────────────→ 情报部（VCP信号）
  │
研发部（创意）
  │
  ├──→ trading_rules.json ───────────────→ 前厅部（规则落地）
  ├──→ 新工具/脚本 ──────────────────────→ 对应部门
  │
读书郎（知识）
  │
  ├──→ reading_index.json ───────────────→ 所有部门（知识检索）
  ├──→ daily-load/daily-compress ────────→ 前厅部（认知上下文）
```

### 7.2 部门依赖检查

| 部门 | 依赖 | 预检检查 | 阻塞条件 |
|------|------|----------|----------|
| 前厅部 | engineering | engineering 状态 healthy + fresh | critical 问题 |
| 情报部 | front-office, engineering | 两部状态 healthy + fresh | critical 问题 |
| 工程部 | （无） | 仅数据文件新鲜度 | 循环依赖 |
| 研发部 | engineering, front-office | 两部状态 healthy + fresh | critical 问题 |
| 读书郎 | （无） | 仅数据文件新鲜度 | 循环依赖 |

### 7.3 部门间 cue/回调

| 发起方 | 接收方 | 触发条件 | 回调内容 |
|--------|--------|----------|----------|
| 任意部门 | 研发部 | 发现知识缺口 | 登记到 gap_registry |
| 工程部 | 所有部门 | 通道故障/门禁失败 | 告警推送到 alerts 群 |
| 前厅部 | 情报部 | 盘中需要最新信号 | 拉取 intel_latest.json |
| 情报部 | 前厅部 | 侦察发现重大信号 | 通过飞书推送 |
| 读书郎 | 前厅部 | 晨间认知加载完成 | 注入上下文 |
| 研发部 | 对应部门 | 新工具/规则落地 | 通知部门更新配置 |
| 所有部门 | 枢部 | 部门操作前 | 强制 OpsGate 预检 |

### 7.4 飞书消息路由对照

| 路由 | 主要发送方 | 接收群 | 内容类型 |
|------|-----------|--------|----------|
| main | 前厅部 + 情报部 | 主群 | 晨报/盘中/热股/复盘 |
| book | 读书郎 | 书虫群 | 读书笔记/穿透 |
| news | 情报部 | 新闻群 | 新闻流 |
| midday | 前厅部 | 午盘数据群 | 午盘快照 |
| closing | 前厅部 + 情报部 | 收盘数据群 | 收盘复盘/推演 |
| alerts | 工程部 | 问题组告警群 | 故障/告警/门禁失败 |
| overnight | 前厅部 | 背调小队 | 隔夜分析 |

---

## 八、Skills 使用规范

Skills 是比 Agent 更高层的技能封装。Agent 处理单一任务（如代码审查），Skill 处理完整工作流（如每日复盘）。

### 8.1 部门技能（已内置于各部门规范）

以下 5 个 Skill 已自动注入各部门 SKILL.md，内容直接作为部门工作上下文：

| Skill | 对应部门 | 作用 |
|-------|----------|------|
| `dept-front-office` | 前厅部 | 交易决策/持仓/风控上下文 |
| `dept-intelligence` | 情报部 | 采集/侦察/推演上下文 |
| `dept-engineering` | 工程部 | 基础设施/SEL/门禁上下文 |
| `dept-rd` | 研发部 | 创意转化/工具开发上下文 |
| `dept-reading` | 读书郎 | 读书→交易穿透上下文 |

### 8.2 知识路由技能（按需自动加载）

由 `rules/knowledge-routing.md` 控制触发条件。当对话中出现对应关键词时，主 Agent 必须先用 Skill 工具加载对应知识框架再推理：

| Skill | 触发关键词 | 加载方式 |
|-------|-----------|----------|
| `knowledge-economics` | 多Agent调度/风险评估/市场分析/交易决策 | `Skill({skill: "knowledge-economics"})` |
| `knowledge-physics` | 多Agent调度/系统架构/推理质量/知识管理 | `Skill({skill: "knowledge-physics"})` |
| `knowledge-chinese-civ` | 推理质量/认知偏差/市场分析/系统架构 | `Skill({skill: "knowledge-chinese-civ"})` |
| `knowledge-religion` | 推理质量/认知偏差/知识管理/风险评估 | `Skill({skill: "knowledge-religion"})` |

**执行规则（P0）：**
- 以上关键词出现任意一个 → 先加载对应 Skill，再开始推理
- 不确定是否需要加载 → 默认加载（加载成本远小于推理偏差成本）
- 复杂任务涉及多个领域 → 同时加载多个 Skill

### 8.3 交易分析技能

| Skill | 调用方式 | 用途 | 触发时机 |
|-------|----------|------|----------|
| `stock-analysis` | `/stock-analysis` | 5专家+grader 全分析管线 | 持仓深度分析 |
| `stock-deep` | `/stock-deep` | 深度基本面+技术面分析 | 开仓/调仓前 |
| `stock-quick` | `/stock-quick` | 快速行情扫描 | 盘中快速决策 |
| `adversarial-review` | 内嵌在 `/stock-deep` 等技能中 | 开仓前安全审查 | 开仓前强制触发 |
| `vv-leida` | `/vv-leida` | 大V雷达（抖音/雪球监控） | 盘中定时 |

**执行规则：**
- P0: 开仓前必须跑 `/stock-deep`（内含 adversarial-review）
- P0: -7% 硬止损不经过任何技能，直接执行
- P1: 持仓调整前至少跑 `/stock-quick`
- P2: 月度全持仓扫描用 `/stock-analysis`

### 8.4 定时认知技能

| Skill | 时间 | 调用方式 | 用途 |
|-------|------|----------|------|
| `daily-load` | 工作日 08:07 | `/daily-load` | 晨间认知加载—注入认知上下文 |
| `morning-brief` | 工作日 08:37 | 定时触发 | AI晨报（前厅部管线） |
| `daily-compress` | 工作日 15:37 | `/daily-compress` | 每日复盘压缩—对话→5段认知摘要 |
| `weekly-audit` | 周五 | `/weekly-audit` | 周审计—扫描5天压缩摘要做模式识别 |

### 8.5 质量审查技能

| Skill | 调用方式 | 用途 | 级别 |
|-------|----------|------|------|
| `adversarial-review` | `/adversarial-review` | 对抗性审查—交易前强制安全门禁 | P0 |
| `code-review` | `/code-review` | 代码审查—审查当前 diff 的正确性/安全性 | P1 |
| `data-verify` | `/data-verify` | 数据验证—检查数据文件完整性和一致性 | P1 |
| `test-engineer` | `/test-engineer` | 测试编写和执行 | P2 |
| `security-review` | `/security-review` | 安全审计—扫描OWASP Top 10 | P2 |

### 8.6 工程构建技能

以下技能在工程部处理多语言构建问题时按需调用：

| Skill | 调用方式 | 用途 |
|-------|----------|------|
| `build-fix`, `go-build`, `rust-build`, `flutter-build`, `cpp-build`, `gradle-build`, `kotlin-build` | `/build-fix` 等 | 对应语言的构建修复 |
| `go-review`, `rust-review`, `flutter-review`, `cpp-review`, `kotlin-review`, `python-review` | `/go-review` 等 | 对应语言的代码审查 |
| `refactor-clean` | `/refactor-clean` | 死代码清理 |
| `prune` | `/prune` | 依赖裁剪 |

### 8.7 知识管理与工具技能

| Skill | 调用方式 | 用途 | 所属 |
|-------|----------|------|------|
| `graphify` | `/graphify` | 知识图谱生成—输入→知识图谱 | 读书郎 |
| `explore` | `/explore` | 结构化探索 | 研发部 |
| `structured-exploration` | `/structured-exploration` | 深度探索（试→调→再试） | 研发部 |
| `cross-dept-flow` | `/cross-dept-flow` | 跨部门流程 | 枢部 |
| `ctx-health` | `/ctx-health` | 上下文健康检查 | 工程部 |
| `errorlog` | `/errorlog` | 错误日志分析 | 工程部 |
| `debugger` | `/debugger` | 调试辅助 | 工程部 |
| `skill-creator` | `/skill-creator` | 创建新Skill | 研发部 |
| `user-image-vision` | 自动触发（发截图路径时） | 图片理解 | 通用 |
| `user-video-learn` | `/user-video-learn` | 视频学习/转录分析 | 读书郎 |
| `user-planning-with-files` | `/user-planning-with-files` | 文件级规划 | 通用 |
| `init` | `/init` | 项目初始化 | 工程部 |

### 8.8 Skill 执行原则

| 原则 | 说明 |
|------|------|
| **Skill 覆盖优先级** | 部门 Skill → 知识路由 Skill → 交易分析 Skill → 质量 Skill → 工程 Skill |
| **部门 Skill 自动加载** | 各部门 SKILL.md 已在部门激活时自动注入 |
| **知识路由必先加载** | 触发关键词时先用 Skill 工具加载知识框架，再推理 |
| **质量 Skill 强制** | adversarial-review 和 code-review 是 P0 强制门禁 |
| **定时 Skill 不手动干预** | daily-load / daily-compress / weekly-audit 按 cron 执行 |
| **不跨部门调 Skill** | 每个 Skill 归属一个部门，其他部门需使用时走 task_queue |

---

## 九、执行铁律（全部门适用）

### P0 — 零号标准（100%执行）

- 零误差、零失误、零跳过、零懈怠、零容忍
- 所有规则/指令都是必须执行的，不经过"我觉得重不重要"过滤器
- 违反→停止→记录→修复→从断点重新执行

### P0 — 处理旧问题先查记忆

| 步骤 | 内容 |
|------|------|
| 1 | 读 interaction-patterns.md [待调整项] |
| 2 | 读 memory/ 下相关主题的反馈记录 |
| 3 | 读 last_error.txt 确认最新错误上下文 |
| 4 | 匹配→直接参照已知根因+修复方案 |
| 5 | 修复完成→写入本次执行结果 |

### P0 — 失败必须记录

记录内容: 问题/根因/修复/防复发
记录落点: `memory/feedback/failure-YYYYMMDD-短描述.md`

### P0 — 交付前强制验证

1. 跑一次正常模式 → exit code = 0
2. 检查输出文件已生成且非空
3. 跑一次边界条件
4. 读输出内容确认格式正确、数值合理
5. bug修复→确认 root cause 解决

### P0 — 架构变更4步模式

1. **P0 全资产盘查** — grep 所有旧名称/旧路径
2. **P1 分层实施** — 数据层→逻辑层→表现层→配置层
3. **P2 全仓库验证** — 零残留
4. **P3 运行时验证** — 每个模块独立跑一次

### 部门间协作规则

| 规则 | 内容 |
|------|------|
| **接到 cue 必须响应** | 其他部门 cue → 直接处理，不等用户传话 |
| **跨部门输出必过 OpsGate** | preflight + crosscheck + source_footer |
| **软依赖不阻塞** | 依赖部门状态缺失 → advisory 继续，不阻塞 |
| **状态文件必发** | 每个操作完成后 publish_status() |
