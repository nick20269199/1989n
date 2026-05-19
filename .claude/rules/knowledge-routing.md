# 知识路由表 — 自动注入，每次会话生效

## 路由规则

当任务涉及以下领域时，必须先加载对应 Skill 获取完整知识框架，再开始推理：

| 任务关键词 | 加载 Skill | 包含内容 |
|-----------|-----------|---------|
| 多Agent调度/协作/分工/编排 | knowledge-economics + knowledge-physics | 比较优势分配/局部知识/自组织治理/同步多样性/涌现简约 |
| 风险评估/安全策略/止损设计 | knowledge-economics + knowledge-physics | 胖尾安全/最小最大策略/期权式探索/多因素共振 |
| 推理质量/效率优化/推理停止 | knowledge-religion + knowledge-physics | 知止/元递归限制/熵预算/自由能最小化/混沌边缘 |
| 认知偏差/自我审查/元认知 | knowledge-religion + knowledge-chinese-civ | 四毋/吾丧我/双模观察/偏差即信号/实时校准 |
| 市场分析/交易决策/投资判断 | knowledge-economics + knowledge-chinese-civ | 安全边际/Mr.Market/乘数定位/乘法质量/实时校准 |
| 系统架构/模块设计/重构 | knowledge-economics + knowledge-chinese-civ | 可逆装配/渐进重构/嵌套分层/榫卯接口 |
| 知识管理/学习路径/认知进化 | knowledge-physics + knowledge-religion | 无标度知识/优先连接/致曲专精/Ghazali三阶段 |
| 工程部/Lint/知识库维护/SEL | project/session-engineering-manifest.md | 工程部上下文规范 — Lint任务/认知审计 |
| 前厅部/交易/持仓/盘前简报 | project/session-front-office-manifest.md | 前厅部上下文规范 — 股票分析/决策 |

## 触发条件

上述关键词在对话中出现任意一个 → 用 Skill 工具加载对应 knowledge Skill → 获取完整原则后再推理。
不确定是否需要加载时 → 默认加载，加载成本远小于推理偏差成本。
