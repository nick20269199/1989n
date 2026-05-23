# 定时任务一览 | 2026-05-23 15:02

Python: `D:\Python314\python`
工作目录: `D:\1989n\stock_analysis`
数据来源: `data/tasks.json`

---

## 汇总

- 任务总数: 42 (启用 41, 禁用 1)
- Windows 定时任务: 37
- 手动脚本: 5

### 前厅部

| 任务 | 说明 | 时间 | 脚本 |
|------|------|------|------|
| StockAnalysis_IntradayMidday | 午盘30分钟分析 | 工作日 11:30 | `daily_task.py` |
| StockAnalysis_VVRadar_Afternoon | 大V雷达 (13:00下午) | 13:00 | `vv_radar.py` |
| StockAnalysis_IntradayClose | 收盘30分钟分析 | 工作日 15:00 | `daily_task.py` |
| StockAnalysis_ClosingReview | 收盘复盘 (带退出码修复) | 工作日 15:15 | `daily_task.py` |
| StockAnalysis_SectorCollect | 板块日数据采集 | 工作日 15:20 | `daily_task.py` |
| StockAnalysis_Recon | 侦查日报 (收盘后探索层) | 工作日 15:30 | `recon_daily.py` |
| StockAnalysis_TechScan | 技术形态扫描 | 工作日 15:33 | `daily_task.py` |
| StockAnalysis_NightlyPlan | 隔夜交易计划生成 | 工作日 15:40 | `nightly_plan.py` |
| StockAnalysis_DecisionBacktest | 决策 T+5 定时回测 | 工作日 16:30 | `daily_task.py` |
| StockAnalysis_Dreamer | 决策梦境推演 — 专家权重动态调整 | 工作日 17:00 | `experts/dreamer.py` |
| StockForecastCloser | 预测追踪闭环 | 工作日 17:05 | `forecast_closer.py` |
| StockAnalysis_Evening | 晚间总结 + 大V雷达 + 预测闭环 | 22:00 | `vv_radar.py` (+2步) |
| StockAnalysis_Overnight | 隔夜分析 (美股+次日展望) | 工作日 23:37 | `daily_task.py` |
| StockAnalysis_MorningBrief ⛔ | 盘前晨报 v1 (旧版) | 工作日 08:27 | `morning_brief.py` |
| Cognitive_MorningBrief | 盘前晨报 v2 (AI Agent) | 工作日 08:37 | `morning_brief_agent.py` |
| StockAnalysis_CallAuction | 集合竞价数据采集 | 工作日 09:26 | `call_auction.py` |
| StockAnalysis_HotStocks | 热门股票采集 + 大V雷达联动 | 工作日 09:35 / 工作日 13:00 | `daily_task.py` (+1步) |
| StockAnalysis_VVRadar | 大V雷达 (09:35) | 09:35 | `vv_radar.py` |
| monitor_000062 | 00062深圳华强专项监控 (未注册定时任务) | 手动执行 | `monitor_000062.py` |
| backtest | 决策 T+5 回测 (手动) | 手动执行 | `daily_task.py` |
| weekly_sector | 周度板块轮动报告 (手动) | 手动执行 | `daily_task.py` |
| multi_angle_analysis | 多角度交叉分析 (手动执行, 10路DeepSeek并行) | 手动执行 | `multi_angle_analysis.py` |

### 情报部

| 任务 | 说明 | 时间 | 脚本 |
|------|------|------|------|
| Intel_Recon | 情报部盘前侦察 | 工作日 08:50 | `intelligence_service.py` |
| Intel_Deduce | 情报部收盘推演 | 工作日 15:45 | `intelligence_service.py` |

### 工程部

| 任务 | 说明 | 时间 | 脚本 |
|------|------|------|------|
| SEL_TaskSentinel | 任务哨兵 — 检查定时任务+数据文件健康 | 10:00 | `task_sentinel.py` |
| SEL_EvolveRead | 工程部 Evolve — 知识阅读 | 12:00 | `sel_evolve_read.py` |
| SEL_EvolveOp | 工程部 Evolve — 知识操作化 | 12:15 | `sel_evolve_op.py` |
| SEL_DistillQueue | 蒸馏队列扫描 — 扫描当日产出加入队列 | 工作日 15:45 / 23:45 | `distill_queue.py` |
| SEL_MorningLint | 工程部 Morning Lint — 6项检测 | 08:30 | `lint_wrapper.py` |
| SEL_Digest | 工程部 Digest — 知识库消化 | 09:00 | `sel_digest.py` |
| SEL_Connect | 工程部 Connect — 知识连接 | 09:10 | `sel_connect.py` |
| SEL_Prune | 工程部 Prune — 知识裁剪 | 09:15 | `sel_prune.py` |
| SEL_Maintain | 工程部 Maintain — 知识库维护 | 09:05 | `sel_maintain.py` |

### 后勤部

| 任务 | 说明 | 时间 | 脚本 |
|------|------|------|------|
| StockNightlyHealth | 夜间健康检查 | 00:30 | `nightly_health_check.py` |
| Cognitive_TaskDashboard | 任务仪表盘监控 | 20:00 | `task_dashboard.py` |
| StockNews_Evening | 晚间新闻采集 | 21:55 | `news_scheduler.py` |
| Cognitive_ConversationMiner | 对话挖掘 | 22:30 | `conversation_miner.py` |
| StockAnalysis_DailyCompress | 每日复盘压缩 | 23:00 | `daily_compress_agent.py` |
| StockAnalysis_HealthCheck | 系统健康检查 | 07:03 | `health_check.py` |
| StockNews_Morning | 早间新闻采集 | 08:00 | `news_scheduler.py` |
| StockNews_Intraday | 盘中新闻采集 (09:30-15:00 每30分钟) | 工作日 09:30 (每30分钟至05:30) | `news_scheduler.py` |
| weekly_audit_agent | 周审计 (未注册定时任务) | 手动执行 | `weekly_audit_agent.py` |

---
*自动生成于 2026-05-23 15:02 | 修改 tasks.json 后重新运行 `python tools/generate_task_bats.py`*
