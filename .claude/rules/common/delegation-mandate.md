# 委派铁律 18 条

> 生效: 2026-05-28
> 关联: task-router/task_router.py, coordinator-agent

1. **全揽=事故** — 任何非闲聊任务，第一反应是"分给谁"，不是"怎么做"。

2. **路由前置** — 收到任务 → 立即执行 `python d:/1989n/task-router/task_router.py "<任务描述>"`，以输出为准。

3. **阻断即停止** — 若路由器返回 `status: blocked`，停止一切操作，追问用户/协调Agent，不得继续。

4. **严格按路由执行** — 若返回 agents/skills 列表，严格按列表顺序调用，不得增减，不得跳过。

5. **无"简单"例外** — 不得以"简单"为借口自己处理；简单任务也需显式分派或由路由器放行。

6. **文件操作只由工程部/知识管理 Agent** — 读/写/移动/删除，主模型不得直接执行。

7. **代码修改先审后存** — 代码修改必须经过 `code-review` Skill 审查后才能提交或保存。

8. **数据操作必须由指定 Agent** — 数据库读写、交易指令、飞书消息发送必须由对应 Agent 执行。

9. **部门映射** — 知识类→`dept-reading`，分析类→`dept-intelligence`，工程类→`dept-engineering`，通信类→`dept-front-office`。

10. **跨部门先协调** — 跨部门任务必须先调用 `coordinator-agent` 制定协作计划。

11. **严禁绕过** — 不得以任何理由绕过 `task-router` 直接调用工具或 Agent。

12. **报错读原文** — 任何错误报告必须先用 `errorlog` Skill 读取原始日志，不接受转述。

13. **修复后百次验证** — 修复代码后，必须由 `test-engineer` Skill 执行至少100次验证，并输出 sha256 校验。

14. **定时任务不模拟** — 日报/周报/清洗只能由对应 Skill（`morning-brief`/`weekly-audit`/`daily-compress`）触发，主模型不得模拟。

15. **敏感操作只限前厅部** — 用户权限、敏感信息、飞书群管理只允许 `dept-front-office` Agent 处理。

16. **会话结束压缩** — 每次会话结束前，由 `daily-compress` Skill 生成本次会话压缩摘要。

17. **审计日志** — 所有 Agent 调用必须记录到审计日志，供 `weekly-audit` 审查。

18. **不确定问协调** — 不确定该分给谁时，先问 `coordinator-agent`，不得猜测。

19. **执行日志强制记录** — 每次 Agent/Skill 调用后必须写日志到 `d:/1989n/logs/agent_exec/{YYYY-MM-DD}/{agent_name}.json`，必含 task/start_time/end_time/exit_code/output_summary/output_hash/agent/skill。

20. **超时重试与降级** — Agent/Skill 3 分钟无响应 → 重试一次；仍失败 → `coordinator-agent` 协调替代。某部门连续 3 次调用失败 → 自动暂停，走人工决策。

21. **外部校验** — `log_verifier.py` 每轮抽查 3 条日志，不一致连续两次 → 飞书告警+暂停对话。

22. **部门级容错** — 各部门按 `rules/common/fault-tolerance.md` 第二章执行，前厅部验证数据新鲜度+adversarial-review，情报部记录数据源质量+空数据告警+冲突校验，工程部改前 build-check+改后测试+改前备份，研发部新 Skill 沙箱测试+架构变更 adversarial-review，读书郎笔记含原文哈希+日终压缩不走主模型，枢部跨部门任务依赖图+路由更新 10 分钟内 backtest 验证。

23. **全局健康巡检** — `weekly-audit-executor` 每周检查路由器调用率≥90%/Agent失败率≤5%/假报告0容忍/路由覆盖≥90%/数据源可用≥95%/日志完整100%。

24. **应急处理流程** — BUG 发现→errorlog 捕获→coordinator 评估影响→隔离问题部门→code-review 修复→test-engineer 100次验证→weekly-audit 复盘更新规则。

25. **桌面文件即事实来源** — 飞书/Web 推送必须以最新桌面文件为数据源，禁止独立生成推送内容。推送前验证桌面文件存在且非空。

26. **文件命名国际化** — 所有输出文件路径和文件名使用英文（snake_case），仅文件内容可使用简体中文。

27. **推送前一致性校验** — 飞书推送前校验消息长度和内容完整性。推送失败须记录日志并尝试备用通道，不得沉默跳过。

> 完整容错规则详见 `rules/common/fault-tolerance.md`

## 违反处理

违反任一条 = 零号标准处理：立即停止 → 记录违反事实 → 修正后从断点重新执行 → 写入 memory/feedback/
