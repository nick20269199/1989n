# 每日技术侦查报告 | 2026-05-14

## Lane 1: Trading Strategy

### 1. Autoresearch-trading — LLM+进化策略发现
- **来源**: GitHub (具体仓库名见搜索结果)
- **核心**: LLM驱动交易策略的自动研究与进化，与Strat-LLM的Alignment Tax互补
- **切入点**: 结合StratEvo遗传算法因子发现，用LLM替代随机变异算子，加速收敛
- **use_for**: daily_task.py信号聚合的进化优化，LLM作为"定向变异"引擎而非全权决策者
- **匹配度**: 4/5 | **成熟度**: 3/5 | **集成成本**: 中

### 2. WEEX Alpha Awakens — GMM体制分类+多Agent
- **来源**: WEEX竞赛方案
- **核心**: GMM (高斯混合模型) 对市场状态分类，每个状态分配独立Agent策略
- **切入点**: 直接映射到cycle_stage判定——用GMM替代当前的手动规则判定，分配不同策略权重
- **use_for**: daily_compress.py的周期阶段判定升级，从规则引擎→概率模型
- **匹配度**: 5/5 | **成熟度**: 3/5 | **集成成本**: 中高

---

## Lane 2: AI Agent

### 1. When2Tool (Probe&Prefill) — 工具调用必要性检测
- **来源**: arXiv 2605.09252 (May 10, 2026)
- **核心**: LLM隐藏状态中线性可解码"是否需要工具调用"(AUROC 0.89-0.96)，Probe&Prefill减少48%不必要工具调用
- **切入点**: 当前每日任务链中大量冗余工具调用（如重复检查稳定文件），可减少约50%的API消耗
- **use_for**: daily_task.py/cron任务链的工具调用优化，减少token浪费
- **匹配度**: 4/5 | **成熟度**: 3/5 | **集成成本**: 低（论文级，概念可借鉴）

### 2. SkillMaster — 自主技能掌握 (DualAdv-GRPO)
- **来源**: arXiv 2605.08693 (May 9, 2026)
- **核心**: Agent在任务解决过程中自主创建/优化/选择技能，ALFWorld+8.8%, WebShop+9.3%
- **切入点**: SEL循环的技能进化可借鉴——当前是手动prune技能，SkillMaster是自动技能调优
- **use_for**: SEL Growth Loop的技能进化自动化
- **匹配度**: 3/5 | **成熟度**: 2/5 | **集成成本**: 高

---

## Lane 3: Trading Software/Tools

### 1. Investing Algorithm Framework (v8.6.0) — 全栈量化框架
- **来源**: GitHub coding-kitties/investing-algorithm-framework
- **核心**: Polars向量化回测 + 事件驱动模拟 + MCP服务器(Claude/Copilot可查回测) + 自包含HTML面板
- **独特点**: **内置MCP Server**——AI Agent可以直接查询回测结果，无需解析日志文件
- **use_for**: 回测报告查询的MCP接口参考；Polars向量化回测替代当前pandas回测
- **匹配度**: 4/5 | **成熟度**: 4/5 | **集成成本**: 中

### 2. open-market-data (omd) — AI Agent原生金融数据CLI
- **来源**: npmjs.com/package/open-market-data
- **核心**: Node.js CLI/AI Agent技能，从免费公开API获取股票/财报/加密/经济数据，无需API Key
- **独特点**: 专为AI Agent设计——Claude Code/GitHub Copilot可直接调用
- **use_for**: market_pool的数据源补充，尤其是美股/全球数据的CLI获取通道
- **匹配度**: 3/5 | **成熟度**: 3/5 | **集成成本**: 低

---

## Lane 4: Frontier/AI Breakthroughs

### 1. OpenAI GPT-5.5 Instant — 幻觉降低52.5%
- **来源**: OpenAI May 6, 2026
- **核心**: 高风险场景(医疗/法律/金融)幻觉降低52.5%，历史标记对话不准确声明减少37.3%
- **对交易的影响**: LLM金融信号可靠性大幅提升——之前LLM分析被质疑的核心问题就是幻觉
- **use_for**: LLM信号可信度重新评估，如果幻觉率确实减半，信号聚合权重可上调
- **匹配度**: 3/5 | **成熟度**: 5/5 | **集成成本**: 低

### 2. "Warm-up Training" — AI学会说"不知道"
- **来源**: Nature Machine Intelligence (May 11, 2026)
- **核心**: 受人类大脑不确定性信号启发，训练AI在不确定时主动承认而非幻觉
- **对交易的影响**: LLM置信度校准——当LLM对市场判断不确定时，系统应降低其信号权重
- **use_for**: llm_competence_check()的置信度校准参考，不确定性-aware信号聚合
- **匹配度**: 3/5 | **成熟度**: 2/5 | **集成成本**: 概念级

---

## 过滤说明

| Lane | 原始结果 | 入选 | 排除原因 |
|------|---------|------|---------|
| Trading Strategy | 7 | 2 | QTMRL/Quantalytics/IMC过于通用，FYP/Sniper策略细节不透明 |
| AI Agent | 6 | 2 | MCP-Cosmos已在之前记录；Google/Azure SDK是基础设施非突破 |
| Trading Software | 6 | 2 | nanoback/Kairos专注加密(非A股)；Factor Engine待下轮评估 |
| Frontier | 7 | 2 | Thinking Machines/Anthropic法律版与交易关联度低 |
