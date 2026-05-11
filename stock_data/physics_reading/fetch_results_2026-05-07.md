# 抓取结果 — 2026-05-07

## 1. Karpathy llm-wiki.md 原版 Gist

**来源**: `gist.github.com/karpathy/442a6bf555914893e9891c11519de94f`
**Stars**: 5000+

**三层架构**:
```
raw/     → 原始材料（只读不可变）
wiki/    → LLM生成的结构化知识  
schema/  → 规则约束文件（CLAUDE.md同类）
```

**两个导航文件**: `index.md`（概念索引）+ `log.md`（操作日志）
**三个操作**: Ingest（摄入原始材料→wiki化）, Query（查询wiki）, Lint（每月检查wiki与schema一致性）
**核心理念**: 编译器模型（一次性编译raw→wiki）vs 解释器模型（每次查询时动态检索raw）

**与我们的MEMORY.md对比**:
- MEMORY.md已有三层结构的雏形（raw/ → knowledge/ → memory索引）
- 缺失: Lint机制（定期检查知识一致性）、log.md操作日志、Ingest的批处理脚本

## 2. Boris Cherny Sequoia 2026 访谈全文要点

**来源**: YouTube `watch?v=SlGRN8jh2RI`（Sequoia Capital 2026.4访谈）

**工作方式细节**:
- 2025年10月至今，100%代码由AI生成，零手写
- 每天10-30个PR，最高纪录150个/天（大部分在iPhone上完成）
- 同时运行5个终端agent + 5-10个浏览器agent
- 用StarCraft比喻——管理自治单元，不写语法

**/loop系统详解**:
- 几十个loop同时跑: babysit PRs、auto-fix CI、auto-rebase
- 每30分钟爬取Twitter反馈并聚类用户情绪
- 晚上跑上千个agents做深度后台工作
- Routines=服务端loop——关电脑也继续

**CLAUDE.md哲学**:
- 每次出错→加入CLAUDE.md→永不重复
- 把代码库变成自我进化的有机体

**关键预言**:
- Claude Code一年内可能缩到100行（模型越来越不需要编排水管）
- 工程师→Builder: 定义目标、判断输出、编排agent
- 好会计软件将由好会计（而非好工程师）构建——领域知识是新护城河
- 10倍更多颠覆性startup

**Anthropic内部**: Claudes在Slack上互相通信——agents之间协调解决未知问题

## 3. Graphify 最新版本/PyPI状态

**包名**: `graphifyy`（注意两个y）
**PyPI**: `pypi.org/project/graphifyy/`
**最新版本**: v0.2.0

**v0.2.0 新功能（7项）**:
- 理由节点（rationale nodes）— 记录"为什么连接"
- 置信度评分 — 边有权重
- 语义相似度边 — 自动检测概念关联
- 超边（hyperedges）— 多节点同时连接
- post-checkout git hooks — 切换分支自动更新图
- PreToolUse hooks — 工具调用前自动记录
- 可选Obsidian导出

**我们当前状态**: 已安装skill，需确认版本并考虑升级

## 4. GitNexus 试用分析

**GitHub**: `github.com/abhigyanpatwari/gitnexus`
**Stars**: 33K+
**安装**: `npx gitnexus analyze`（单命令索引）
**MCP工具**: 7个（代码搜索、依赖分析、变更影响评估等）
**Web UI**: `gitnexus.vercel.app`

**核心能力**:
- 零配置代码库索引
- 自然语言查询代码库
- MCP协议集成（与Claude Code原生兼容）
- 变更影响分析

**试用建议**: 先在stock_analysis项目上跑`npx gitnexus analyze`（只读），评估索引质量和查询效果后再决定是否安装MCP

---

## 交叉分析与行动建议

| 来源 | 我们已有的 | 可改进的 |
|------|-----------|---------|
| Karpathy llm-wiki | MEMORY.md三层结构 | 加Lint机制、log.md、批处理Ingest |
| Cherny访谈 | cron定时任务已有 | 加auto-fix CI loop、Twitter情绪监控 |
| Graphify v0.2.0 | 已安装skill | 升级到0.2.0，用置信度评分+超边 |
| GitNexus | 无 | 在stock_analysis上试用只读分析 |
