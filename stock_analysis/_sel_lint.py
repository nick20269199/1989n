#!/usr/bin/env python3
"""SEL Morning Lint — 6 scans, detect only, no fix."""
import os, re, json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

BASE = Path("D:/1989n/.claude/memory")
PHYSICS = Path("D:/1989n/stock_data/physics_reading")
TODAY = datetime.now().date()
CUTOFF_14D = TODAY - timedelta(days=14)
CUTOFF_7D = TODAY - timedelta(days=7)

results = {f"scan{i}": {"findings": [], "severity": "LOW"} for i in range(1, 7)}

def severity_label(count, threshold_high=3, threshold_med=1):
    if count >= threshold_high: return "HIGH"
    if count >= threshold_med: return "MEDIUM"
    return "LOW"

# ============================================================
# SCAN 1: Knowledge Rot
# ============================================================
rot_findings = []
for root, dirs, files in os.walk(str(BASE / "knowledge")):
    for fname in files:
        if not fname.endswith('.md'): continue
        fp = Path(root) / fname
        content = fp.read_text(encoding='utf-8', errors='ignore')
        mtime = datetime.fromtimestamp(fp.stat().st_mtime).date()
        days_since_mod = (TODAY - mtime).days
        has_reviewed = 'last_reviewed' in content[:800]

        rel = str(fp.relative_to(BASE))

        if days_since_mod > 14:
            rot_findings.append({
                "file": rel, "days_ago": days_since_mod,
                "issue": f"超过14天({days_since_mod}d)未修改",
                "severity": "HIGH",
            })
        elif not has_reviewed:
            rot_findings.append({
                "file": rel, "days_ago": days_since_mod,
                "issue": "frontmatter缺少last_reviewed字段",
                "severity": "LOW",
            })

results["scan1"]["findings"] = rot_findings
results["scan1"]["severity"] = severity_label(
    sum(1 for f in rot_findings if f["severity"] == "HIGH"))

# ============================================================
# SCAN 2: Draft Long-Term Unverified
# ============================================================
draft_findings = []
for root, dirs, files in os.walk(str(BASE)):
    for fname in files:
        if not fname.endswith('.md'): continue
        fp = Path(root) / fname
        content = fp.read_text(encoding='utf-8', errors='ignore')
        fm = content[:600].lower()
        if 'status: draft' in fm or 'status:draft' in fm:
            mtime = datetime.fromtimestamp(fp.stat().st_mtime).date()
            days_old = (TODAY - mtime).days
            rel = str(fp.relative_to(BASE))
            if days_old > 7:
                draft_findings.append({
                    "file": rel, "days_old": days_old,
                    "issue": f"draft状态超7天({days_old}d)未验证",
                    "severity": "MEDIUM",
                })
            else:
                draft_findings.append({
                    "file": rel, "days_old": days_old,
                    "issue": f"draft状态{days_old}d (正常)",
                    "severity": "LOW",
                })

results["scan2"]["findings"] = draft_findings
results["scan2"]["severity"] = severity_label(
    sum(1 for f in draft_findings if f["severity"] in ("HIGH", "MEDIUM")))


# ============================================================
# SCAN 3: New-Old Conflicts
# ============================================================
conflict_findings = []
# Find today's new files
new_files = []
for d in [PHYSICS, BASE / "knowledge"]:
    if d.exists():
        for f in d.rglob("*.md"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime).date()
            if mtime == TODAY:
                new_files.append(f)
            elif mtime == TODAY - timedelta(days=1):
                new_files.append(f)

# Check against feedback rules
feedback_dir = BASE / "feedback"
feedback_rules = {}
for fb in feedback_dir.glob("*.md"):
    fb_content = fb.read_text(encoding='utf-8', errors='ignore')
    # Extract key assertions (lines with **Why:** or **How to apply:**)
    key_lines = re.findall(r'\*\*(Why|How to apply):\*\*\s*(.+?)(?:\n|$)', fb_content)
    if key_lines:
        feedback_rules[fb.stem] = key_lines

for nf in new_files[:5]:  # Top 5 newest
    nf_content = nf.read_text(encoding='utf-8', errors='ignore')[:3000]
    for rule_name, assertions in feedback_rules.items():
        for tag, text in assertions:
            # Simple keyword overlap check
            words = set(text.lower().split())
            nf_words = set(nf_content.lower().split())
            overlap = words & nf_words
            # Check for negation/contradiction indicators
            if len(overlap) > 3:
                # Check if there's contradictory language
                has_negation = any(w in nf_content.lower() for w in [
                    "not ", "don't ", "shouldn't", "avoid", "never", "wrong", "incorrect"
                ])
                if has_negation:
                    conflict_findings.append({
                        "file": str(nf.relative_to(nf.parents[2])),
                        "rule": rule_name,
                        "shared_terms": list(overlap)[:5],
                        "issue": "可能矛盾: 新文件含否定语言与feedback规则重叠",
                        "severity": "HIGH",
                    })

results["scan3"]["findings"] = conflict_findings
results["scan3"]["severity"] = severity_label(
    sum(1 for f in conflict_findings if f["severity"] == "HIGH"))


# ============================================================
# SCAN 4: Rule Disconnection
# ============================================================
disco_findings = []
# Collect all memory content
all_content = {}
for root, dirs, files in os.walk(str(BASE)):
    for fname in files:
        if fname.endswith('.md'):
            fp = Path(root) / fname
            all_content[str(fp)] = fp.read_text(encoding='utf-8', errors='ignore')

for fb in feedback_dir.glob("*.md"):
    fb_name = fb.stem
    ref_count = 0
    for fpath, content in all_content.items():
        if str(fb) == fpath:
            continue
        if fb_name in content:
            ref_count += 1
    if ref_count == 0:
        disco_findings.append({
            "rule_file": fb.name,
            "refs": 0,
            "issue": "僵尸规则: 无任何memory文件引用此规则",
            "severity": "MEDIUM",
        })

results["scan4"]["findings"] = disco_findings
results["scan4"]["severity"] = severity_label(
    sum(1 for f in disco_findings if f["severity"] in ("HIGH", "MEDIUM")))


# ============================================================
# SCAN 5: Ingest Incomplete
# ============================================================
ingest_findings = []
raw_dir = BASE / "raw"
knowledge_dir = BASE / "knowledge"

# Raw files that look like knowledge (not sessions, not tools)
raw_files = []
for f in raw_dir.glob("*.md"):
    name = f.name.lower()
    if 'session-archive' in name: continue
    raw_files.append(f)

# Knowledge file stems for matching
knowledge_stems = set()
for f in knowledge_dir.rglob("*.md"):
    knowledge_stems.add(f.stem.lower())

# Topic mapping from raw filenames
raw_topics = {}
for f in raw_files:
    stem = f.stem.lower()
    # Normalize to extract topic
    topic = stem.replace('knowledge_', '').replace('knowlege_', '')
    topic = topic.replace('_', ' ').strip()
    raw_topics[f.name] = topic

for fname, topic in raw_topics.items():
    # Check if any knowledge file covers this topic
    found = False
    for ks in knowledge_stems:
        topic_words = set(topic.split())
        ks_words = set(ks.replace('-', ' ').split())
        if len(topic_words & ks_words) >= 2:
            found = True
            break
    if not found:
        ingest_findings.append({
            "raw_file": fname,
            "topic": topic,
            "issue": "raw/中有但knowledge/无对应结构化条目",
            "severity": "LOW",
        })

results["scan5"]["findings"] = ingest_findings
results["scan5"]["severity"] = severity_label(
    sum(1 for f in ingest_findings if f["severity"] in ("HIGH", "MEDIUM")))


# ============================================================
# SCAN 6: Missing Connections
# ============================================================
missing_findings = []
recent = []
for root, dirs, files in os.walk(str(BASE)):
    for fname in files:
        if not fname.endswith('.md'): continue
        fp = Path(root) / fname
        mtime = datetime.fromtimestamp(fp.stat().st_mtime)
        if mtime.date() >= CUTOFF_7D:
            content = fp.read_text(encoding='utf-8', errors='ignore')
            recent.append({
                'path': str(fp.relative_to(BASE)),
                'content': content[:4000],
            })

# Extract concepts
file_concepts = {}
for rf in recent:
    text = rf['content']
    headers = re.findall(r'^#{1,3}\s+(.+?)$', text, re.MULTILINE)
    bolds = re.findall(r'\*\*(.{3,60}?)\*\*', text)
    wikis = re.findall(r'\[\[(.+?)\]\]', text)
    terms = set()
    for t in headers + bolds + wikis:
        t = t.lower().strip()
        if len(t) > 4 and t not in {'frontmatter', 'description', 'content', 'title',
                                     'created', 'updated', 'summary', 'notes', 'details'}:
            terms.add(t)
    file_concepts[rf['path']] = terms

# Find pairs with overlapping concepts but no mutual reference
from itertools import combinations
all_pairs = list(combinations(recent, 2))
for a, b in all_pairs:
    a_c = file_concepts.get(a['path'], set())
    b_c = file_concepts.get(b['path'], set())
    shared = a_c & b_c
    if len(shared) >= 3:
        a_name = Path(a['path']).stem.lower()
        b_name = Path(b['path']).stem.lower()
        a_refs_b = b_name in a['content'].lower()
        b_refs_a = a_name in b['content'].lower()
        if not (a_refs_b and b_refs_a):
            missing_findings.append({
                "file_a": a['path'],
                "file_b": b['path'],
                "shared_concepts": sorted(list(shared))[:8],
                "issue": "讨论相同概念但未相互引用",
                "severity": "LOW",
            })

# Limit to top 10
missing_findings = missing_findings[:10]
results["scan6"]["findings"] = missing_findings
results["scan6"]["severity"] = severity_label(len(missing_findings), 10, 5)


# ============================================================
# GENERATE REPORT
# ============================================================
daily_dir = BASE / "daily"
daily_dir.mkdir(parents=True, exist_ok=True)

report_path = daily_dir / f"{TODAY.isoformat()}_lint.md"

lines = []
lines.append(f"# SEL Morning Lint Report — {TODAY}")
lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
overall_high = sum(1 for s in results.values() if s["severity"] == "HIGH")
overall_med = sum(1 for s in results.values() if s["severity"] == "MEDIUM")
if overall_high > 0:
    sev_text = f"**HIGH** ({overall_high}项HIGH, {overall_med}项MEDIUM)"
elif overall_med > 0:
    sev_text = f"**MEDIUM** ({overall_med}项MEDIUM)"
else:
    sev_text = "**LOW** (全部正常)"
lines.append(f"**总体严重度**: {sev_text}")

lines.append("")
lines.append("---")
lines.append("")

# Scan 1
lines.append("## 1. 知识腐烂检测 (Knowledge Rot)")
lines.append(f"**严重度: {results['scan1']['severity']}** | 扫描knowledge/下所有.md")
lines.append("")
if results['scan1']['findings']:
    for f in results['scan1']['findings']:
        lines.append(f"- [{f['severity']}] **{f['file']}** — {f['issue']} (距上次修改: {f.get('days_ago', '?')}d)")
else:
    lines.append("- 无问题，所有文件均在14天内。")
lines.append("")

# Scan 2
lines.append("## 2. Draft长期未验证")
lines.append(f"**严重度: {results['scan2']['severity']}** | 扫描status:draft文件")
lines.append("")
if results['scan2']['findings']:
    overdue = [f for f in results['scan2']['findings'] if f['severity'] != 'LOW']
    normal = [f for f in results['scan2']['findings'] if f['severity'] == 'LOW']
    if overdue:
        for f in overdue:
            lines.append(f"- [{f['severity']}] **{f['file']}** — {f['issue']}")
    if normal:
        lines.append(f"\n正常draft ({len(normal)}个):")
        for f in normal[:5]:
            lines.append(f"- [OK] {f['file']} ({f['days_old']}d)")
        if len(normal) > 5:
            lines.append(f"- ... 还有{len(normal)-5}个")
else:
    lines.append("- 无draft文件。")
lines.append("")

# Scan 3
lines.append("## 3. 新-旧矛盾检测")
lines.append(f"**严重度: {results['scan3']['severity']}** | 今天新文件 vs feedback规则")
lines.append("")
if results['scan3']['findings']:
    for f in results['scan3']['findings']:
        lines.append(f"- [{f['severity']}] **{f['file']}** vs {f['rule']} — {f['issue']}")
        lines.append(f"  共享词: {f.get('shared_terms', [])}")
else:
    lines.append("- 未发现矛盾。今天无新增文件。")
lines.append("")

# Scan 4
lines.append("## 4. 规则脱节 (Zombie Rules)")
lines.append(f"**严重度: {results['scan4']['severity']}** | feedback/引用统计")
lines.append("")
if results['scan4']['findings']:
    for f in results['scan4']['findings']:
        lines.append(f"- [{f['severity']}] **{f['rule_file']}** — {f['issue']}")
else:
    lines.append("- 无僵尸规则，所有feedback文件均有引用。")
lines.append("")

# Scan 5
lines.append("## 5. Ingest未完成 (Raw vs Knowledge)")
lines.append(f"**严重度: {results['scan5']['severity']}** | raw/归档 vs knowledge/结构化")
lines.append("")
if results['scan5']['findings']:
    lines.append(f"共 {len(results['scan5']['findings'])} 个待消化条目:")
    for f in results['scan5']['findings'][:15]:
        lines.append(f"- [{f['severity']}] **{f['raw_file']}** — {f['topic'][:80]}")
    if len(results['scan5']['findings']) > 15:
        lines.append(f"- ... 还有{len(results['scan5']['findings'])-15}个")
else:
    lines.append("- 所有raw文件均有对应knowledge条目。")
lines.append("")

# Scan 6
lines.append("## 6. 缺失连接")
lines.append(f"**严重度: {results['scan6']['severity']}** | 最近7天文件交叉引用")
lines.append("")
if results['scan6']['findings']:
    lines.append(f"共 {len(results['scan6']['findings'])} 对文件讨论相同概念但未互引:")
    for f in results['scan6']['findings'][:10]:
        lines.append(f"- [{f['severity']}] **{Path(f['file_a']).name}** ↔ **{Path(f['file_b']).name}**")
        lines.append(f"  共享概念: {', '.join(f['shared_concepts'][:5])}")
else:
    lines.append("- 所有相关文件均有交叉引用。")
lines.append("")

# Summary
lines.append("---")
lines.append("## 汇总")
high_count = sum(1 for s in results.values() for f in s['findings'] if f['severity'] == 'HIGH')
med_count = sum(1 for s in results.values() for f in s['findings'] if f['severity'] == 'MEDIUM')
low_count = sum(1 for s in results.values() for f in s['findings'] if f['severity'] == 'LOW')
lines.append(f"- HIGH: {high_count} | MEDIUM: {med_count} | LOW: {low_count}")
lines.append(f"- 飞书告警: {'已触发' if high_count > 0 else '无需 (无HIGH级问题)'}")

report_content = "\n".join(lines)
report_path.write_text(report_content, encoding="utf-8")
print(f"Report written: {report_path}")
print(f"Summary: HIGH={high_count} MEDIUM={med_count} LOW={low_count}")
