# 侦查评估报告 — 2026-05-15

**评估日期**: 2026-05-15
**评估条目**: 8条 (20260514-001~008 全部)
**来源**: 2026-05-14 Tech Scout 4车道搜索

---

## 评估结果汇总

| 条目 | 决策 | match/maturity/cost/risk | 核心逻辑 |
|------|------|--------------------------|---------|
| Autoresearch-trading (LLM进化策略) | **deferred** | 3/2/4/2 | 方法论有价值，纯论文无代码，StratEvo已覆盖 |
| WEEX Alpha Awakens (GMM体制分类) | **approved** | 5/2/3/2 | **直接命中周期判定痛点**，sklearn GMM可落地 |
| When2Tool (工具调用检测) | **deferred** | 4/2/4/3 | 依赖模型隐藏状态访问，当前API不可行 |
| SkillMaster (自主技能) | **deferred** | 4/2/4/3 | 纯论文级RL管道，实现成本极高 |
| Investing Algorithm Framework (v8.6.0) | **approved** | 3/5/2/1 | 成熟框架+MCP Server，pip install即可 |
| open-market-data (omd) | **deferred** | 2/2/1/3 | v0.1.0极早期，Node.js栈不一致 |
| GPT-5.5 Instant (幻觉降低) | **approved** | 3/5/1/1 | 产品级数据→信号聚合权重调整依据 |
| Warm-up Training (置信度校准) | **approved** | 3/5/2/1 | Nature方法论→llm_competence校准参考 |

## 决策分布

- **approved**: 4条 (002 GMM体制/005 量化框架MCP/007 幻觉降低/008 置信度校准)
- **deferred**: 4条 (001 进化策略/003 When2Tool/004 SkillMaster/006 omd)
- **rejected**: 0条

## 4条 approved 的落地计划

### 1. WEEX Alpha Awakens → GMM体制分类 (高优先级)
- **问题**: daily_compress.py连续2天周期阶段误判(比率数据全0+规则引擎局限)
- **解法**: sklearn.mixture.GaussianMixture 对历史市场特征聚类→6阶段映射
- **集成方式**: daily_compress周期判定新增GMM分支，与规则引擎并行输出→置信度加权融合
- **依赖**: 历史市场特征数据(已有8比率+指数数据)

### 2. Investing Algorithm Framework v8.6.0 → MCP Server (中优先级)
- **问题**: 当前无回测MCP接口
- **解法**: pip install → 复用其MCP Server架构
- **集成方式**: 参考MCP Server实现，无需全栈迁移

### 3. GPT-5.5 Instant → 信号权重校准 (低优先级)
- **动作**: 记录到 knowledge/tools/llm-confidence.md，上调LLM信号聚合权重

### 4. Warm-up Training → 置信度校准 (低优先级)
- **动作**: 提取方法论核心 → 写入 llm_competence_check() 校准逻辑

---

## 本次评估覆盖

- 20260514-001→008: 8条评估完成
- Scout周期闭合: 昨日新增→今日评估→4approved/4deferred
- 注册表状态: 无 remaining new 条目
