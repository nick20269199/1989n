"""
knowledge_runner.py — 知识勘探仪统一入口

完整管线: 缺口审计 → 主动搜索 → 发现吸收 → 提案生成

用法:
  python knowledge_runner.py status          # 全链路状态
  python knowledge_runner.py search          # 执行搜索 (douyin)
  python knowledge_runner.py absorb          # 吸收发现 → 生成提案
  python knowledge_runner.py pipeline              # 一次完整管线
  python knowledge_runner.py pipeline --incremental # 增量模式（仅处理新缺口）
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
INCREMENTAL_STATE_FILE = KNOWLEDGE_DIR / "incremental_state.json"
DAILY_DIGEST_FILE = STOCK_DATA / "status" / "daily_digest.md"


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


def cmd_absorb(auto_execute: bool = False):
    """执行吸收。auto_execute 时触发 SEL 执行链。"""
    from knowledge_absorber import absorb_pending
    proposals = absorb_pending()
    print(f"生成 {len(proposals)} 个提案:")
    for p in proposals:
        print(f"  [{p['priority']}] {p['pattern']}: {p['gap_title'][:50]}")

    if auto_execute and proposals:
        print("\n--auto-execute: 触发 SEL 执行链")
        try:
            # Step 1: Agent 模式扫描
            import sel_digest
            patterns = sel_digest.scan_agent_patterns()
            anom_count = sum(1 for s in patterns.values() if s.get("distill_suggestion"))
            print(f"  Agent 模式: {len(patterns)} 个有足够样本, {anom_count} 个含蒸馏建议")

            # Step 2: 自动执行 planned 提案
            prop_dir = Path("D:/1989n/stock_data/knowledge/proposals")
            executed = 0
            for pf in sorted(prop_dir.glob("*.json")):
                try:
                    prop = json.loads(pf.read_text(encoding="utf-8"))
                    if prop.get("status") == "planned" and prop.get("gap_id"):
                        prop["status"] = "executed"
                        prop["executed_at"] = datetime.now().isoformat()
                        prop["execution_result"] = "auto: chained into SEL pipeline"
                        pf.write_text(json.dumps(prop, ensure_ascii=False, indent=2), encoding="utf-8")
                        executed += 1
                except Exception:
                    continue
            print(f"  已执行 {executed} 个待执行提案")
        except Exception as e:
            print(f"  auto-execute 异常: {e}")


def cmd_pipeline(incremental: bool = False):
    """一次完整管线。"""
    from knowledge_gap_registry import cmd_audit, load_registry
    from knowledge_prospector import run_prospecting
    from knowledge_absorber import absorb_pending
    from knowledge_tracer import run_tracing as run_upstream_tracing

    print("=" * 60)
    print("知识勘探仪 — 全流程" + (" [增量模式]" if incremental else ""))
    print("=" * 60)

    # 增量模式：读取上次运行时间
    incremental_since = None
    if incremental:
        state = {}
        if INCREMENTAL_STATE_FILE.exists():
            try:
                state = json.loads(INCREMENTAL_STATE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        incremental_since = state.get("last_run_at")
        if incremental_since:
            print(f"\n  增量模式: 仅处理 {incremental_since[:10]} 之后创建的缺口")
        else:
            print("\n  增量模式: 无历史记录，处理全部开放缺口")

    # Step 1: 审计缺口
    print("\n[1/6] 缺口审计")
    cmd_audit()

    # 开放探索模式：缺口归零时从博主引用中探索新方向
    gap_registry = load_registry()
    open_gaps = [g for g in gap_registry if g.get("status") == "open"]
    if not open_gaps and not incremental:
        print("\n[探索模式] 缺口归零，启动开放探索")
        _open_exploration()
    else:
        print(f"\n  → {len(open_gaps)} 个开放缺口{' (增量模式跳过开放探索)' if incremental else ''}")

    # Step 2: 上游追溯 (从归档追源头)
    print("\n[2/6] 上游追溯")
    trace_result = run_upstream_tracing()
    print(f"  → {trace_result['refs_extracted']} 引用痕迹, {trace_result['findings_recorded']} 发现")

    # Step 3: 搜索 — 注入 incremental_since
    print("\n[3/6] 抖音搜索")
    result_dy = run_prospecting(target_source="douyin", incremental_since=incremental_since)
    print(f"  → {result_dy['searches_done']} 搜索, {result_dy['findings']} 发现")

    print("\n[4/6] Web/GitHub 搜索")
    result_web = run_prospecting(target_source="web", incremental_since=incremental_since)
    result_gh = run_prospecting(target_source="github", incremental_since=incremental_since)
    print(f"  → Web {result_web['findings']} / GitHub {result_gh['findings']} 发现")

    # Step 5: 吸收
    print("\n[5/6] 知识吸收")
    proposals = absorb_pending()
    print(f"  → 生成 {len(proposals)} 个提案")

    # 生成管线摘要 → 写入 daily_digest.md / kae_discoveries.md
    _write_pipeline_summary(result_dy, result_web, result_gh, proposals)

    # 保存增量状态
    now_ts = datetime.now().isoformat()
    INCREMENTAL_STATE_FILE.write_text(
        json.dumps({"last_run_at": now_ts, "mode": "incremental" if incremental else "full"},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n  → 增量状态已保存: {now_ts[:19]}")

    from feishu_sender import send_kae_discovery
    send_kae_discovery()

    # Step 6: SEL 健康检查
    print("\n[6/6] SEL 健康检查")
    try:
        import subprocess
        import sys as _sys
        sel_result = subprocess.run(
            [_sys.executable, "sel_lint.py"],
            capture_output=True, text=True, timeout=60,
            cwd=str(STOCK_ANALYSIS),
        )
        lint_lines = sel_result.stdout.strip().split("\n")
        # 提取扫描结果行
        result_lines = [l for l in lint_lines if "发现" in l or "PASS" in l or "FAIL" in l or "总计" in l]
        for l in result_lines[:8]:
            print(f"    {l.strip()}")
        if sel_result.returncode != 0:
            print(f"    SEL lint 返回非零: {sel_result.returncode}")
    except Exception as e:
        print(f"    SEL lint 执行异常: {e}")

    print("\n管线完成")


def _write_pipeline_summary(result_dy: dict, result_web: dict,
                            result_gh: dict, proposals: list[dict]):
    """管线完成后写入摘要，供 Feishu 推送。"""
    from knowledge_gap_registry import load_registry, gap_statistics
    from knowledge_absorber import absorption_stats

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    gs = gap_statistics()
    abs_stats = absorption_stats()

    # 读数发现日志中的最新记录
    new_findings = 0
    top_findings = []
    if PROSPECTOR_LOG.exists():
        try:
            log = json.loads(PROSPECTOR_LOG.read_text(encoding="utf-8"))
            new_findings = len(log)
            # 取最新5条高价值发现
            recent = sorted(log, key=lambda x: x.get("discovered_at", ""), reverse=True)[:5]
            for f in recent:
                top_findings.append(f"  • [{f.get('relevance', '?')}] {f.get('title', '?')[:60]}")
        except Exception:
            pass

    lines = [
        f"## KAE 管线摘要 — {now}",
        "",
        f"**搜索统计**",
        f"  • 抖音: {result_dy.get('searches_done', 0)} 搜索, {result_dy.get('findings', 0)} 发现",
        f"  • Web: {result_web.get('findings', 0)} 发现",
        f"  • GitHub: {result_gh.get('findings', 0)} 发现",
        "",
        f"**缺口面板**",
        f"  • 总缺口: {gs['total']} 项",
        f"  • 开放中: {gs['open_count']} 项",
        f"  • 已吸收: {gs.get('by_status', {}).get('absorbed', 0)} 项",
        f"  • 本轮提案: {len(proposals)} 个",
        "",
        f"**吸收管线**",
        f"  • 总发现: {abs_stats['total_findings']} 条",
        f"  • 已吸收: {abs_stats['absorbed_findings']} 条",
        f"  • 提案: {abs_stats['total_proposals']} 个 ({abs_stats.get('proposals_by_status', '?')})",
        "",
        f"**最新发现**",
    ]
    if top_findings:
        lines.extend(top_findings)
    else:
        lines.append("  (本轮无新发现)")

    lines.append("")
    lines.append("---")
    lines.append(f"_KAE Pipeline @ {now}_")

    # 写入 daily digest
    try:
        DAILY_DIGEST_FILE.parent.mkdir(parents=True, exist_ok=True)
        DAILY_DIGEST_FILE.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  → 摘要已写入 {DAILY_DIGEST_FILE}")
    except Exception as e:
        logger.warning("写入 daily digest 失败: %s", e)


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
        auto_exec = "--auto-execute" in args
        cmd_absorb(auto_execute=auto_exec)
    elif cmd == "pipeline":
        inc = "--incremental" in args
        cmd_pipeline(incremental=inc)
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


def _open_exploration():
    """缺口归零时，从博主引用中探索新方向。

    扫描抖音归档提取博主引用的论文/GitHub/工具等，
    为每个高价值引用创建新知识缺口 → 后续 pipeline 步骤自动搜索。
    """
    from knowledge_tracer import scan_archives
    from knowledge_gap_registry import add_gap

    refs = scan_archives()
    if not refs:
        print("  无归档引用，跳过")
        return

    # 去重+评分
    seen = set()
    scored = []
    for r in refs:
        name = r.get("ref_name", "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        score = 1
        if r.get("confidence", 0) >= 3:
            score += 1
        if r.get("ref_type") in ("github", "paper_arxiv", "paper_named", "tool_framework"):
            score += 1
        scored.append((score, r))

    scored.sort(key=lambda x: -x[0])
    top = scored[:15]

    print(f"  引用提取: {len(refs)} 条原始 → {len(scored)} 个唯一 → {len(top)} 个高优先级")
    for s, r in top:
        print(f"    [{r.get('ref_type','?')}] {r.get('ref_name','')[:60]} (博主:{r.get('creator','?')})")

    created = 0
    for s, r in top:
        name = r["ref_name"]
        safe_id = re.sub(r"[^a-z0-9]", "-", name.lower())[:40]
        gap_id = f"explore-{safe_id}"
        ctx = r.get("context", "")[:200]
        desc = f"博主 {r.get('creator','?')} 引用" + (f": {ctx}" if ctx else f": {name[:80]}")
        if add_gap({
            "gap_id": gap_id,
            "title": f"探索: {name[:60]}",
            "description": desc,
            "priority": "P1" if s >= 3 else "P2",
            "domain": "open-exploration",
            "search_queries": [name[:100]],
            "target_sources": ["web", "github"],
        }):
            created += 1

    print(f"  开放探索完成: 创建 {created} 个新探索缺口")


if __name__ == "__main__":
    main()
