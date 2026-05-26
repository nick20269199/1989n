#!/usr/bin/env python3
"""
工程部 Morning Lint v2 — 确定性6项检测，不修复。

Changes from v1:
- Parses frontmatter last_reviewed (not mtime) for knowledge rot
- Parses frontmatter status field for draft detection
- Ghost reference check (broken [[wiki-links]])
- External files: CLAUDE.md × 2, learning/findings*
- Feishu alert integration (actual send, not just print)
- Trend history (_lint_history.json)
- Exit codes for scheduler: 0=LOW 1=MEDIUM 2=HIGH
"""
import os, re, json, sys
from pathlib import Path
from datetime import datetime, date, timedelta
from collections import defaultdict
from itertools import combinations

# ── Config ──────────────────────────────────────────────────────────────
BASE = Path("D:/1989n/.claude/memory")
STOCK_ANALYSIS = Path("D:/1989n/stock_analysis")
LEARNING_DIR = Path("D:/1989n/stock_data/learning")

# Additional external files to scan
EXTERNAL_FILES = [
    Path("D:/1989n/CLAUDE.md"),
    Path("D:/1989n/stock_analysis/CLAUDE.md"),
]

# Directories under memory/ to scan
MEMORY_SUBDIRS = ["knowledge", "feedback", "user", "project"]

TODAY = date.today()
CUTOFF_14D = TODAY - timedelta(days=14)
CUTOFF_7D = TODAY - timedelta(days=7)

# Frontmatter field names, by lang
FM_LAST_REVIEWED = {"last_reviewed", "lastreviewed", "reviewed", "verified_until"}
FM_STATUS = {"status"}
FM_CREATED = {"created", "date", "created_date"}

logger = None  # will use print unless feishu_sender is available


# ── Frontmatter Parser ──────────────────────────────────────────────────
def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter fields as plain dict."""
    m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split('\n'):
        line = line.strip()
        if ':' in line:
            key, _, val = line.partition(':')
            fm[key.strip().lower()] = val.strip().strip('"\'')
    return fm


def get_frontmatter_date(fm: dict, field_names: set) -> date | None:
    """Try multiple date field names, return date or None."""
    for key in field_names:
        if key in fm and fm[key]:
            val = fm[key]
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
                try:
                    return datetime.strptime(val[:10], fmt).date()
                except ValueError:
                    continue
    return None


# ── File Walker ─────────────────────────────────────────────────────────
def collect_files() -> list[tuple[Path, str]]:
    """Return list of (path, relative_path) for all scanned files."""
    files = []
    for subdir in MEMORY_SUBDIRS:
        d = BASE / subdir
        if d.exists():
            for f in sorted(d.rglob("*.md")):
                rel = str(f.relative_to(BASE))
                files.append((f, rel))

    # Root-level memory files (migrated project memories)
    for f in sorted(BASE.glob("*.md")):
        if f.name in ("SEL.md", "BRAIN.md", "MEMORY.md"):
            continue
        rel = str(f.relative_to(BASE))
        files.append((f, rel))

    # External files
    for f in EXTERNAL_FILES:
        if f.exists():
            files.append((f, str(f)))

    # Learning directory findings files
    if LEARNING_DIR.exists():
        for f in LEARNING_DIR.glob("findings_*.md"):
            files.append((f, str(f)))

    return files


def read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


# ── Scan 1: Knowledge Rot ──────────────────────────────────────────────
def scan_knowledge_rot(files: list) -> list:
    """Files where last_reviewed > 14 days, or missing the field."""
    findings = []
    for fp, rel in files:
        if rel.startswith("feedback") or rel.startswith("raw/"):
            continue
        content = read_file(fp)
        fm = parse_frontmatter(content)
        last_reviewed = get_frontmatter_date(fm, FM_LAST_REVIEWED)

        if last_reviewed:
            days = (TODAY - last_reviewed).days
            if days > 14:
                findings.append({
                    "file": rel, "days": days,
                    "issue": f"超过14天未复审 ({days}d)",
                    "severity": "MEDIUM" if days <= 30 else "HIGH",
                })
        else:
            # Check mtime as fallback signal
            mtime = datetime.fromtimestamp(fp.stat().st_mtime).date()
            days = (TODAY - mtime).days
            if days > 14:
                findings.append({
                    "file": rel, "days": days,
                    "issue": f"无last_reviewed字段 + mtime超14天 ({days}d)",
                    "severity": "MEDIUM",
                })
            else:
                findings.append({
                    "file": rel, "days": days,
                    "issue": "frontmatter缺少last_reviewed字段 (mtime正常)",
                    "severity": "LOW",
                })
    return findings


# ── Scan 2: Draft Unverified >7 days ────────────────────────────────────
def scan_draft_unverified(files: list) -> list:
    """Files with status: draft and last_reviewed/created > 7 days."""
    findings = []
    for fp, rel in files:
        content = read_file(fp)
        fm = parse_frontmatter(content)
        status = fm.get("status", "").lower()
        if status != "draft":
            continue

        # Use last_reviewed first, fall back to created, then mtime
        ref_date = get_frontmatter_date(fm, FM_LAST_REVIEWED)
        if not ref_date:
            ref_date = get_frontmatter_date(fm, FM_CREATED)
        if not ref_date:
            ref_date = datetime.fromtimestamp(fp.stat().st_mtime).date()

        days = (TODAY - ref_date).days
        findings.append({
            "file": rel,
            "days": days,
            "ref_date": ref_date.isoformat(),
            "issue": f"draft状态超过7天未验证 ({days}d)",
            "severity": "HIGH" if days > 14 else ("MEDIUM" if days > 7 else "LOW"),
        })
    return findings


# ── Scan 3: Ghost References (broken [[wiki-links]]) ────────────────────
def scan_ghost_references(files: list) -> list:
    """
    Find [[links]] that don't resolve to any existing file.
    Also detect mismatched filenames (target exists but with different date suffix).
    """
    # Build lookup: stem → full path (for fuzzy matching)
    all_files = {}
    for fp, rel in files:
        stem = fp.stem.lower()
        all_files[stem] = rel
        # Also index without date suffix: "sanbei-bug-fix-2026-05-12" → also "sanbei-bug-fix"
        date_suffix_match = re.search(r'-\d{4}-\d{2}-\d{2}$', stem)
        if date_suffix_match:
            base_stem = stem[:date_suffix_match.start()]
            all_files.setdefault(base_stem, rel)

    findings = []
    seen = set()

    for fp, rel in files:
        content = read_file(fp)
        # Skip MEMORY.md since it's intentionally a full index
        if "MEMORY.md" in rel:
            continue

        for match in re.finditer(r'\[\[([^\]]+?)\]\]', content):
            target = match.group(1).strip()
            target_lower = target.lower()

            # Skip non-md references (JSON data files, URLs, relative paths)
            if target_lower.endswith(('.json', '.csv', '.png', '.jpg', '.py')):
                continue

            if target_lower in seen:
                continue
            seen.add(target_lower)

            # Direct match?
            target_stem = target_lower.replace(".md", "")
            target_stem = target.replace(".md", "")
            if target_stem in all_files:
                continue

            # Fuzzy: check partial match
            matched = False
            for existing_stem, existing_rel in all_files.items():
                # One contains the other
                if target_stem in existing_stem or existing_stem in target_stem:
                    findings.append({
                        "source_file": rel,
                        "target": match.group(1),
                        "suggestion": existing_rel,
                        "issue": f"幽灵引用: [[{match.group(1)}]] → 最接近的是 {existing_rel}",
                        "severity": "MEDIUM",
                    })
                    matched = True
                    break

            if not matched:
                findings.append({
                    "source_file": rel,
                    "target": match.group(1),
                    "suggestion": None,
                    "issue": f"幽灵引用: [[{match.group(1)}]] → 无匹配文件",
                    "severity": "HIGH",
                })

    return findings


# ── Scan 4: Rule Disconnection (Zombie Rules) ───────────────────────────
def scan_zombie_rules(files: list) -> list:
    """Feedback files not referenced by any other memory file."""
    feedback_files = [(fp, rel) for fp, rel in files if rel.startswith("feedback/")]
    other_files = [(fp, rel) for fp, rel in files if not rel.startswith("feedback/")]

    # Build reference corpus from non-feedback files
    ref_corpus = ""
    for fp, rel in other_files:
        ref_corpus += read_file(fp).lower() + "\n"

    findings = []
    for fp, rel in feedback_files:
        stem = fp.stem
        # Check both the slug (feedback_xxx) and a shortened name
        ref_name = stem.replace("feedback_", "")
        if stem in ref_corpus or ref_name in ref_corpus:
            continue
        findings.append({
            "file": rel,
            "issue": "僵尸规则: 未被其他memory文件引用",
            "severity": "LOW",
        })
    return findings


# ── Scan 5: Ingest Incomplete ──────────────────────────────────────────
def scan_ingest_incomplete(files: list) -> list:
    """raw/ has content but knowledge/ has no structured version."""
    raw_dir = BASE / "raw"
    if not raw_dir.exists():
        return []

    # Knowledge topics (file stems without date suffixes)
    knowledge_stems = set()
    for fp, rel in files:
        if not rel.startswith("knowledge/"):
            continue
        stem = fp.stem.lower()
        knowledge_stems.add(stem)
        # Also add without date suffix
        ds = re.search(r'-\d{4}-\d{2}-\d{2}$', stem)
        if ds:
            knowledge_stems.add(stem[:ds.start()])

    findings = []
    for f in sorted(raw_dir.glob("*.md")):
        if "session-archive" in f.name.lower():
            continue
        stem = f.stem.lower()
        topic = stem.replace("knowledge_", "").replace("knowlege_", "")
        topic = topic.replace("_", " ").strip()

        # Check if any knowledge stem covers this
        matched = False
        topic_words = set(topic.split())
        for ks in knowledge_stems:
            ks_words = set(ks.replace("-", " ").split())
            if len(topic_words & ks_words) >= 2:
                matched = True
                break

        if not matched:
            findings.append({
                "file": f.name,
                "topic": topic[:80],
                "issue": "raw/存在但knowledge/无结构化版本",
                "severity": "LOW",
            })

    return findings


# ── Scan 6: Missing Connections ─────────────────────────────────────────
def scan_missing_connections(files: list) -> list:
    """Files modified within 7 days, sharing concepts but no mutual reference."""
    recent = []
    for fp, rel in files:
        mtime = datetime.fromtimestamp(fp.stat().st_mtime).date()
        if mtime >= CUTOFF_7D:
            recent.append((fp, rel))

    if len(recent) < 2:
        return []

    # Extract concepts per file
    file_concepts = {}
    for fp, rel in recent:
        content = read_file(fp)
        headers = re.findall(r'^#{1,3}\s+(.+?)$', content, re.MULTILINE)
        bolds = re.findall(r'\*\*(.{3,60}?)\*\*', content)
        wikis = re.findall(r'\[\[(.+?)\]\]', content)
        terms = set()
        for t in headers + bolds + wikis:
            t = t.lower().strip()
            if len(t) > 4 and t not in {
                "frontmatter", "description", "content", "title",
                "created", "updated", "summary", "notes", "details",
                "name", "type", "status",
            }:
                terms.add(t)
        file_concepts[rel] = terms

    findings = []
    for a, b in combinations(recent, 2):
        a_rel, b_rel = a[1], b[1]
        a_c = file_concepts.get(a_rel, set())
        b_c = file_concepts.get(b_rel, set())
        shared = a_c & b_c
        if len(shared) >= 3:
            a_content = read_file(a[0]).lower()
            b_content = read_file(b[0]).lower()
            a_stem = Path(a_rel).stem.lower()
            b_stem = Path(b_rel).stem.lower()
            a_refs_b = b_stem in a_content or b_stem.replace("feedback_", "") in a_content
            b_refs_a = a_stem in b_content or a_stem.replace("feedback_", "") in b_content

            if not (a_refs_b and b_refs_a):
                findings.append({
                    "file_a": a_rel,
                    "file_b": b_rel,
                    "shared_concepts": sorted(list(shared))[:8],
                    "issue": "讨论相同概念但未相互引用",
                    "severity": "LOW",
                })

    return findings[:15]  # cap at 15


# ── Feishu Alert ────────────────────────────────────────────────────────
def send_alert_if_needed(summary: dict):
    """Send HIGH-level findings to Feishu via existing sender."""
    if summary["high_count"] == 0:
        return

    try:
        sys.path.insert(0, str(STOCK_ANALYSIS))
        from feishu_sender import send_feishu_alert
    except ImportError:
        print("[lint] feishu_sender not available, skipping alert")
        return

    # Consice alert: one line per HIGH issue
    lines = [f"**{s['issue']}**" for s in summary["high_items"]]
    if summary["med_count"] > 0:
        lines.append(f"\n另有 {summary['med_count']} 项 MEDIUM 问题")

    send_feishu_alert(
        title=f"工程部 — {summary['high_count']}项HIGH",
        content="\n".join(lines),
    )


# ── Trend History ───────────────────────────────────────────────────────
def update_trend(summary: dict):
    """Append today's scan result to _lint_history.json."""
    history_path = BASE / "daily" / "_lint_history.json"
    entry = {
        "date": TODAY.isoformat(),
        "high": summary["high_count"],
        "med": summary["med_count"],
        "low": summary["low_count"],
        "draft_count": summary.get("draft_count", 0),
        "draft_max_days": summary.get("draft_max_days", 0),
        "ghost_count": summary.get("ghost_count", 0),
    }

    history = []
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            history = []

    # Avoid duplicate for today
    history = [h for h in history if h.get("date") != TODAY.isoformat()]
    history.append(entry)
    history = history[-90:]  # keep last 90 days
    history_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def trend_alert(history: list) -> list:
    """Check for deteriorating trends."""
    alerts = []
    if len(history) < 3:
        return alerts

    recent = sorted(history, key=lambda x: x["date"])[-5:]

    # Draft aging trend: consecutive increases in max days
    draft_days = [h.get("draft_max_days", 0) for h in recent if h.get("draft_count", 0) > 0]
    if len(draft_days) >= 3:
        if all(draft_days[i] < draft_days[i + 1] for i in range(len(draft_days) - 1)):
            alerts.append({
                "issue": f"draft老化持续恶化: {draft_days}",
                "severity": "HIGH",
            })

    # Zero knowledge growth: 7 days with no new HIGH issues (stagnation signal)
    if len(recent) >= 7:
        last_7 = recent[-7:]
        if all(h["high"] == 0 and h["med"] == 0 for h in last_7):
            alerts.append({
                "issue": "知识库零增长: 连续7天未发现任何问题",
                "severity": "MEDIUM",
            })

    return alerts


# ── Severity Helper ─────────────────────────────────────────────────────
def severity_label(count: int, high_th=3, med_th=1) -> str:
    if count >= high_th:
        return "HIGH"
    if count >= med_th:
        return "MEDIUM"
    return "LOW"


# ── Main ────────────────────────────────────────────────────────────────
def main():
    files = collect_files()
    print(f"[lint] 扫描文件数: {len(files)}")

    # Run all scans
    rot = scan_knowledge_rot(files)
    draft = scan_draft_unverified(files)
    ghost = scan_ghost_references(files)
    zombie = scan_zombie_rules(files)
    ingest = scan_ingest_incomplete(files)
    missing = scan_missing_connections(files)

    scans = {
        "1_知识腐烂": rot,
        "2_Draft未验证": draft,
        "3_幽灵引用": ghost,
        "4_僵尸规则": zombie,
        "5_Ingest未完成": ingest,
        "6_缺失连接": missing,
    }

    # Count by severity per scan
    scan_severity = {}
    for name, items in scans.items():
        high = sum(1 for i in items if i["severity"] == "HIGH")
        med = sum(1 for i in items if i["severity"] == "MEDIUM")
        scan_severity[name] = {"high": high, "med": med, "total": len(items)}

    # Summary
    all_findings = []
    for items in scans.values():
        all_findings.extend(items)

    high_count = sum(1 for i in all_findings if i["severity"] == "HIGH")
    med_count = sum(1 for i in all_findings if i["severity"] == "MEDIUM")
    low_count = sum(1 for i in all_findings if i["severity"] == "LOW")
    high_items = [i for i in all_findings if i["severity"] == "HIGH"]

    draft_count = sum(1 for i in draft if i["severity"] in ("HIGH", "MEDIUM"))
    draft_max_days = max((i["days"] for i in draft), default=0)
    ghost_count = len(ghost)

    summary = {
        "high_count": high_count,
        "med_count": med_count,
        "low_count": low_count,
        "high_items": high_items,
        "draft_count": draft_count,
        "draft_max_days": draft_max_days,
        "ghost_count": ghost_count,
        "scan_severity": scan_severity,
    }

    # ── Generate Report ───────────────────────────────────────────────
    daily_dir = BASE / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    report_path = daily_dir / f"{TODAY.isoformat()}_lint.md"

    lines = []
    lines.append(f"# 工程部 — {TODAY}")
    lines.append(f"> 工程部巡检 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 扫描: {len(files)} 文件 | 范围: {', '.join(MEMORY_SUBDIRS)} + {len(EXTERNAL_FILES)}外部 + learning/")
    lines.append("")

    if high_count:
        lines.append(f"**总体: {high_count}项 HIGH, {med_count}项 MEDIUM** 🔴")
    elif med_count:
        lines.append(f"**总体: {med_count}项 MEDIUM** 🟡")
    else:
        lines.append("**总体: LOW (全部正常)** ✅")
    lines.append("")

    for scan_name, items in scans.items():
        label = {"1_知识腐烂": "知识腐烂", "2_Draft未验证": "Draft长期未验证",
                 "3_幽灵引用": "幽灵引用", "4_僵尸规则": "规则脱节",
                 "5_Ingest未完成": "Ingest未完成", "6_缺失连接": "缺失连接"}.get(scan_name, scan_name)
        sv = scan_severity[scan_name]
        if sv["high"] + sv["med"] == 0:
            lines.append(f"### {label} ✅ — {sv['total']}项, 全部正常")
            continue

        sev = severity_label(sv["high"], 1, 0)
        icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}.get(sev, "⚪")
        lines.append(f"### {label} {icon} — {sv['high']}HIGH / {sv['med']}MEDIUM / {sv['total']}总")

        # Group by severity
        for s in ("HIGH", "MEDIUM", "LOW"):
            group = [i for i in items if i["severity"] == s]
            if not group:
                continue
            for item in group:
                f = item.get("file", item.get("source_file", ""))
                lines.append(f"  - **{f}**")
                lines.append(f"    {item['issue']}")
                if item.get("suggestion"):
                    lines.append(f"    → 建议: {item['suggestion']}")

    lines.append("")
    lines.append("---")
    # Total summary
    lines.append(f"**汇总**: HIGH={high_count} MEDIUM={med_count} LOW={low_count}")

    report_content = "\n".join(lines)
    report_path.write_text(report_content, encoding="utf-8")
    print(f"[lint] 报告已写: {report_path}")

    # ── Trend ─────────────────────────────────────────────────────────
    update_trend(summary)
    history_path = BASE / "daily" / "_lint_history.json"
    if history_path.exists():
        try:
            history = json.loads(history_path.read_text(encoding="utf-8"))
            trend_alerts = trend_alert(history)
            for ta in trend_alerts:
                print(f"[lint] 趋势告警 [{ta['severity']}]: {ta['issue']}")
        except Exception:
            pass

    # ── Feishu ─────────────────────────────────────────────────────────
    if high_count > 0:
        send_alert_if_needed(summary)
        print(f"[工程部] 飞书告警: {high_count}项HIGH")
    else:
        print(f"[工程部] 无HIGH, 跳过飞书告警")

    # ── Exit Code ──────────────────────────────────────────────────────
    if high_count > 0:
        sys.exit(2)
    elif med_count > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
