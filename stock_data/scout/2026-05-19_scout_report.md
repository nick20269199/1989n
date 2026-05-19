# 技术侦查日报 2026-05-19

## 交易策略 (2 items)

### Awesome-LLM-Quantitative-Trading-Papers — 来源: [GitHub](https://github.com/Tom-roujiang/Awesome-LLM-Quantitative-Trading-Papers)
- **做什么**: LLM量化交易论文精选集，收录ICLR/KDD/ACL 2026 + NeurIPS 2025论文，覆盖Trading Agents/因子挖掘/RL交易
- **对我们的作用**: 替代零散手工搜索——直接获得2026年顶会量化交易论文全景图，因子挖掘管道(Trading-R1, Alpha-R1)和RL交易方向可对标
- **风险评估**: GitHub资源列表，MIT协议，持续更新

### Daily Return Information Factor (DRIF) — 来源: [Alpha Architect](https://alphaarchitect.com/daily-stock-returns/)
- **做什么**: 约90年美股数据发现"日收益率时序信息"因子，月收益1.57%，Sharpe 1.23，超越150+已知异象
- **对我们的作用**: 候选因子——日收益率时序模式可集成到tech_scan.py信号体系，与现有三倍量/动量因子互补
- **风险评估**: 实证研究，非代码库。需在A股验证(市场结构差异)。Alpha Architect持续更新。

### MSCI非线性因子效应 (Mar 2026) — 来源: [MSCI Blog](https://www.msci.com/research-and-insights/blog-post/transparency-and-insights-into-nonlinear-factor-effects-through-market-regimes)
- **做什么**: MSCI用Random Forest+SHAP分析ML因子在AI驱动市场中的权重漂移——流动性+残差波动影响力上升，动量相对下降
- **对我们的作用**: 间接——验证因子权重需要动态调整，当前StratEvo遗传算法的walk-forward验证已覆盖，无需额外操作
- **风险评估**: 机构研究参考，非代码

## AI 智能体 (2 items)

### Tool Attention: 消除MCP/工具Token税 — 来源: [arXiv:2604.21816](https://browse-export.arxiv.org/abs/2604.21816)
- **做什么**: 两阶段惰性schema加载+意图重叠评分，减少95%工具调用token(47.3k→2.4k)，上下文利用率24%→91%
- **对我们的作用**: 直接解决cron任务链context膨胀问题——当前13个cron共享上下文，"工具税"占大部分。惰性加载模式可参考设计cron链的checkpoint/rollback
- **风险评估**: 论文级(arXiv)，无代码。方法论参考——设计模式可提取但无需直接集成

### EnvFactory: 可执行环境合成+RL训练工具Agent — 来源: [arXiv:2605.18703](https://arxiv.org/html/2605.18703v1)
- **做什么**: 自动从真实资源创建有状态可执行工具环境，合成多轮轨迹训练Agentic RL。85个环境→Qwen3在BFCLv3 +15%, MCP-Atlas +8.6%
- **对我们的作用**: SEL Growth Loop自动化参考——当前skill进化依赖手工反馈，EnvFactory模式可实现自动环境合成→RL训练管道
- **风险评估**: 论文级，Meta/UMD研究。方法论参考——当前SEL架构已覆盖基础，不需立即跟进

## 交易软件/工具 (2 items)

### SEC EDGAR Open Dataset (43B Tokens) — 来源: [Hugging Face / daft.ai](https://www.daft.ai/blog/sec-edgar-case-study)
- **做什么**: SEC全部历史披露(10-K/10-Q/8-K)开源数据集——8M样本/590GB/43B tokens，2026-04-09发布，MIT协议
- **对我们的作用**: 基本面分析数据源——当前公司背调靠手工搜索，EDGAR数据集可自动化年报/季报/重大事项分析管道
- **风险评估**: 数据量大(590GB)，需本地或云存储。SEC覆盖美股——A股不可用。

### FinMCP: 免费金融数据MCP服务器 — 来源: [GitHub: Steve-sy/finmcp](https://github.com/Steve-sy/finmcp)
- **做什么**: MCP协议连接AI到50+交易所实时数据(含ASX/LSE/crypto/forex)，15工具，免费开源无API Key
- **对我们的作用**: market_pool全球数据补充通道——通过MCP直接让Claude Code查询实时报价/US期权链/分析师共识
- **风险评估**: 较新项目，Yahoo Finance数据源稳定性不确定。pip+MCP配置即可集成，低风险试用。

## 前沿探索 (1 item)

### Qwen3.6-27B: 单GPU跑赢397B MoE — 来源: Alibaba (May 2026)
- **做什么**: 27B参数模型在多项基准上击败397B MoE模型，仅需18GB显存(单GPU)，支持本地部署
- **对我们的作用**: 本地部署候选——当前依赖在线API(DeepSeek/Claude)，Qwen3.6可在本地运行推理任务(因子生成/信号聚合)降低成本+延迟
- **风险评估**: 阿里系模型，开源许可证待确认。27B参数量级适合推理而非前沿研究。估值因子/技术分析类任务可用。
