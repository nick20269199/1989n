# 技术侦查日报 2026-05-11

## 交易策略 (3 items)

### AlphaCrafter — 多Agent量化选股框架
- **来源**: https://www.catalyzex.com/paper/alphacrafter-a-full-stack-multi-agent (arXiv, NeurIPS 2026)
- **做什么**: 三个 LLM Agent 协作 — Miner 挖因子、Screener 做 regime 条件集成、Trader 做风险约束执行，在 CSI 300 和 S&P 500 上跑赢基准
- **对我们的作用**: 我们持仓 5 只全是 A 股，CSI 300 测试结果直接可用；Miner→Screener→Trader 三段式与我们的 analysis→adversarial-review→execution 管道同构，Miner 逻辑可融入 daily_task.py 的因子挖掘
- **风险评估**: 论文阶段，仓库未开源，需关注后续代码发布

### FinRL-X — AI原生模块化量化基础设施
- **来源**: https://export.arxiv.org/abs/2603.21330 (PAKDD 2026)
- **做什么**: 统一数据处理→策略构建→回测→券商执行的全栈框架，支持 RL 分配器和 LLM 情绪信号
- **对我们的作用**: 模块化设计可直接借鉴其数据管道架构优化我们的 stock_data 流水线；LLM 情绪信号模块可集成到 intraday_report.py
- **风险评估**: 框架成熟度待验证，依赖较多云端组件

### StratEvo — 遗传算法自动挖因子
- **来源**: https://github.com/NeuZhou/stratevo / PyPI: stratevo
- **做什么**: 遗传算法在 484 个市场因子中自动发现权重组合，walk-forward 验证，实盘 Crypto Sharpe 2.89、美股年化 45%
- **对我们的作用**: 因子自动发现机制可移植到 A 股，替代手工技术指标筛选；walk-forward 验证方法论可直接用于我们的回测框架
- **风险评估**: 活跃维护（2026），PyPI 可装，需适配 A 股数据源（AKShare 对接）

---

## AI 智能体 (3 items)

### DeepSeek V4 已发布
- **来源**: LLM-stats.com + 多源确认
- **做什么**: DeepSeek 最新代码模型，与 GLM-5.1/MiniMax M2.7/Kimi K2.6 同期发布，中国开源模型编程能力接近西方前沿
- **对我们的作用**: 我们 .env 里配了 6 个 DeepSeek API 通道，V4 升级后 agent 推理质量直接提升；需确认 API endpoint 是否需要切换
- **风险评估**: 确认 API 兼容性和配额

### ZeroClaw — Claude Code 多 MCP 路由器
- **来源**: https://github.com/IKingBarou/Zeroclaw-Plugin-Hub (2847 stars)
- **做什么**: Agentic CLI 框架，多 MCP 路由编排器，支持子 agent、自适应上下文路由和 skill 插件
- **对我们的作用**: 我们的 13 个定时任务 + 多个 skill 需要一个统一编排层，ZeroClaw 的 MCP 路由模式可参考用于我们的 cron 调度优化；子 agent 隔离上下文窗口可降低每天 30+ 次调用的上下文膨胀
- **风险评估**: 项目较新（2026-01），GitHub 星星 2847，需评估稳定性

### Claude Code Channels — 飞书直接对接
- **来源**: https://indianexpress.com/article/technology/artificial-intelligence/what-is-claude-code-channels-anthropic-openclaw-ai-agents-10595037/
- **做什么**: Claude Code 通过 MCP 接入 Telegram/Discord，手机端实时交互
- **对我们的作用**: 我们已有飞书 Bot（FEISHU_BOT_PORT=19899），可以参考 Channels 的 MCP 架构升级飞书 Bot，让手机端直接触发 daily_task.py 和查看持仓状态
- **风险评估**: 官方功能，稳定；飞书适配需自己写 bot→MCP 映射

---

## 交易软件/工具 (2 items)

### AKShare — A股数据 API (持续活跃)
- **来源**: https://github.com/akfamily/akshare (2026-04-28 更新)
- **做什么**: 统一 pandas 接口覆盖 A 股/期货/期权/ETF/外汇/债券/宏观，数据源含东方财富/新浪/沪深交易所
- **对我们的作用**: 我们的 stock_data 采集可能已有类似来源，AKShare 可作为备选数据源，东方财富和交易所原始数据比我们的腾讯 API 更快更全
- **风险评估**: MIT 协议，成熟项目，可直接 pip install

### intraday-prices — 日内 OHLCV 数据清洗管道
- **来源**: https://github.com/vivek-v-rao/intraday-prices
- **做什么**: 多供应商日内 OHLCV 抓取/清洗/缓存/拼接，解决数据不一致问题
- **对我们的作用**: 我们的 intraday_report.py 每 30 分钟跑一次，数据质量直接决定信号准确度；这套清洗管道可减少"数据源返回 0/None"类问题
- **风险评估**: 需对接 A 股数据源（原项目主要支持美股）

---

## 前沿探索 (1 item)

### State of AI: May 2026 — 中国编程模型追平西方
- **来源**: https://press.airstreet.com/p/state-of-ai-may-2026
- **做什么**: 月频 AI 行业全景报告，5 月要点包括中国开源模型在 agentic coding 上接近西方前沿、AI 安全对抗升级、模型幻觉率大幅下降
- **对我们的作用**: 作为每日交易决策的上下文背景 — "AI 行业格局正在剧烈变化"这个事实影响我们对半导体/科技链持仓的判断（通富微电、光力科技）
- **风险评估**: 信息来源可靠，作为背景参考不直接产生交易信号
