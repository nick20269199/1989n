# 技术侦查日报 2026-05-12

## 交易策略 (1 item)
### TradingAgents — 来源: [GitHub](https://github.com/TauricResearch/TradingAgents)
- **做什么**: 71,400+星的多Agent AI系统，模拟华尔街完整研报+交易团队——分析师、多空辩论、交易员、风控。支持GPT/Claude/Gemini/Grok/DeepSeek及本地模型(Ollama)，无需GPU。
- **对我们的作用**: 可直接作为 adversarial-review 流水线的架构参考——它的多空辩论模式可以替换我们当前的对立审查流程。也可用于 vv-radar 转录后分析的自动化多角度交叉验证。
- **风险评估**: 成熟度极高(71.4K星)，MIT协议，活跃维护。无GPU需求，现有 DeepSeek API 可接。

## AI 智能体 (2 items)
### OpenSage — 来源: [arXiv](https://arxiv.org/html/2602.16891v2)
- **做什么**: 首个Agent自动开发工具包(ADK)，LLM自动创建Agent拓扑和工具集。Agent可动态创建/终止子Agent，自我编写工具函数，分层图内存管理。在 Terminal-Bench 2.0 等基准显著超越 Google/OpenAI/Claude/LangChain 官方 ADK。
- **对我们的作用**: SEL 自进化系统的参考架构——目前SEL需要手动设计进化路径，OpenSage的"自编程拓扑生成"概念可以自动化Lint→Digest→Connect→Evolve→Prune全流程。
- **风险评估**: 新发布(2026.03)，学术论文阶段，无稳定发布。参考架构概念，不宜直接集成。

### NVIDIA AI-Q (GTC 2026) — 来源: [NVIDIA News](https://nvidianews.nvidia.com/news/ai-agents)
- **做什么**: 开源Agent蓝图，登上 DeepResearch Bench 榜首。混合架构(前沿模型编排+ Nemotron 研究子Agent)，成本降低~50%。集成 NemoClaw 沙箱运行时的安全隔离+隐私路由器。
- **对我们的作用**: deep-research cron 任务的直接升级——当前用 DeepSeek 通道做后台研究，AI-Q 的混合架构(强模型规划+弱模型执行)可以显著降低 API 成本。
- **风险评估**: NVIDIA官方发布，企业级成熟度。需要NVIDIA NIM部署，可以仅参考架构不直接安装。

## 交易软件/工具 (1 item)
### FinMCP — 来源: [GitHub](https://github.com/Steve-sy/finmcp)
- **做什么**: 免API key的金融数据 MCP Server，通过 Yahoo Finance 提供实时报价、财报、期权链、机构持仓、新闻、美股筛选器、加密货币、外汇。可直接接入 Claude/ChatGPT 等 AI 助手。
- **对我们的作用**: 解决 Eastmoney WAF 阻断后的数据盲区——目前用 Sina/Tencent 做A股替代，但缺少美股数据(需通过akshare)。FinMCP 的 MCP 架构可以直接向 Claude 暴露实时金融数据，替代目前 daily_task.py 的硬编码数据路由。
- **风险评估**: 开源免费，Yahoo Finance 接口稳定性一般(需防限流)。建议作为美股数据补充通道，不替代核心A股通道。

## 前沿探索 (1 item)
### GPT-5.5 Instant — 来源: [eWeek](https://www.eweek.com/news/openai-gpt-55-instant-chatgpt-default-model/)
- **做什么**: OpenAI 5/5/2026 发布的新默认模型。幻觉减少52.5%(法律/金融/医学)，输出更简洁(~30%少词)，AIME 2025数学从65.4→81.2。新增记忆源透明度功能。
- **对我们的作用**: 推理质量提升直接影响 Claude Code 的分析准确性。52%幻觉率下降对交易分析(特别是持仓决断)意义重大——更少错误信号。
- **风险评估**: API可用，但需要更新依赖。与当前 DeepSeek V4 通道的性价比对比待评估。
