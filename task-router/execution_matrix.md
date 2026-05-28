# 部门 → Agent → Skill → 关键词 执行矩阵

> 生成: 2026-05-28 | 基于: route_map.yaml v2 | 合计: 81 个路由单元 + 12 条正则

## 关键词路由

| 部门 | Agent | Skill | 触发关键词 |
|------|-------|-------|-----------|
| **前厅部** | stock-analysis | stock-analysis | 股票分析, 分析, 选股, 量化回测, 回测结果, 回测报告, 量化, 行情, K线, 技术面, 持仓, 盈亏, 当前持仓, 走势, 操作建议 |
|  | stock-deep | stock-deep | 深度分析, 基本面, 开仓, 调仓, 加仓, 建仓 |
|  | stock-quick | stock-quick | 快速行情, 盘中, 闪电, 快查 |
|  | adversarial-review | adversarial-review | 止损, 风控, 风险评估, 安全审查, -7% |唉我真的 你找出来 是你 嗯 
|  | morning-brief | morning-brief | 晨报, 早报, morning brief, 盘前, 简报, 早晨, 晨间简报 |
|  | dept-front-office | dept-front-office | 发送飞书, 发飞书, 推送到飞书, 飞书消息, 飞书通知, 飞书群 |
| **情报部** | dept-intelligence | data-verify | 数据采集, 新闻, 爬虫, 多源, 通道, 数据校验, 健康检查, 保鲜, 新鲜度 |
|  | dept-intelligence | vv-leida | 大V雷达, 抖音, 雪球, 大V监控 |
| **工程部** | python-reviewer | python-review | Python审查, Python代码, PEP 8, Python.*代码审查 |
|  | typescript-reviewer | code-review | TypeScript审查, JavaScript审查, TS代码, JS代码, Node.*审查 |
|  | go-reviewer | go-review | Go审查, Go代码, Golang.*审查 |
|  | rust-reviewer | rust-review | Rust审查, Rust代码, Rust.*审查 |
|  | java-reviewer | java-review | Java审查, Spring Boot.*审查, Java代码 |
|  | cpp-reviewer | cpp-review | C++审查, C++代码, Cpp.*审查 |
|  | csharp-reviewer | csharp-review | C#审查, .NET审查, CSharp.*审查 |
|  | kotlin-reviewer | kotlin-review | Kotlin审查, Android.*审查, Compose.*审查, Kotlin代码 |
|  | flutter-reviewer | flutter-review | Flutter审查, Dart审查, Flutter代码 |
|  | healthcare-reviewer | healthcare-phi-compliance | 医疗代码, PHI, HIPAA, 医疗系统, 临床安全 |
|  | code-review | code-review | 代码审查, code review, PR, 静态分析, 代码质量, 安全漏洞, 审查代码 |
|  | security-reviewer | security-review | 安全审计, OWASP, 注入, XSS, 密钥, 敏感数据 |
|  | build-error-resolver | build-fix | 构建错误, 编译错误, 测试失败, 类型错误, lint |
|  | silent-failure-hunter | silent-failure-hunter | 静默失败, 吞错误, 坏后备, 异常传播 |
|  | code-explorer | explore | 代码探索, 追踪执行路径, 依赖分析, 调用链, 数据溯源, 数据流, 数据断链, 管线追踪 |
|  | test-engineer | test-engineer | 测试, pytest, 覆盖率, 单元测试, 集成测试, 验证脚本, 回测验证, 脚本测试, 跑测试 |
|  | e2e-runner | e2e-testing | E2E测试, Playwright, 冒烟测试, 浏览器测试 |
|  | pr-test-analyzer | code-review | PR测试, 测试质量, 测试覆盖 |
|  | performance-optimizer | performance-optimizer | 性能优化, 性能分析, 瓶颈, 内存泄漏, 渲染优化, 包体积, 管线慢 |
|  | harness-optimizer | ctx-health | Harness优化, 配置优化, hooks优化, 上下文优化, harness审计 |
|  | harness-auditor | skill-stocktake | harness诊断, 模块健康, harness审计 |
|  | doc-updater | code-review | 文档更新, README, 代码地图, CODEMAP |
|  | docs-lookup | docs-lookup | 文档查询, API参考, 库用法, Context7 |
|  | comment-analyzer | code-review | 注释, 注释分析, 注释质量, 注释过时 |
|  | code-simplifier | refactor-clean | 代码精简, 代码简化, 死代码, 重复代码, 冗余代码 |
|  | refactor-cleaner | prune | 重构清理, 死代码清理, 依赖清理 |
|  | database-reviewer | data-verify | 数据库, SQL, PostgreSQL, 查询优化, Schema |
|  | user-image-vision | user-image-vision | 图片, 图像, OCR, 视觉, 图像识别, 图里, 图中, 看图 |
|  | errorlog | errorlog | 错误日志, last_error.txt, 报错, traceback, 异常 |
|  | debugger | debugger | 调试, 根因分析, 错误修复, debug |
|  | dept-engineering | dept-engineering | 部署, 发布, 生产环境, 上线, 生产部署, 版本发布, 发布到生产, 重启服务器, 重启服务, 重启生产, 重启生产服务器, 写入文件, 写文件, 生成文件, 创建文件, 输出到, 保存到, 写入, 写进 |
|  | a11y-architect | code-review | 无障碍, a11y, WCAG, ARIA, 辅助功能 |
|  | type-design-analyzer | code-review | 类型设计, 类型安全, 非法状态, 类型封装 |
|  | seo-specialist | seo | SEO, 搜索引擎优化, 页面优化, 结构化数据, 核心网页指标 |
|  | go-build-resolver | go-build | Go构建, go build, Go编译 |
|  | rust-build-resolver | rust-build | Rust构建, cargo, Rust编译 |
|  | java-build-resolver | gradle-build | Java构建, Maven, Gradle |
|  | cpp-build-resolver | cpp-build | C++构建, CMake, C++编译 |
|  | kotlin-build-resolver | kotlin-build | Kotlin构建, Gradle构建 |
|  | dart-build-resolver | flutter-build | Dart构建, Flutter构建, pub |
|  | pytorch-build-resolver | build-fix | PyTorch, CUDA, 张量错误, 训练错误 |
| **研发部** | architect | blueprint | 架构, 系统设计, 重构, 模块化, 技术决策 |
|  | code-architect | blueprint | 蓝图, 实施计划, 分步, 多agent方案 |
|  | planner | explore | 规划, 功能实现, 复杂度, 实施步骤 |
|  | deep-research | deep-research | 深度研究, 知识缺口, DeepSeek研究 |
|  | skill-creator | skill-creator | Skill创建, 新Skill, 技能管理 |
|  | explore | explore | 探索, 项目地图, 调用链路, 代码地图 |
|  | structured-exploration | structured-exploration | 结构化探索, 试到调, 迭代探索 |
|  | opensource-forker | skill-stocktake | 开源自研, 开源打包, 开源清理, 开源分叉 |
|  | opensource-packager | skill-stocktake | 开源发布, 开源打包 |
|  | opensource-sanitizer | security-review | 开源安全, 开源验证, 泄露扫描 |
| **读书郎** | dept-reading | knowledge-chinese-civ | 读书笔记, 知识整理, 知识图谱, graphify, 读书内容, 整理.*笔记, 读书, 书摘, 书单, 穿透 |
|  | dept-reading | knowledge-religion | 认知偏差, 自我审查, 元认知, 四毋, 宗教, 信仰, 神学, 佛, 道, 儒 |
|  | dept-reading | knowledge-physics | 知识管理, 学习路径, 认知进化, 无标度, 量子, 物理, 力学, 相对论, 熵, 混沌, 涌现, 复杂系统 |
|  | daily-compress | daily-compress | 复盘, 收盘, daily compress, 压缩 |
|  | daily-load | daily-load | 晨间, daily load, 认知加载 |
|  | weekly-audit-executor | weekly-audit | 周审计, 周报, 审计, weekly audit, 审查.*日志, 违规, 调用日志, 审计日志 |
|  | user-video-learn | user-video-learn | 视频, 转录, 字幕, 学习视频, B站 |
|  | session-learner | continuous-learning | 会话学习, 经验提取, 记忆写入 |
| **枢部** | knowledge-economics | knowledge-economics | 多Agent调度, 编排, 分工, 比较优势, 风险评估, 安全策略, 止损设计, 胖尾, 市场分析, 交易决策, 投资判断, 安全边际 |
|  | knowledge-chinese-civ | knowledge-chinese-civ | 系统架构, 模块设计, 可逆装配, 榫卯 |
|  | knowledge-physics | knowledge-physics | 推理质量, 效率优化, 推理停止, 混沌边缘 |
|  | cross-dept-flow | cross-dept-flow | 跨部门, 协作, 状态跟踪, 部门间 |
|  | ctx-health | ctx-health | 上下文预算, 上下文, token, 窗口优化, 上下文清洁, 太长.*清理, 清理.*上下文 |
|  | 先搜后做 | 先搜后做 | 先搜索, 先研究, 找现有工具, 避免重复 |
| **工程部** | gan-evaluator | gan-evaluator | GAN评估, GAN测试, 应用测试, 评分 |
|  | gan-generator | gan-generator | GAN生成, 功能实现, 迭代开发 |
| **研发部** | gan-planner | gan-planner | GAN规划, 规格说明, 产品规划 |
| **工程部** | conversation-analyzer | conversation-analyzer | 会话分析, 对话模式, 交互模式 |
|  | user-planning-with-files | user-planning-with-files | 规划文件, 任务跟踪, 进度管理, task_plan |
|  | 循环执行 | 持续循环 | 循环执行, 自主循环, 持续循环, loop调度 |
| **枢部** | 总调度 | 先搜后做 | 消息分类, 邮件分类, 沟通分诊, 通信协调 |
|  | coordinator-agent | cross-dept-flow | 协调, 分诊, 路由决策, 任务归属, 不清楚该谁 |

## 正则路由（补充匹配）

| 正则模式 | Agent | Skill |
|---------|-------|-------|
| `.*(错误|异常|失败|报错).*(日志|log|traceback).*` | errorlog | errorlog |
| `.*(评估|检查|诊断|审计).*(agent|Agent|技能|skill|系统).*` | gan-evaluator | skill-stocktake |
| `.*(开仓|买入|卖入|加仓).*(股票|代码|symbol|代码).*` | adversarial-review | adversarial-review |
| `.*(语法|门禁|gate|import|检查).*(代码|文件|脚本).*` | build-error-resolver | code-review |
| `.*(对话|会话).*(太长|压缩|清理|clear|超过).*` | ctx-health | ctx-health |
| `.*(部署|上线|发布|release).*(脚本|配置|服务).*` | planner | blueprint |
| `.*(备份|迁移|搬家).*(数据|配置|文件).*` | code-explorer | explore |
| `.*(注释|文档).*(过时|不准确|更新|修复).*` | comment-analyzer | code-review |
| `.*(Agent|agent|技能|skill|系统).*(不工作|故障|挂了|坏了|异常|无法运行).*` | gan-evaluator | gan-evaluator |
| `.*(无障碍|辅助功能|屏幕阅读器|键盘导航).*` | a11y-architect | code-review |
| `.*(开源).*(发布|分叉|fork|清理|安全|验证).*` | opensource-forker | skill-stocktake |
| `.*(不确定|不知道|不清楚).*(该谁|路由|部门|分配|协调).*` | coordinator-agent | cross-dept-flow |

## 兜底路由

| 条件 | Agent | Skill |
|------|-------|-------|
| 未匹配任何路由 | coordinator-agent | cross-dept-flow |