# 1989n 量化交易系统

## 当前持仓 (7只) — 每次会话必须记住 (最后更新: 2026-05-11 盘中)

| 代码 | 名称 | 持仓(股) | 成本价 | 止损(-7%) | 行业 |
|------|------|---------|--------|----------|------|
| 000062 | 深圳华强 | 2000 | 37.28 | 34.67 | 电子元器件分销 |
| 002156 | 通富微电 | 2200 | 49.77 | 46.29 | 半导体封测 |
| 300480 | 光力科技 | 200 | 36.28 | 33.74 | 半导体划片设备 |
| 002407 | 多氟多 | 600 | 36.25 | 33.71 | 锂电化工 |
| 300342 | 天银机电 | 200 | 64.56 | 60.04 | 商业航天/军工电子 |
| 300739 | 明阳电路 | 100 | 29.72 | 27.64 | PCB/电子 |
| 601789 | 宁波建工 | 600 | 6.36 | 5.91 | 建筑工程/基建 |

## 路径配置（硬约束）

| 路径 | 用途 |
|------|------|
| `D:/1989n/stock_analysis/` | 代码主目录 |
| `D:/1989n/stock_data/` | 所有数据文件（JSON/CSV/DB） |
| `D:/1989n/stock_data/last_error.txt` | 最后一次脚本报错的完整 traceback |
| `D:/1989n/stock_data/stock.db` | SQLite 数据库 |
| `D:/1989n/screenshots/` | 截图存储 |
| `D:/1989n/.claude/` | Claude Code 配置 |

**铁律**：所有数据写入必须在 `D:/1989n/stock_data/` 下，禁止写到项目源码目录。

## 核心定时任务

| 脚本 | 触发时间 | 功能 |
|------|---------|------|
| `call_auction.py` | 工作日 9:26 | 集合竞价数据采集 |
| `daily_task.py morning_enhanced` | 工作日 9:28 | 盘前增强简报 |
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
|---------|---------|
| 风险评估/止损/安全策略 | `knowledge-economics` + `knowledge-physics` |
| 多Agent调度/系统架构/模块设计 | `knowledge-economics` + `knowledge-chinese-civ` |
| 推理质量/效率/停止条件 | `knowledge-religion` + `knowledge-physics` |
| 认知偏差/自我审查/元认知 | `knowledge-religion` + `knowledge-chinese-civ` |
| 市场分析/交易决策/投资判断 | `knowledge-economics` + `knowledge-chinese-civ` |
| 知识管理/学习路径/认知进化 | `knowledge-physics` + `knowledge-religion` |

路由判断原则：不确定是否需要加载 → 默认加载。加载成本远小于推理偏差成本。

蒸馏产出目录: `stock_data/economics_reading/` (80本), `stock_data/religion_reading/` (100+本), `stock_data/physics_reading/` (50本), `stock_data/chinese_civilization/` (22部) — 完整原始产出供深入查阅。
