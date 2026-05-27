"""
knowledge_absorber.py — 知识自动吸收器

从勘探发现→可执行变更提案。关闭"发现→吸收"闭环。

工作流:
  1. 读 prospector_log.json，找未吸收的高价值发现
  2. 对每条发现，根据缺口类型映射到系统组件
  3. 生成结构化变更提案 (什么/为什么/怎么改)
  4. 写入 proposals/ 目录，标记已吸收
  5. 更新缺口清单状态

用法:
  python knowledge_absorber.py --list          # 列出待吸收发现
  python knowledge_absorber.py --proposals     # 列出已生成的提案
  python knowledge_absorber.py --absorb        # 自动吸收 (生成提案)
  python knowledge_absorber.py --execute <id>  # 执行某个提案 (dry-run)
"""
import json
import logging
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("knowledge_absorber")

DATA_DIR = Path("D:/1989n/stock_data/knowledge")
GAP_REGISTRY_FILE = DATA_DIR / "gap_registry.json"
PROSPECTOR_LOG = DATA_DIR / "prospector_log.json"
PROPOSALS_DIR = DATA_DIR / "proposals"

PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)

# ── 系统组件映射：缺口 → 受影响的文件/模块 ──
# 每个缺口映射到: 需要改的文件, 需要加的测试, 参考资源
COMPONENT_MAP = {
    "pipeline-knowledge-db-expert-connect": {
        "target_files": [
            "stock_analysis/experts/base.py",       # expert 基类 — 加 knowledge_query 方法
            "stock_analysis/experts/lead.py",       # 编排器 — 加 knowledge_context 注入
        ],
        "pattern": "inject_knowledge",
        "test_files": ["stock_analysis/tests/test_knowledge_db.py"],
    },
    "arch-context-isolation": {
        "target_files": [
            "stock_analysis/experts/lead.py",       # 拆大 prompt 为独立上下文
            "stock_analysis/experts/config.py",     # 各 expert 独立配置
        ],
        "pattern": "isolated_context",
        "test_files": ["stock_analysis/tests/test_grader.py"],
    },
    "pipeline-shared-cache": {
        "target_files": [
            "stock_analysis/experts/lead.py",       # 加 data_cache 模块
            "stock_analysis/data_source_router.py",  # 缓存集成
        ],
        "pattern": "shared_cache",
        "test_files": [],
    },
    "pipeline-data-whitelist": {
        "target_files": [
            "stock_analysis/data_source_router.py",  # 加白名单校验层
        ],
        "pattern": "data_whitelist",
        "test_files": ["stock_analysis/tests/test_data_quality_gate.py"],
    },
    "knowledge-creator-discovery": {
        "target_files": [
            "stock_analysis/douyin_monitor.py",     # 改造为按缺口搜索
            "stock_analysis/knowledge_prospector.py",
        ],
        "pattern": "creator_discovery",
        "test_files": [],
    },
    "arch-multi-layer-security": {
        "target_files": [
            "stock_analysis/experts/expert5_risk.py",  # 多层防御
            "stock_analysis/experts/grader.py",         # 审查层
        ],
        "pattern": "layered_defense",
        "test_files": ["stock_analysis/tests/test_grader.py"],
    },
    "arch-memory-hierarchy": {
        "target_files": [
            "stock_analysis/knowledge_db.py",           # 记忆分层
            "stock_analysis/sel_lint.py",
        ],
        "pattern": "memory_tiering",
        "test_files": [],
    },
    "trading-rules-not-operationalized": {
        "target_files": [
            "stock_analysis/experts/expert5_risk.py",  # 加载 trading_rules
            "stock_analysis/experts/grader.py",
        ],
        "pattern": "load_trading_rules",
        "test_files": [],
    },
    "arch-gbrain-integration": {
        "target_files": [
            "stock_analysis/knowledge_db.py",
            "stock_analysis/session_tracker.py",  # 如果存在
        ],
        "pattern": "dream_cycle",
        "test_files": [],
    },
    "tool-claude-code-skills-distillation": {
        "target_files": [
            # Skills 蒸馏在 .claude/skills/ 层面
        ],
        "pattern": "skills_distill",
        "test_files": [],
    },
    "concept-position-sizing": {
        "target_files": [
            "stock_analysis/experts/expert5_risk.py",  # 仓位模型
        ],
        "pattern": "position_sizing",
        "test_files": [],
    },
    "tool-agent-self-evolution-pattern": {
        "target_files": [
            "stock_analysis/sel_evolve_op.py",
            "stock_analysis/sel_evolve_read.py",
        ],
        "pattern": "self_evolve",
        "test_files": [],
    },
}


# ── 加载数据 ──


def _load_prospector_log() -> list[dict]:
    if PROSPECTOR_LOG.exists():
        try:
            return json.loads(PROSPECTOR_LOG.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _load_gaps() -> list[dict]:
    if GAP_REGISTRY_FILE.exists():
        try:
            return json.loads(GAP_REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_gaps(gaps: list[dict]):
    GAP_REGISTRY_FILE.write_text(
        json.dumps(gaps, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _save_prospector_log(log: list[dict]):
    PROSPECTOR_LOG.write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# ── 提案生成 ──


def _generate_proposal(finding: dict, gap: dict) -> Optional[dict]:
    """为一条发现生成变更提案。"""
    gap_id = finding.get("gap_id", "")
    component_info = COMPONENT_MAP.get(gap_id)
    if not component_info:
        # 未知缺口类型，生成通用提案
        component_info = {
            "target_files": [],
            "pattern": "general",
            "test_files": [],
        }

    proposal_id = f"prop_{gap_id}_{int(datetime.now().timestamp())}"

    # 系统组件映射
    source_desc = {
        "douyin": "抖音视频内容",
        "douyin_search": "抖音搜索结果",
        "web_intent": "Web搜索(待人工执行)",
        "github_intent": "GitHub搜索(待人工执行)",
        "web": "网页内容",
        "github": "GitHub仓库",
    }.get(finding.get("source", ""), "外部来源")

    # 生成提案详情的结构框架
    pattern = component_info["pattern"]
    implementation_hint = _get_pattern_hint(pattern, gap)

    proposal = {
        "proposal_id": proposal_id,
        "gap_id": gap_id,
        "gap_title": gap.get("title", "?") if gap else "?",
        "priority": gap.get("priority", "P2") if gap else "P2",
        "source": source_desc,
        "source_title": finding.get("title", ""),
        "source_url": finding.get("url", ""),
        "relevance": finding.get("relevance", 3),
        "summary": finding.get("summary", "")[:500],
        "pattern": pattern,
        "implied_changes": component_info["target_files"],
        "implementation_hint": implementation_hint,
        "test_files": component_info["test_files"],
        "status": "proposed",
        "created_at": datetime.now().isoformat(),
        "executed_at": None,
        "execution_result": None,
    }
    return proposal


def _get_pattern_hint(pattern: str, gap: dict) -> str:
    """为变更模式提供实施提示。"""
    hints = {
        "inject_knowledge": (
            "在 expert base.py 的 analyze() 中增加 knowledge_query(gap_context) 调用，"
            "将 knowledge_db.search_knowledge() 结果注入 prompt 上下文。"
            "lead.py 中在调度各 expert 前先收集 knowledge_context 并传参。"
        ),
        "isolated_context": (
            "将 lead.py 中的统一 prompt 拆分为每个 expert 独立的 context builder。"
            "config.py 中为每位 expert 配置独立的 max_tokens/temperature。"
            "lead.py 汇总时只传各 expert 的摘要而非全量输出。"
        ),
        "shared_cache": (
            "在 lead.py 中引入 SharedDataCache 类，expert 拉取数据前先查 cache。"
            "cache key = f\"{data_type}_{stock_code}\"，TTL 按数据类型配置。"
        ),
        "data_whitelist": (
            "在 data_source_router.py 的采集入口加白名单校验层："
            "允许的字段列表 + 类型校验 + 范围校验。非法数据拒绝写入。"
        ),
        "creator_discovery": (
            "将 douyin_monitor.py 的扫描来源从固定 JSON 改为："
            "读取 gap_registry 的 search_queries → 抖音搜索 → 发现新博主 → 自动加入监控列表。"
        ),
        "layered_defense": (
            "expert5_risk.py 中增加：层①数据校验 → 层②规则审查 → 层③AI独立审查 → 层④断路器。"
            "断路器条件：连续 N 次亏损 / 单日亏损超阈值 / 风控信号矛盾。"
        ),
        "memory_tiering": (
            "knowledge_db.py 中增加 tier 字段："
            "L1=会话记忆(瞬时)，L2=日频记忆(短期)，L3=知识库(长期)，L4=规则(持久)。"
            "按访问频率自动升降级。"
        ),
        "load_trading_rules": (
            "expert5_risk.py 或 grader.py 启动时加载 trading_rules.json。"
            "对每只股票检查是否有匹配规则，在评分中增加 rule_check 维度。"
        ),
        "dream_cycle": (
            "参考 Gbrain dream 周期：夜间整理阶段对当日所有交互做实体提取→主题关联→冲突仲裁→过期标记。"
            "在 sel_digest.py 或定时任务中实现。"
        ),
        "skills_distill": (
            "分析成功交互模式 → 提取可复用 pattern → 自动生成 Claude Code skill 文档。"
            "验证：给定测试任务，检查 skill 加载后准确率是否提升。"
        ),
        "position_sizing": (
            "expert5_risk.py 中增加 Kelly 公式 / 风险平价仓位计算。"
            "输入：胜率/赔率/波动率/最大回撤容忍度。输出：建议仓位比例。"
        ),
        "self_evolve": (
            "sel_evolve_op.py 中增加自测循环：知识注入后 → 用测试任务验证 → 不达标继续迭代。"
            "与 prospector 联动：高价值发现自动触发一次改进循环。"
        ),
    }
    return hints.get(pattern, "待分析具体实施方案")


# ── 核心吸收流程 ──


def absorb_pending(max_findings: int = 10, dry_run: bool = False) -> list[dict]:
    """吸收待处理的发现，生成提案。

    Args:
        max_findings: 最多处理的发现数
        dry_run: 只打印，不写入

    Returns:
        生成的提案列表
    """
    log = _load_prospector_log()
    gaps = _load_gaps()
    gaps_by_id = {g["gap_id"]: g for g in gaps}

    # 找未吸收的高价值发现
    pending = [
        f for f in log
        if not f.get("absorbed") and f.get("relevance", 0) >= 4
    ]
    # 按关联度排序
    pending.sort(key=lambda x: x.get("relevance", 0), reverse=True)
    pending = pending[:max_findings]

    if not pending:
        logger.info("无待吸收的高价值发现")
        return []

    logger.info("待吸收发现: %d 条", len(pending))
    proposals = []

    for finding in pending:
        gap_id = finding.get("gap_id", "")
        gap = gaps_by_id.get(gap_id)

        logger.info("  处理: %s (rel=%d)", finding.get("title", "?")[:60], finding.get("relevance", 0))

        proposal = _generate_proposal(finding, gap)
        if not proposal:
            continue

        proposals.append(proposal)
        logger.info("    生成提案: %s [%s]", proposal["proposal_id"], proposal["pattern"])

        if not dry_run:
            # 标记发现已吸收
            finding["absorbed"] = True
            finding["absorbed_at"] = datetime.now().isoformat()
            finding["proposal_id"] = proposal["proposal_id"]

            # 保存提案
            proposal_file = PROPOSALS_DIR / f"{proposal['proposal_id']}.json"
            proposal_file.write_text(
                json.dumps(proposal, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 写入 SEL evolve pending_ingest (KAE→SEL 桥)
            _bridge_to_evolve(finding, proposal)

            # 更新缺口状态
            if gap:
                high_value_count = sum(
                    1 for f in log if f.get("gap_id") == gap_id and f.get("absorbed")
                )
                if high_value_count >= 2 and gap.get("status") != "solution_found":
                    gap["status"] = "solution_found"
                    gap["updated_at"] = datetime.now().isoformat()
                    gap["absorbed_at"] = datetime.now().isoformat()
                    gap["absorbed_as"] = f"提案: {proposal['proposal_id']}"

    if not dry_run:
        _save_prospector_log(log)
        _save_gaps(gaps)
        logger.info("吸收完成: 生成 %d 个提案", len(proposals))
    else:
        logger.info("Dry run: 将生成 %d 个提案", len(proposals))

    return proposals


# ── KAE → SEL 桥 — 高价值发现自动注入进化管线 ──


def _bridge_to_evolve(finding: dict, proposal: dict):
    """将高价值发现写入 SEL evolve 的 pending_ingest.json，启动知识注入。

    SEL Read→Op 管线在下个调度周期自动读取此文件并注入 knowledge/。
    这样 KAE 的发现不仅生成执行提案，也自动进入知识库。
    """
    PENDING_FILE = Path("D:/1989n/stock_data/learning/pending_ingest.json")
    try:
        title = f"[KAE] {finding.get('title', '?')[:80]}"
        tags = [proposal.get("pattern", "kae"), finding.get("source", "prospector")]
        gap_id = finding.get("gap_id", "")
        if gap_id:
            tags.append(gap_id)

        entry = {
            "title": title,
            "source": "prospector",
            "tags": tags,
            "file_path": "",
            "_proposal_id": proposal.get("proposal_id", ""),
            "_gap_id": gap_id,
            "_summary": finding.get("summary", "")[:300],
        }

        pending = json.loads(PENDING_FILE.read_text(encoding="utf-8")) if PENDING_FILE.exists() else []
        pending.append(entry)
        PENDING_FILE.write_text(json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("  KAE→SEL 桥: 写入 pending_ingest ✓")
    except Exception as e:
        logger.warning("  KAE→SEL 桥写入失败: %s", e)


# ── 提案管理 ──


def list_proposals(status: str = None) -> list[dict]:
    """列出所有提案。"""
    proposals = []
    for fp in sorted(PROPOSALS_DIR.glob("*.json")):
        try:
            p = json.loads(fp.read_text(encoding="utf-8"))
            if status and p.get("status") != status:
                continue
            proposals.append(p)
        except Exception:
            continue
    return proposals


def print_proposals(status: str = None):
    """打印提案清单。"""
    proposals = list_proposals(status)
    if not proposals:
        print("暂无提案" if not status else f"暂无 {status} 状态的提案")
        return

    print(f"提案清单 ({len(proposals)} 项):")
    print("=" * 80)
    for p in sorted(proposals, key=lambda x: (x.get("priority", "Z"), x.get("proposal_id", ""))):
        status_icon = {
            "proposed": "○", "approved": "◉", "implemented": "●",
            "verified": "✓", "rejected": "✗",
        }.get(p.get("status", ""), "?")
        print(f"  {status_icon} [{p['priority']}] {p['gap_title']}")
        print(f"      ID: {p['proposal_id']}")
        print(f"      模式: {p['pattern']} → 涉及 {len(p.get('implied_changes', []))} 个文件")
        print(f"      来自: {p.get('source', '?')}: {p.get('source_title', '')[:60]}")
        print()

    by_status = {}
    for p in proposals:
        s = p.get("status", "?")
        by_status[s] = by_status.get(s, 0) + 1
    print(f"统计: {', '.join(f'{k}={v}' for k, v in by_status.items())}")


def print_pending():
    """打印待吸收的发现。"""
    log = _load_prospector_log()
    gaps = _load_gaps()
    gaps_by_id = {g["gap_id"]: g for g in gaps}

    pending = [
        f for f in log
        if not f.get("absorbed") and f.get("relevance", 0) >= 4
    ]
    pending.sort(key=lambda x: x.get("relevance", 0), reverse=True)

    if not pending:
        print("无待吸收的高价值发现")
        return

    print(f"待吸收发现 ({len(pending)} 条):")
    print("=" * 80)
    for f in pending:
        gap = gaps_by_id.get(f.get("gap_id", ""), {})
        print(f"  [{f.get('relevance', '?')}★] {f.get('title', '?')[:70]}")
        print(f"      源: {f.get('source', '?')} | 缺口: {gap.get('title', f.get('gap_id', '?'))[:50]}")
        print(f"      发现于: {f.get('discovered_at', '?')}")
        print()


# ── 提案执行跟踪 ──


def update_proposal_status(proposal_id: str, status: str, result: str = ""):
    """更新提案状态。"""
    fp = PROPOSALS_DIR / f"{proposal_id}.json"
    if not fp.exists():
        logger.error("提案不存在: %s", proposal_id)
        return False
    try:
        proposal = json.loads(fp.read_text(encoding="utf-8"))
        proposal["status"] = status
        if status in ("implemented", "verified"):
            proposal["executed_at"] = datetime.now().isoformat()
        if result:
            proposal["execution_result"] = result
        fp.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
    except Exception as e:
        logger.error("更新提案失败: %s", e)
        return False


# ── 状态摘要 ──


def absorption_stats() -> dict:
    """吸收统计。"""
    log = _load_prospector_log()
    gaps = _load_gaps()
    proposals = list_proposals()

    total_findings = len(log)
    absorbed_findings = sum(1 for f in log if f.get("absorbed"))
    high_value = sum(1 for f in log if f.get("relevance", 0) >= 4)

    open_gaps = sum(1 for g in gaps if g.get("status") in ("open", "investigating"))
    solved_gaps = sum(1 for g in gaps if g.get("status") in ("solution_found", "absorbed"))

    by_proposal_status = {}
    for p in proposals:
        s = p.get("status", "?")
        by_proposal_status[s] = by_proposal_status.get(s, 0) + 1

    return {
        "total_findings": total_findings,
        "absorbed_findings": absorbed_findings,
        "high_value_pending": high_value - absorbed_findings,
        "open_gaps": open_gaps,
        "solved_gaps": solved_gaps,
        "total_proposals": len(proposals),
        "proposals_by_status": by_proposal_status,
    }


# ── CLI ──


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if not args or args[0] in ("--list", "-l"):
        print_pending()
    elif args[0] in ("--proposals", "-p"):
        status = args[1] if len(args) > 1 else None
        print_proposals(status)
    elif args[0] in ("--absorb", "-a"):
        dry_run = "--dry" in args
        result = absorb_pending(dry_run=dry_run)
        print(f"生成 {len(result)} 个提案")
        for p in result:
            print(f"  [{p['priority']}] {p['proposal_id']}: {p['pattern']}")
    elif args[0] in ("--status", "-s"):
        stats = absorption_stats()
        print("知识吸收状态:")
        print(f"  发现总数: {stats['total_findings']}")
        print(f"  已吸收: {stats['absorbed_findings']}")
        print(f"  高价值待处理: {stats['high_value_pending']}")
        print(f"  开放缺口: {stats['open_gaps']}")
        print(f"  已解决缺口: {stats['solved_gaps']}")
        print(f"  提案总数: {stats['total_proposals']}")
        if stats['proposals_by_status']:
            print(f"  提案状态: {stats['proposals_by_status']}")
    elif args[0] in ("--update", "-u") and len(args) >= 3:
        proposal_id = args[1]
        status = args[2]
        result_text = " ".join(args[3:]) if len(args) > 3 else ""
        if update_proposal_status(proposal_id, status, result_text):
            print(f"提案 {proposal_id} → {status}")
        else:
            print(f"更新失败: {proposal_id}")
    else:
        print("用法:")
        print("  python knowledge_absorber.py --list          # 待吸收发现")
        print("  python knowledge_absorber.py --absorb        # 吸收[--dry 预览]")
        print("  python knowledge_absorber.py --proposals     # 已生成提案")
        print("  python knowledge_absorber.py --status        # 状态概览")
        print("  python knowledge_absorber.py --update <id> <status> [result]")


if __name__ == "__main__":
    main()
