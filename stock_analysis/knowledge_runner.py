"""
knowledge_runner.py — 知识勘探仪统一入口

完整管线: 缺口审计 → 主动搜索 → 发现吸收 → 提案生成

用法:
  python knowledge_runner.py status          # 全链路状态
  python knowledge_runner.py search          # 执行搜索 (douyin)
  python knowledge_runner.py absorb          # 吸收发现 → 生成提案
  python knowledge_runner.py pipeline        # 一次完整管线
  python knowledge_runner.py plan            # 搜索计划
  python knowledge_runner.py seed            # 种子注入：从已有归档注入发现
"""
import json
import logging
import re
import sys
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("knowledge_runner")

STOCK_ANALYSIS = Path("D:/1989n/stock_analysis")
STOCK_DATA = Path("D:/1989n/stock_data")
KNOWLEDGE_DIR = STOCK_DATA / "knowledge"
PROSPECTOR_LOG = KNOWLEDGE_DIR / "prospector_log.json"


def cmd_status():
    """全链路状态。"""
    from knowledge_gap_registry import gap_statistics
    from knowledge_absorber import absorption_stats
    from knowledge_prospector import print_status

    print("=" * 60)
    print("知识勘探仪 — 全链路状态")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 缺口状态
    print()
    gs = gap_statistics()
    print(f"知识缺口: {gs['total']} 项 ({gs['open_count']} 开放 / {gs.get('by_status', {}).get('absorbed', 0)} 已吸收)")
    for p, c in sorted(gs.get("by_priority", {}).items()):
        print(f"  {p}: {c}")
    print()

    # 勘探状态
    print_status()
    print()

    # 吸收状态
    abs_stats = absorption_stats()
    print(f"吸收管线: 发现{abs_stats['total_findings']}条 / 已吸收{abs_stats['absorbed_findings']}条")
    print(f"提案: {abs_stats['total_proposals']} 个 ({abs_stats['proposals_by_status']})")
    print()


def cmd_search():
    """执行勘探搜索。"""
    from knowledge_prospector import run_prospecting

    # 先搜索抖音
    print("抖音勘探...")
    result_dy = run_prospecting(target_source="douyin")

    # 记录 Web/GitHub 搜索意图
    print("Web/GitHub 搜索意图已记录 (需 harness 执行)...")
    result_web = run_prospecting(target_source="web")
    result_gh = run_prospecting(target_source="github")

    print(f"抖音: {result_dy['searches_done']}搜索, {result_dy['findings']}发现")
    print(f"Web: {result_web['searches_done']}意图")
    print(f"GitHub: {result_gh['searches_done']}意图")


def cmd_absorb():
    """执行吸收。"""
    from knowledge_absorber import absorb_pending
    proposals = absorb_pending()
    print(f"生成 {len(proposals)} 个提案:")
    for p in proposals:
        print(f"  [{p['priority']}] {p['pattern']}: {p['gap_title'][:50]}")


def cmd_pipeline():
    """一次完整管线。"""
    from knowledge_gap_registry import cmd_audit
    from knowledge_prospector import run_prospecting
    from knowledge_absorber import absorb_pending
    from knowledge_tracer import run_tracing as run_upstream_tracing

    print("=" * 60)
    print("知识勘探仪 — 全流程")
    print("=" * 60)

    # Step 1: 审计缺口
    print("\n[1/5] 缺口审计")
    cmd_audit()

    # Step 2: 上游追溯 (从归档追源头)
    print("\n[2/5] 上游追溯")
    trace_result = run_upstream_tracing()
    print(f"  → {trace_result['refs_extracted']} 引用痕迹, {trace_result['findings_recorded']} 发现")

    # Step 3: 搜索 (抖音)
    print("\n[3/5] 抖音搜索")
    result_dy = run_prospecting(target_source="douyin")
    print(f"  → {result_dy['searches_done']} 搜索, {result_dy['findings']} 发现")

    # Step 4: Web/GitHub 搜索意图
    print("\n[4/5] Web/GitHub 搜索 (记录搜索意图)")
    run_prospecting(target_source="web")
    run_prospecting(target_source="github")
    print("  → 意图已记录，待 harness 执行")

    # Step 5: 吸收
    print("\n[5/5] 知识吸收")
    proposals = absorb_pending()
    print(f"  → 生成 {len(proposals)} 个提案")

    print("\n管线完成")


def cmd_seed():
    """种子注入：从已有归档/合成报告注入发现。

    把已经分析过的博主归档和合成报告中的洞察注入为"发现"，
    让吸收器能把它们变成提案。
    """
    import re

    # 1. 读取合成报告
    synthesis_file = Path("D:/1989n/stock_data/douyin/archive/synthesis_20260527.md")
    if synthesis_file.exists():
        print("注入合成报告发现...")
        content = synthesis_file.read_text(encoding="utf-8")
        _inject_synthesis(content)

    # 2. 读取各博主归档的高价值视频
    archive_dir = STOCK_DATA / "douyin" / "archive"
    if archive_dir.exists():
        for fp in sorted(archive_dir.glob("*.json")):
            if fp.name == "synthesis_20260527.md":
                continue
            nickname = fp.stem
            print(f"  扫描归档: {nickname}...")
            _inject_archive_findings(fp, nickname)

    # 3. 检查缺口清单是否已同步更新
    from knowledge_gap_registry import load_registry, save_registry
    gaps = load_registry()
    for g in gaps:
        if g.get("source", "").startswith("synthesis") or g.get("source", "").startswith("archive"):
            if g["status"] == "open":
                g["status"] = "investigating"
                g["updated_at"] = datetime.now().isoformat()
                print(f"  更新缺口: {g['gap_id']} → investigating")
    save_registry(gaps)

    print("种子注入完成")


def _inject_synthesis(content: str):
    """从合成报告提取洞察，注入为发现。"""
    sections = re.split(r'^##\s+', content, flags=re.MULTILINE)
    # 映射: 分析段落 → 缺口 ID
    section_gap_map = {
        "九天Hector": {"gap_id": "arch-multi-layer-security", "priority": "P2"},
        "九天Hector": {"gap_id": "arch-context-isolation", "priority": "P1"},
        "清华姜学长": {"gap_id": "arch-context-isolation", "priority": "P1"},
        "阿森编程日记": {"gap_id": "tool-claude-code-skills-distillation", "priority": "P2"},
    }

    for sec in sections:
        if not sec.strip():
            continue
        first_line = sec.split("\n")[0].strip()
        # 找匹配的缺口
        for keyword, target in section_gap_map.items():
            if keyword in first_line:
                gap_id = target["gap_id"]
                summary = sec[:300].replace("\n", " ").strip()
                _record_seed_finding(gap_id, "synthesis_report", f"合成报告: {first_line}", summary)
                break

    # 行动计划中的 P0/P1/P2
    action_section = ""
    for sec in sections:
        if "行动计划" in sec:
            action_section = sec
            break
    if action_section:
        for line in action_section.split("\n"):
            line = line.strip()
            if line.startswith("- ") and ("knowledge_db" in line or "expert" in line):
                _record_seed_finding(
                    "pipeline-knowledge-db-expert-connect", "synthesis_action_plan",
                    "知识库接入expert管线", line.lstrip("- ")[:200],
                )
            elif line.startswith("- ") and "上下文" in line:
                _record_seed_finding(
                    "arch-context-isolation", "synthesis_action_plan",
                    "Expert上下文隔离", line.lstrip("- ")[:200],
                )


def _inject_archive_findings(archive_fp: Path, nickname: str):
    """从博主归档中提取有章节的高价值视频注入为发现。"""
    try:
        data = json.loads(archive_fp.read_text(encoding="utf-8"))
    except Exception:
        return

    videos = data.get("videos", [])
    with_chapters = [v for v in videos if v.get("has_chapters")]

    for v in with_chapters[:10]:  # 最多10条
        desc = v.get("desc", "")[:200]
        chapter = v.get("chapter_content", "")[:200]
        title = desc[:100] if desc else "无描述"

        # 估算关联缺口
        gap_id = _guess_gap_from_text(desc + " " + chapter)

        _record_seed_finding(
            gap_id, f"archive_{nickname}", title,
            f"章节: {chapter[:200]}" if chapter else f"描述: {desc[:200]}",
        )


def _guess_gap_from_text(text: str) -> str:
    """根据文本内容猜测关联的知识缺口。"""
    text_l = text.lower()
    mapping = [
        (["agent", "上下文", "context", "prompt"], "arch-context-isolation"),
        (["缓存", "cache", "重复", "重复拉取"], "pipeline-shared-cache"),
        (["安全", "防御", "guard", "安全模型", "风控"], "arch-multi-layer-security"),
        (["记忆", "memory", "长期记忆", "持久化", "hierarchical"], "arch-memory-hierarchy"),
        (["Gbrain", "dream", "skillify"], "arch-gbrain-integration"),
        (["skill", "蒸馏", "distill", "skill 蒸馏", "skills 蒸馏"], "tool-claude-code-skills-distillation"),
        (["白名单", "校验", "validation", "whitelist", "sanitization"], "pipeline-data-whitelist"),
        (["仓位", "position", "凯利", "kelly", "风险平价"], "concept-position-sizing"),
        (["进化", "evolve", "自进化", "self-evolve", "迭代"], "tool-agent-self-evolution-pattern"),
        (["知识库", "knowledge", "检索", "RAG", "查询"], "pipeline-knowledge-db-expert-connect"),
    ]
    for keywords, gid in mapping:
        if any(kw in text_l for kw in keywords):
            return gid
    return "knowledge-creator-discovery"  # 默认


def _record_seed_finding(gap_id: str, source: str, title: str, summary: str):
    """记录一条种子发现。"""
    log = []
    if PROSPECTOR_LOG.exists():
        try:
            log = json.loads(PROSPECTOR_LOG.read_text(encoding="utf-8"))
        except Exception:
            pass

    import time
    finding = {
        "finding_id": f"seed_{gap_id}_{int(time.time())}_{len(log)}",
        "gap_id": gap_id,
        "source": source,
        "title": title[:200],
        "url": "",
        "relevance": 4,  # 种子注入默认高价值
        "summary": summary[:500],
        "discovered_at": datetime.now().isoformat(),
        "absorbed": False,
    }
    # 去重
    for existing in log:
        if existing.get("title") == finding["title"] and existing.get("gap_id") == gap_id:
            return
    log.append(finding)
    PROSPECTOR_LOG.write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def cmd_plan():
    """打印搜索计划。"""
    from knowledge_prospector import print_search_plan
    from knowledge_gap_registry import cmd_audit

    print("=" * 60)
    print("勘探计划")
    print("=" * 60)
    print()
    print("缺口概览:")
    cmd_audit()
    print()
    print_search_plan()


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = sys.argv[1:] if len(sys.argv) > 1 else ["status"]

    cmd = args[0]

    if cmd == "status":
        cmd_status()
    elif cmd == "search":
        cmd_search()
    elif cmd == "absorb":
        cmd_absorb()
    elif cmd == "pipeline":
        cmd_pipeline()
    elif cmd == "plan":
        cmd_plan()
    elif cmd == "seed":
        cmd_seed()
    elif cmd in ("trace", "upstream"):
        # 上游追溯
        dry_run = "--dry" in args
        from knowledge_tracer import run_tracing, print_trace_report, scan_archives, print_trace_refs
        print("=" * 60)
        print("上游追溯 — 从抖音归档追源头")
        print("=" * 60)
        if "--scan" in args:
            refs = scan_archives()
            print_trace_refs(refs)
        else:
            result = run_tracing(dry_run=dry_run)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            if not dry_run:
                print()
                print_trace_report()
    else:
        print("用法: python knowledge_runner.py [status|search|absorb|pipeline|plan|seed|trace]")


if __name__ == "__main__":
    main()
