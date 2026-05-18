# 技术侦查日报 2026-05-16

## AI 智能体 (2 items)
### Claude Code 2.1.0 — Agent生命周期钩子 — 来源: [VentureBeat](https://venturebeat.com/orchestration/claude-code-2-1-0-arrives-with-smoother-workflows-and-smarter-agents)
- **做什么**: Claude Code 2.1.0新增PreToolUse/PostToolUse/Stop生命周期钩子、forked sub-agent context、wildcard工具权限、hot reload技能。Agent在权限拒绝后继续执行。
- **对我们的作用**: cron任务链可使用PreToolUse钩子插入checkpoint/rollback逻辑（如data_guard.py在写文件前校验），forked sub-agent context可替代当前token膨胀的子Agent编排。wildcard权限(Bash npm *)减少权限弹窗。
- **风险评估**: Anthropic官方发布，成熟度5/5。pip update即可升级，零集成成本。

### Claude Skill-Creator Evals — 多Agent技能评估 — 来源: [claude.com/blog/improving-skill-creator](https://claude.com/blog/improving-skill-creator)
- **做什么**: 技能创建器新增Evals(测试技能防止回归)、Benchmark mode(标准化评估)、多Agent并行评估(消除上下文污染)、Comparator Agent(双版本盲测A/B)。
- **对我们的作用**: 直接用于我们技能开发流程——每日复盘/daily-compress等技能可用benchmark mode量化质量变化，Comparator Agent做版本A/B测试。
- **风险评估**: Anthropic官方，成熟度4/5。需要主动使用Evals功能，不自动生效。

## 交易软件/工具 (2 items)
### FinMCP — 免费金融数据MCP服务器 — 来源: [GitHub](https://github.com/Steve-sy/finmcp)
- **做什么**: MCP协议连接AI助手(Claude/ChatGPT/Cursor)到全球50+交易所实时金融数据。15个工具：实时报价、财务报表、期权链、分析师共识。**免费开源，无API Key**，数据源Yahoo Finance。
- **对我们的作用**: 直接作为market_pool的全球市场补充数据源。当前market_pool聚焦A股(腾讯API)，美股/全球指数通过akshare获取。FinMCP提供MCP原生接口，可在Claude Code中直接调用实时报价/期权链做持仓分析。
- **风险评估**: 开源免费(MIT未明确但代码公开)，依赖Yahoo Finance稳定性。备用数据源角色，不影响主链路。

### wrtrade — Polars超快回测框架 — 来源: [PyPI](https://pypi.org/project/wrtrade/)
- **做什么**: 基于Polars的极速回测(10-50x pandas)，极简API：Portfolio + backtest() + validate()。内置Kelly仓位优化、permutation testing验证、tear sheets可视化、CLI部署。
- **对我们的作用**: 当前trade_backtest.py基于pandas回测，大数据量(全市场4411只)性能瓶颈。wrtrade的Polars向量化可大幅提速，Kelly优化可替代当前固定的仓位管理逻辑。
- **风险评估**: 较新项目(2026)，PyPI可安装，但社区规模未知。可先在单策略回测中试用，不替换现有框架。

## 交易策略 (1 item)
### Hubble — LLM因子挖掘安全沙箱 — 来源: [arXiv](https://arxiv.org/html/2604.09601v1)
- **做什么**: LLM驱动的闭环因子挖掘框架，AST语法树沙箱保证因子代码100%计算稳定性，无崩溃/异常。30只美股752天回测峰值综合评分0.827。强调可解释性和安全约束。
- **对我们的作用**: AST沙箱验证逻辑可直接借鉴到StratEvo因子生成的代码校验环节——当前因子生成可能产生异常计算(如除零)，Hubble的AST预检查可以100%拦截。
- **风险评估**: 论文级(arXiv 2026-04)，无稳定代码库。方法论参考——AST沙箱概念可独立实现(50行Python)，无需依赖论文代码。

## 前沿探索 (1 item)
### GPT-5.5 Instant — 幻觉降低52.5% — 来源: [The Peninsula](https://s.thepeninsula.qa/article/06/05/2026/openai-launches-gpt-55-instant)
- **做什么**: OpenAI 2026-05-06发布，金融/医疗/法律场景幻觉降低52.5%，历史标记对话不准确声明减少37.3%。新增"memory sources"透明功能。
- **对我们的作用**: LLM信号可信度重新评估——幻觉率减半意味着LLM信号在daily_task.py信号聚合中的权重可上调(当前因幻觉风险压低权重)。记录到llm-confidence.md供后续权重校准参考。
- **风险评估**: OpenAI产品级，成熟度5/5。非集成项，信息参考。
