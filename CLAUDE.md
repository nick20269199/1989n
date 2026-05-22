# 1989n 量化交易系统

## 铁律：每次会话第一件事

**启动时必须先读 `stock_data/interaction/interaction-patterns.md`**，对照其中[待调整项]逐条核查本次会话是否重犯。读完才算会话开始。

## 开发环境

```bash
# Python 解释器
/d/Python314/python

# 运行测试（全部）
/d/Python314/python -m pytest stock_analysis/tests/ -v

# 运行单个测试文件
/d/Python314/python -m pytest stock_analysis/tests/test_grader.py -v

# 运行单个测试用例
/d/Python314/python -m pytest stock_analysis/tests/test_grader.py::test_grade_below_threshold -v

# 运行脚本（必须从 stock_analysis 目录）
cd D:/1989n/stock_analysis && /d/Python314/python -m script_name

# SEL 知识库健康检查
/d/Python314/python D:/1989n/stock_analysis/_sel_lint.py
```

## 架构概览

### 数据流

```text
外部数据源 (TDX/新浪/腾讯/搜狐/财联社)
  → data_source_router.py (自动健康检查+通道回退)
    → 采集脚本 (daily_task.py / call_auction.py / news_scheduler.py)
      → JSON/DB 写入 D:/1989n/stock_data/
        → 分析层 (晨报/复盘/盘中) → 飞书推送
```

关键设计：**无单点故障**。每类数据至少 2 个独立通道，东方财富 WAF 封锁后自动跳过。

### 多 Agent 分析管线 (experts/)

```bash
experts/
  lead.py          — 编排器：并行调度 5 专家 → 汇总 → 送 grader
  grader.py        — 五维门禁 (方向/方式/轨迹/边际/逻辑)，评分<阈值阻断
  expert1_tech.py  — 技术面 (价格/均线/量能)
  expert2_money.py — 资金面 (主力流向/大单分布)
  expert3_sentiment.py — 情绪面 (涨停/跌停/市场情绪)
  expert4_macro.py — 宏观面 (市场体制/板块轮动)
  expert5_risk.py  — 风控 (止损/集中度/持仓时长)
  base.py          — 基类 + LLM 调用 + 自修复装饰器
  config.py        — 权重/超时/路径配置
```

触发：`python -m stock_analysis.experts.lead --symbol 002156 --name 通富微电` 或 `--portfolio` 全持仓扫描。

### 调度层

Windows Task Scheduler (~15 个任务) → `run_*.bat` → Python 入口脚本。所有 .bat 在 `stock_analysis/` 下。

### 输出层

`feishu_sender.py` — 基于飞书 IM API (tenant_access_token)，支持 4 种消息类型 + 7 路群路由 + 15条/分钟限流。

## 四部架构

系统分三个部门，通过 `dept_status_protocol.py`（JSON 文件协议）通信：

| 部门 | 职责 | 触发 |
| ------ | ------ | ------ |
| **前厅部** | 股票分析自动化 — 数据→分析→决策支持全流水线 | 交易时段驱动 |
| **工程部** | SEL 知识库健康巡检 — 腐烂/断链/draft老化/规则脱节 | 08:30 日频 |
| **财务部** | 财务分析、持仓校验、5 维度分析报告 | 对话触发 |

状态文件：`stock_data/status/{dept}_status.json`。预检：`dept_preflight.py --dept <name>`。

### SEL 自进化循环 (engineering/)

```text
维修循环 (日频): Lint → Digest → Connect → Maintain → Prune
进化循环 (日/周频): Read → Extract → Operationalize → Inject
```

脚本：`_sel_lint.py` 检测 6 项（腐烂/draft/幽灵引用/规则脱节/Ingest未完成/缺失连接）。

## 读书知识体系

读书产出存 `stock_data/reading_notes/`，格式为 **文本→交易穿透**（原文摘录 → 逐段穿透到交易动作）。

已读（按文本→交易穿透格式）：

| 日期 | 书目 | 核心穿透 |
| ------ | ------ | --------- |
| 05-18 | 庄子内篇 | 七篇修行：格局/心斋/游刃/散木/真人/浑沌 |
| 05-18 | 道德经 | 81 章：道法自然/上善若水/知止不殆 |
| 05-19 | 孙子兵法 | 十三篇体系：五事七计/先为不可胜/风林火山 |
| 05-20 | 毛选·矛盾论 | 矛盾定多空、内因为主、不同矛盾不同策略 |
| 05-20 | 毛选·实践论 | 实践出真知、感性→理性、知行统一 |

索引：`stock_data/status/reading_index.json` — 各部门通过钩子发现和调阅。

### 错误处理链

脚本入口调 `error_capture.trap()` → 异常自动写 `D:/1989n/stock_data/last_error.txt` → 同时触发 error_kb_hook 匹配知识库 + session_tracker 记录。

### 测试策略 (stock_analysis/tests/)

| 文件 | 覆盖路径 | 等级 |
| ------ | --------- | ------ |
| test_portfolio_loader.py | 持仓加载 + 后备方案 + 字段标准化 | critical |
| test_data_quality_gate.py | 保鲜门禁 + 过期检测 + 空文件 | critical |
| test_hot_stocks_pipeline.py | 涨停池数据转换 (akshare mock) | critical |
| test_grader.py | 评分逻辑 + 阻断条件 | high |
| test_feishu_router.py | 路由解析 + 限流 + 发送开关 | high |
| test_conversation_miner.py | JSONL 解析 + 消息提取 | medium |

运行：`/d/Python314/python -m pytest stock_analysis/tests/ -v`

## 当前持仓 — 以 data/portfolio.json 为唯一准 (最后同步: 2026-05-22)

| 代码 | 名称 | 持仓(股) | 成本价 | 行业 |
| ------ | ------ | -------- | ------- | ------ |
| 002156 | 通富微电 | 600 | 44.850 | 半导体封测 |
| 002208 | 合肥城建 | 1100 | 24.599 | 房地产 |
| 300136 | 信维通信 | 600 | 113.107 | 消费电子/射频 |
| 600498 | 烽火通信 | 600 | 57.850 | 通信设备 |
| 002077 | 大港股份 | 2500 | 18.684 | 半导体/EDA |
| 300058 | 蓝色光标 | 800 | 18.240 | AI营销/出海 |

## 已清仓

| 代码 | 名称 | 出清价 | 盈亏 | 出清日 |
| ------ | ------ | ------- | ------ | -------- |
| 000062 | 深圳华强 | 37.20 | -160 | 2026-05-12 |
| 300739 | 明阳电路 | 30.35 | -1,741 | 2026-05-13 |
| 300480 | 光力科技 | 39.60 | +1,328 | 2026-05-14 |
| 300342 | 天银机电 | 59.89 | -1,390 | 2026-05-14 |
| 600236 | 桂冠电力 | 10.90 | -8,558 | 2026-05-14 |
| 002407 | 多氟多 | 36.47 | +120 | 2026-05-15 |
| 002050 | 三花智控 | 52.96 | +2,447 | 2026-05-18 |
| 000981 | 山子高科 | 3.99 | -3,368 | 2026-05-20 |
| 600860 | 京城股份 | 10.53 | -1,959 | 2026-05-20 |
| 601789 | 宁波建工 | 5.815 | -2,033 | 2026-05-21 |
| 300792 | 壹网壹创 | 38.038 | +1,007 | 2026-05-21 |
| 300339 | 润和软件 | 43.520 | -417 | 2026-05-21 |

## 路径配置（硬约束）

| 路径 | 用途 |
| ------ | ------ |
| `D:/1989n/stock_analysis/` | 代码主目录 |
| `D:/1989n/stock_data/` | 所有数据文件（JSON/CSV/DB） |
| `D:/1989n/stock_data/last_error.txt` | 最后一次脚本报错的完整 traceback |
| `D:/1989n/stock_data/stock.db` | SQLite 数据库 |
| `D:/1989n/screenshots/` | 截图存储 |
| `D:/1989n/.claude/` | Claude Code 配置 |

**铁律**：所有数据写入必须在 `D:/1989n/stock_data/` 下，禁止写到项目源码目录。

## 核心定时任务

| 脚本 | 触发时间 | 功能 |
| ------ | --------- | ------ |
| `call_auction.py` | 工作日 9:26 | 集合竞价数据采集 |
| `morning_brief_agent.py` | 工作日 8:37 | 盘前晨报（含AI推理） |
| `intraday_report.py` | 工作日 9:03-15:03 每30分钟 | 盘中综合情报 + 飞书推送 |
| `daily_task.py closing_review` | 工作日 15:05 | 收盘复盘 |
| `nightly_plan.py auto` | 工作日 15:40 | 隔夜交易计划生成 |
| `daily_task.py tech_scan` | 工作日 15:33 | 技术形态扫描 |
| `news_scheduler.py morning` | 每天 8:03 | 早间新闻采集 |
| `news_scheduler.py evening` | 每天 22:07 | 晚间新闻采集 |
| `daily_task.py overnight` | 工作日 23:37 | 隔夜分析 |
| `health_check.py` | 每天 7:03 | 系统健康检查 |
| `nightly_health_check.py` | 每天 0:07 | 夜间健康检查 + C盘空间告警 |

## 交易纪律（硬约束）

- **开仓/加仓/调仓前必须跑 adversarial-review**，审查不通过不执行
- **-7% 无条件硬止损**，任何分析/决策中不得建议扛单
- 分析基于可溯源真实数据，每个数据点标注来源。数据差就说差，不确定就说不知道，不因持仓偏乐观

## 数据安全（硬约束）

- 禁止删除 `stock_data/` 下任何 JSON/CSV/DB 文件（用户明确要求除外）
- 禁止修改 `config.py` 中的路径配置（用户明确要求除外）
- 所有 API 密钥通过 `.env` 管理，禁止硬编码

## 错误处理

- 脚本报错 → 先读 `last_error.txt` 原文，不接受转述
- 修完 → 跑两次脚本确认（正常模式 + 边界条件）

## 用户偏好

- 英文报错 Claude 自己读 `last_error.txt`，所有输出用中文，回复简洁，不使用 emoji
- 改配置/脚本后必须验证，不假设"改了就能用"

## 知识路由（硬约束）

任务涉及以下领域时，**必须先加载对应 Skill**，获取完整知识框架后再推理：

| 任务场景 | 必须加载 |
| --------- | --------- |
| 风险评估/止损/安全策略 | `knowledge-economics` + `knowledge-physics` |
| 多Agent调度/系统架构/模块设计 | `knowledge-economics` + `knowledge-chinese-civ` |
| 推理质量/效率/停止条件 | `knowledge-religion` + `knowledge-physics` |
| 认知偏差/自我审查/元认知 | `knowledge-religion` + `knowledge-chinese-civ` |
| 市场分析/交易决策/投资判断 | `knowledge-economics` + `knowledge-chinese-civ` |
| 知识管理/学习路径/认知进化 | `knowledge-physics` + `knowledge-religion` |

路由判断原则：不确定是否需要加载 → 默认加载。加载成本远小于推理偏差成本。

蒸馏产出目录: `stock_data/economics_reading/` (80本), `stock_data/religion_reading/` (100+本), `stock_data/physics_reading/` (50本), `stock_data/chinese_civilization/` (22部) — 完整原始产出供深入查阅。
