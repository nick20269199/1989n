# 多部门容错与预防规则

> 生效: 2026-05-28
> 关联: delegation-mandate.md (#19-24)

## 一、通用容错机制（所有部门/Agent 强制遵守）

### 1.1 执行日志强制记录

- 每次 Agent/Skill 调用结束后，必须将执行结果写入日志文件：
  路径：`d:/1989n/logs/agent_exec/{YYYY-MM-DD}/{agent_name}.json`
- 日志内容必含字段：
  ```json
  {
    "task": "原始任务描述",
    "start_time": "ISO时间戳",
    "end_time": "ISO时间戳",
    "exit_code": 0,
    "output_summary": "不超过200字的摘要",
    "output_hash": "sha256(完整输出)",
    "agent": "agent_name",
    "skill": "skill_name"
  }
  ```

### 1.2 超时与重试

- Agent/Skill 调用后若 3 分钟内无响应，自动重试一次。
- 重试仍失败 → 记录到 errorlog，切换 coordinator-agent 协调替代方案，不得编造结果。

### 1.3 降级开关

- 当某个部门连续 3 次调用失败，自动暂停该部门 Agent，任务路由到 coordinator-agent 走人工决策。
- 全局应急降级：若 `d:/1989n/task-router/emergency_direct_mode.txt` 存在，路由器全部返回 `allow_direct`，旁路所有规则。

### 1.4 外部校验

- 每轮对话结束后，外部脚本 `log_verifier.py` 随机抽查 3 条 Agent 日志，对比回复与日志一致性。
- 连续两次发现不一致 → 发送飞书告警，暂停对话直到人工确认。

---

## 二、部门级容错规则

### 前厅部（stock-analysis、dept-front-office 等）

**预防：**
- 飞书发送前必须验证 webhook 可用性，失败自动切换备用通道。
- 晨报生成失败时，回退到前一日模板，填充最近可用数据，不得空报。

**BUG 处理：**
- 股票分析结果必须包含数据源时间戳，若数据源过期（>15分钟），自动重新拉取。
- 止损/风控建议输出前，必须经 adversarial-review 反向验证。

### 情报部（dept-intelligence）

**预防：**
- 所有数据采集任务必须记录数据源响应时间、数据量、新鲜度。
- `data_sources.yaml` 每周自动巡检可用性，不可用渠道自动标记为 degraded。

**BUG 处理：**
- 采集到空数据时，不得静默跳过，必须写入 `d:/1989n/logs/data_gaps/` 并注明原因。
- 多源数据冲突时（如不同渠道价格偏差>2%），触发 `data-verify` 校验并报告。

### 工程部（dept-engineering、code-review、test-engineer 等）

**预防：**
- 任何代码修改前，必须运行 `build-error-resolver` 检查当前状态。
- 修改后必须运行 `test-engineer` 的回归套件，100% 通过才允许提交。
- 文件写入操作前必须备份原文件到 `d:/1989n/backups/`。
- 所有输出文件的路径与文件名必须使用英文（snake_case），仅文件内容可使用简体中文。`auto_verify.py` 每日扫描违反规则的输出文件并告警。

**BUG 处理：**
- 部署失败立即回滚到上一个稳定版本，由 `code-review` 审查失败原因。
- 静默失败检测：`silent-failure-hunter` 每日扫描日志，发现吞错误行为立即告警。

### 研发部（architect、planner、skill-creator 等）

**预防：**
- 新 Skill 创建前必须通过 `gan-evaluator` 的沙箱测试。
- 架构变更必须先输出变更影响分析，经 `adversarial-review` 审查后才能执行。

**BUG 处理：**
- 新规划/蓝图若连续 2 次执行失败，自动标记为"不可行"，退回 `coordinator-agent`。
- 开源打包/发布前必须经 `security-review` 和 `opensource-sanitizer` 双重扫描。

### 读书郎（dept-reading、daily-compress、weekly-audit-executor 等）

**预防：**
- 读书笔记整理后必须包含原文引用哈希，防止捏造。
- 日终压缩必须由 `daily-compress` 执行，主模型不得手动模拟。

**BUG 处理：**
- 审计报告若发现数据缺失，自动补采，补采失败则标记 incomplete。
- 视频转录失败时，保留原始音频和部分转录文本，不得丢弃。

### 枢部（coordinator-agent、ctx-health、cross-dept-flow 等）

**预防：**
- 跨部门任务启动前，必须由 `cross-dept-flow` 生成任务依赖图，各方确认后才开始。
- `ctx-health` 每 5 轮对话检查一次上下文预算，超过 80% 自动触发 `daily-compress`。

**BUG 处理：**
- 协调器分配任务后，若目标部门 2 分钟内未确认接收，自动重新分配或升级为人工介入。
- 路由表更新后，必须在 10 分钟内运行 `backtest_runner.py` 验证，不通过自动回滚。

---

## 三、全局健康巡检（每周自动执行）

由 `weekly-audit-executor` 负责，检查以下指标：

| 指标 | 阈值 | 超标处理 |
|------|------|---------|
| 路由器调用率 | ≥90% | 低于 → 告警，审查违规记录 |
| Agent 失败率 | ≤5% | 超过 → 暂停该 Agent，通知协调 |
| 假报告嫌疑 | 0 容忍 | 发现 → 标记违规，人工复核 |
| 路由覆盖率 | ≥90% | 低于 → 自动建议新增关键词 |
| 数据源可用率 | ≥95% | 低于 → 触发情报部渠道巡检 |
| 日志完整性 | 100% | 缺失 → 补采或标记 |

---

## 四、应急处理流程

1. **发现** — 发现 BUG/异常 → 立即由 `errorlog` 捕获，写入 `last_error.txt`。
2. **评估** — `coordinator-agent` 评估是否影响核心任务。
3. **隔离** — 暂停问题 Agent/部门，切换备用路径。
4. **修复** — 指定部门修复，必须经 `code-review` 审查。
5. **验证** — `test-engineer` 跑满 100 次验证。
6. **复盘** — `weekly-audit-executor` 生成事件报告，更新容错规则。

---

## 五、与现有系统衔接

- 所有容错规则自动纳入 `delegation-mandate.md` 第19-24条。
- `task_router.py` 在输出 JSON 中加入 `retry` 和 `timeout_seconds` 字段。
- 外部监控脚本 `router_watchdog.py`、`log_verifier.py` 由 `dept-engineering` 创建并加入定时任务。
