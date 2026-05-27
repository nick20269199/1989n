"""
knowledge_gap_registry.py — 知识缺口清单

形式化系统知识缺口清单，驱动主动搜索。缺口=我们需要但还不知道的东西。

每个缺口定义：
  - 描述：缺什么、为什么缺、填上能做什么
  - 优先级：P0(阻塞)/P1(重要)/P2(锦上添花)
  - 状态：open/investigating/solution_found/absorbed/verified/abandoned
  - 搜索查询：自动生成多源搜索关键词
  - 系统关联：关联到哪些系统组件/模块

用法:
  python knowledge_gap_registry.py --audit     # 审计系统，发现新缺口
  python knowledge_gap_registry.py --list      # 列出所有缺口
  python knowledge_gap_registry.py --export    # 导出搜索用缺口列表
"""
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("knowledge_gap")

DATA_DIR = Path("D:/1989n/stock_data/knowledge")
REGISTRY_FILE = DATA_DIR / "gap_registry.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# ── 缺口分类域名 ──
DOMAINS = [
    "architecture",      # 系统架构
    "pipeline",          # 数据管线
    "trading",           # 交易策略/决策
    "risk",              # 风控
    "engineering",       # 工程部基础设施
    "knowledge",         # 知识管理
    "tool",              # 工具/外部框架
    "concept",           # 投资概念/理念
]

# ── 缺口感兴趣的搜索源 ──
TARGET_SOURCES = ["douyin", "github", "web", "zhihu", "paper"]


def _default_registry() -> list[dict]:
    """初始缺口清单 — 基于当前系统审计的已知缺口。"""
    return [
        # ── P0: 阻塞级 ──
        {
            "gap_id": "pipeline-knowledge-db-expert-connect",
            "domain": "pipeline",
            "title": "Knowledge DB 未接入 Expert 管线",
            "description": "expert 分析外部数据时不会自动查 knowledge_db，每次从零推理。"
                           "应让 expert 在分析前自动检索已有知识作为上下文。",
            "priority": "P0",
            "status": "open",
            "source": "synthesis_20260527",
            "related_components": ["experts/base.py", "experts/lead.py", "knowledge_db.py"],
            "search_queries": [
                "agent auto-retrieve knowledge base before analysis",
                "RAG for multi-agent pipeline",
                "knowledge base integration with expert system",
            ],
            "target_sources": ["github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        # ── P1: 重要级 ──
        {
            "gap_id": "arch-context-isolation",
            "domain": "architecture",
            "title": "Expert 上下文隔离 — 拼接大 prompt 导致知识熵增",
            "description": "5 位 expert 各自独立采集数据后拼成大 prompt 给 grader。"
                           "expert1 的数据 expert2 看不到，且总 prompt 过长烧 Token。"
                           "应引入上下文隔离：每位 expert 独立上下文，只传摘要给下游。",
            "priority": "P1",
            "status": "open",
            "source": "synthesis_20260527",
            "related_components": ["experts/lead.py", "experts/base.py", "experts/config.py"],
            "search_queries": [
                "multi-agent context isolation pattern",
                "agent prompt splitting technique",
                "reduce token usage multi-agent system",
            ],
            "target_sources": ["douyin", "github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "pipeline-shared-cache",
            "domain": "pipeline",
            "title": "Expert 间无共享缓存 — 同一数据被重复拉取",
            "description": "expert1_tech 拉到的量价数据，expert2_money 要重新拉。"
                           "应引入共享缓存层：任一 expert 已获取的数据自动对其他 expert 可用。",
            "priority": "P1",
            "status": "open",
            "source": "synthesis_20260527",
            "related_components": ["experts/lead.py", "experts/base.py", "data_source_router.py"],
            "search_queries": [
                "shared cache multi-agent data pipeline",
                "agent result cache pattern",
                "data deduplication agent system",
            ],
            "target_sources": ["github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "pipeline-data-whitelist",
            "domain": "pipeline",
            "title": "数据采集层缺白名单校验",
            "description": "当前数据采集无输入校验层。应按九天Hector五层防御模型："
                           "数据采集层→白名单通道→清洗层正则校验→分析层独立审查→决策层断路器→风控层人工兜底。",
            "priority": "P1",
            "status": "open",
            "source": "synthesis_20260527",
            "related_components": ["data_source_router.py", "stock_analysis/"],
            "search_queries": [
                "data validation whitelist pipeline",
                "defense in depth data ingestion",
                "input sanitization pipeline architecture",
            ],
            "target_sources": ["douyin", "github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "knowledge-creator-discovery",
            "domain": "knowledge",
            "title": "无主动知识发现机制 — 等人给链接而非自己搜",
            "description": "当前抖音监控只扫描已知博主。需要系统能根据知识缺口主动搜索："
                           "用需求清单(缺口)作为搜索 query，去抖音/知乎/GitHub 找有相关内容的人。",
            "priority": "P1",
            "status": "open",
            "source": "user_question_20260527",
            "related_components": ["douyin_monitor.py", "knowledge_gap_registry.py"],
            "search_queries": [
                "knowledge discovery agent system",
                "expert finder AI",
                "content discovery pipeline",
            ],
            "target_sources": ["github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        # ── P2: 增强级 ──
        {
            "gap_id": "arch-multi-layer-security",
            "domain": "architecture",
            "title": "单点安全防御 — 需扩展为多层架构",
            "description": "目前仅 -7% 硬止损 + adversarial-review 单点防御。"
                           "可扩展为九天Hector五层模型：字符串拦截→正则过滤→白名单放行→独立AI审查→人工兜底。",
            "priority": "P2",
            "status": "open",
            "source": "synthesis_20260527",
            "related_components": ["experts/expert5_risk.py", "experts/grader.py"],
            "search_queries": [
                "multi-layer AI safety architecture",
                "agent guardrails layered defense",
                "circuit breaker pattern AI system",
            ],
            "target_sources": ["douyin", "github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "arch-memory-hierarchy",
            "domain": "architecture",
            "title": "记忆系统未分层 — 单层 flat 结构",
            "description": "Hermes 四层记忆(瞬时/短期/长期/持久)可参考重构 session_tracker + knowledge_db。"
                           "当前所有 memory 在同一层级，无访问频率/时效性分层。",
            "priority": "P2",
            "status": "open",
            "source": "synthesis_20260527",
            "related_components": ["knowledge_db.py", "sel_lint.py", "session_tracker.py"],
            "search_queries": [
                "hierarchical memory system AI agent",
                "memory tiering agent architecture",
                "short term long term memory agent",
            ],
            "target_sources": ["douyin", "github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "trading-rules-not-operationalized",
            "domain": "trading",
            "title": "trading_rules.json 存在但未被 analysis 管线加载",
            "description": "trading_rules.json 中存有可川科技等交易规则，但没有任何 expert 或 grader 读取。"
                           "规则→代码的链路断裂，下一轮修改 expert5_risk 或 grader 时应补上。",
            "priority": "P2",
            "status": "open",
            "source": "memory_20260524",
            "related_components": ["experts/expert5_risk.py", "experts/grader.py"],
            "search_queries": [
                "trading rules engine architecture",
                "rule-based trading agent",
                "operationalize trading rules",
            ],
            "target_sources": ["github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "arch-gbrain-integration",
            "domain": "architecture",
            "title": "Gbrain 长期记忆可探索集成",
            "description": "九天Hector 视频中介绍了 Gbrain(YC开源)的长期记忆方案——按主题归档结构化笔记+dream周期整理+skillify自愈。"
                           "我们的 session_tracker+knowledge_db 可参考其 dream 周期和 skillify 机制。",
            "priority": "P2",
            "status": "open",
            "source": "archive_九天Hector",
            "related_components": ["knowledge_db.py", "sel_digest.py", "session_tracker.py"],
            "search_queries": [
                "Gbrain memory system",
                "dream cycle agent memory",
                "skillify agent self-healing",
            ],
            "target_sources": ["github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "tool-claude-code-skills-distillation",
            "domain": "tool",
            "title": "Claude Code Skills 蒸馏机制",
            "description": "阿森编程日记和九天Hector都介绍了Skills蒸馏——从用户与Agent的真实对话自动识别并生成结构化skill。"
                           "可参考实现：记录有效交互模式→自动蒸馏为可复用skill→验证准确率。",
            "priority": "P2",
            "status": "open",
            "source": "archive_阿森编程日记",
            "related_components": ["skills/", ".claude/skills/"],
            "search_queries": [
                "Claude Code skills distillation",
                "agent interaction pattern extraction",
                "skill auto-generation AI agent",
            ],
            "target_sources": ["douyin", "github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "concept-position-sizing",
            "domain": "trading",
            "title": "缺乏系统化的仓位管理模型",
            "description": "当前没有形式化的仓位管理模型——开多少仓位凭感觉或固定股数。"
                           "需要基于凯利公式/风险平价/波动率调整的系统化仓位计算。",
            "priority": "P2",
            "status": "open",
            "source": "system_audit",
            "related_components": ["experts/expert5_risk.py", "experts/lead.py"],
            "search_queries": [
                "Kelly criterion position sizing A shares",
                "risk parity position management",
                "volatility adjusted position sizing",
            ],
            "target_sources": ["web", "zhihu"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
        {
            "gap_id": "tool-agent-self-evolution-pattern",
            "domain": "tool",
            "title": "Agent 自进化模式 — 从九天Hector Skills自进化工程",
            "description": "九天Hector 视频展示了Agent自进化：给定初始skill+一组测试任务，Agent自行迭代修正skill直到达标。"
                           "可参考应用到我们的SEL循环：让Agent在完成知识注入后自测理解准确率，不达标则继续迭代。",
            "priority": "P2",
            "status": "open",
            "source": "archive_九天Hector",
            "related_components": ["sel_evolve_op.py", "sel_evolve_read.py", "sel_lint.py"],
            "search_queries": [
                "agent self-evolution pattern",
                "self-improving AI agent loop",
                "iterative skill refinement agent",
            ],
            "target_sources": ["douyin", "github", "web"],
            "absorbed_at": None,
            "absorbed_as": None,
        },
    ]


def load_registry() -> list[dict]:
    """加载缺口清单。不存在则用默认初始清单。"""
    if REGISTRY_FILE.exists():
        try:
            return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("缺口文件损坏，重置: %s", e)
    gaps = _default_registry()
    save_registry(gaps)
    return gaps


def save_registry(gaps: list[dict]):
    """保存缺口清单。"""
    REGISTRY_FILE.write_text(
        json.dumps(gaps, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_gap(gap_id: str) -> Optional[dict]:
    """按 ID 获取单个缺口。"""
    gaps = load_registry()
    for g in gaps:
        if g["gap_id"] == gap_id:
            return g
    return None


def update_gap(gap_id: str, updates: dict) -> bool:
    """更新缺口字段。"""
    gaps = load_registry()
    for g in gaps:
        if g["gap_id"] == gap_id:
            g.update(updates)
            g["updated_at"] = datetime.now().isoformat()
            save_registry(gaps)
            return True
    logger.warning("缺口不存在: %s", gap_id)
    return False


def add_gap(new_gap: dict) -> bool:
    """添加新缺口。"""
    gaps = load_registry()
    if any(g["gap_id"] == new_gap.get("gap_id") for g in gaps):
        logger.warning("缺口已存在: %s", new_gap.get("gap_id"))
        return False
    new_gap["status"] = new_gap.get("status", "open")
    new_gap["created_at"] = datetime.now().isoformat()
    gaps.append(new_gap)
    save_registry(gaps)
    return True


def list_gaps(domain: str = None, priority: str = None, status: str = None) -> list[dict]:
    """按条件筛选缺口。"""
    gaps = load_registry()
    if domain:
        gaps = [g for g in gaps if g.get("domain") == domain]
    if priority:
        gaps = [g for g in gaps if g.get("priority") == priority]
    if status:
        gaps = [g for g in gaps if g.get("status") == status]
    return gaps


def gaps_for_search(target_source: str = None) -> list[dict]:
    """导出适合搜索的缺口列表 — 只含 open/investigating 状态。"""
    gaps = load_registry()
    active = [g for g in gaps if g.get("status") in ("open", "investigating")]
    if target_source:
        active = [g for g in active if target_source in g.get("target_sources", [])]
    return active


def gap_statistics() -> dict:
    """缺口统计。"""
    gaps = load_registry()
    by_priority = {}
    by_domain = {}
    by_status = {}
    for g in gaps:
        p = g.get("priority", "?")
        by_priority[p] = by_priority.get(p, 0) + 1
        d = g.get("domain", "?")
        by_domain[d] = by_domain.get(d, 0) + 1
        s = g.get("status", "?")
        by_status[s] = by_status.get(s, 0) + 1
    return {
        "total": len(gaps),
        "by_priority": by_priority,
        "by_domain": by_domain,
        "by_status": by_status,
        "open_count": by_status.get("open", 0),
        "absorbed_count": by_status.get("absorbed", 0),
    }


# ── CLI ──


def cmd_list():
    """列出所有缺口。"""
    gaps = load_registry()
    print(f"知识缺口清单 ({len(gaps)} 项):")
    print("=" * 80)
    for g in sorted(gaps, key=lambda x: (x.get("priority", "Z"), x.get("gap_id", ""))):
        status_icon = {
            "open": "○", "investigating": "◎", "solution_found": "◉",
            "absorbed": "●", "verified": "✓", "abandoned": "✗",
        }.get(g.get("status", ""), "?")
        print(f"  {status_icon} [{g.get('priority','?')}] {g['title']}")
        print(f"      ID={g['gap_id']}, 域={g.get('domain','?')}, 源={g.get('source','?')}")
        if g.get("absorbed_as"):
            print(f"      → 已吸收: {g['absorbed_as']}")
        print()
    stats = gap_statistics()
    print(f"统计: {stats['open_count']}开放 / {stats['absorbed_count']}已吸收 / {stats['total']}总计")


def cmd_audit():
    """审计系统，报告当前缺口状态。"""
    stats = gap_statistics()
    gaps = load_registry()

    print("系统知识审计报告")
    print("=" * 60)
    print(f"总缺口: {stats['total']}")
    print(f"  开放中: {stats['open_count']}")
    print(f"  调研中: {stats['by_status'].get('investigating', 0)}")
    print(f"  已吸收: {stats['absorbed_count']}")
    print(f"  已验证: {stats['by_status'].get('verified', 0)}")
    print(f"  已废弃: {stats['by_status'].get('abandoned', 0)}")
    print()
    print("按优先级:")
    for p, c in sorted(stats['by_priority'].items()):
        print(f"  {p}: {c}项")
    print()
    print("按域名:")
    for d, c in sorted(stats['by_domain'].items()):
        print(f"  {d}: {c}项")
    print()
    print("未吸收缺口:")
    for g in gaps:
        if g.get("status") in ("open", "investigating", "solution_found"):
            qs = g.get("search_queries", [])
            print(f"  [{g['priority']}] {g['title']}")
            if qs:
                print(f"    搜索: {qs[0]}")
    print()

    return stats


def cmd_export():
    """导出为搜索就绪格式。"""
    gaps = gaps_for_search()
    export = []
    for g in gaps:
        export.append({
            "gap_id": g["gap_id"],
            "title": g["title"],
            "priority": g["priority"],
            "queries": g.get("search_queries", [])[:3],
            "target_sources": g.get("target_sources", []),
        })
    print(json.dumps(export, ensure_ascii=False, indent=2))
    return export


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if not args or args[0] in ("--list", "-l"):
        cmd_list()
    elif args[0] in ("--audit", "-a"):
        cmd_audit()
    elif args[0] in ("--export", "-e"):
        cmd_export()
    elif args[0] == "--add":
        # --add gap_id title domain priority "description"
        if len(args) >= 6:
            add_gap({
                "gap_id": args[1],
                "title": args[2],
                "domain": args[3],
                "priority": args[4],
                "description": args[5],
                "source": "manual",
                "related_components": [],
                "search_queries": [],
                "target_sources": ["web"],
                "absorbed_at": None,
                "absorbed_as": None,
                "created_at": datetime.now().isoformat(),
            })
            print(f"已添加缺口: {args[1]}")
        else:
            print("用法: --add <gap_id> <title> <domain> <priority> <description>")
    else:
        print("用法: python knowledge_gap_registry.py [--list|--audit|--export|--add ...]")


if __name__ == "__main__":
    main()
