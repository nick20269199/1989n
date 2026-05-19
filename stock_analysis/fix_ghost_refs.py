#!/usr/bin/env python3
"""
Fix Ghost References — auto-fix broken [[wiki-links]] in memory files.

Strategies (in order):
1. Exact match: target file exists at the referenced path → no fix needed
2. Stem match: target file's stem matches another file's stem (e.g., [[sanbei-bug-fix]] → sanbei-bug-fix-2026-05-12.md)
3. Fuzzy match: significant word overlap (e.g., [[portfolio-cost-basis]] → portfolio-cost-basis-2026-05-12.md)
4. Skip: no match found → report only

Usage:
    python fix_ghost_refs.py          # dry-run: show what would be fixed
    python fix_ghost_refs.py --apply  # actually modify files
"""
import re, sys, json
from pathlib import Path
from collections import defaultdict

BASE = Path("D:/1989n/.claude/memory")
EXTERNAL = [
    Path("D:/1989n/CLAUDE.md"),
    Path("D:/1989n/stock_analysis/CLAUDE.md"),
]
LEARNING = Path("D:/1989n/stock_data/learning")

DRY_RUN = "--apply" not in sys.argv

# ── Index all available file stems ──────────────────────────────────────
def build_stem_index() -> dict[str, Path]:
    """Build stem → path map. Each stem indexed with and without date suffix."""
    index = {}
    for root in [BASE, LEARNING]:
        if not root.exists():
            continue
        for f in root.rglob("*.md"):
            stem = f.stem.lower()
            index[stem] = f
            # Also index without date suffix: "foo-2026-05-12" → also "foo"
            ds = re.search(r'-\d{4}-\d{2}-\d{2}$', stem)
            if ds:
                base = stem[:ds.start()]
                if base not in index:
                    index[base] = f
                # For .md extension match
                index[base + ".md"] = f

    # Also index external files
    for f in EXTERNAL:
        if f.exists():
            stem = f.stem.lower()
            index[stem] = f

    return index


def collect_all_md_files() -> list[Path]:
    files = []
    for root in [BASE, LEARNING]:
        if root.exists():
            for f in root.rglob("*.md"):
                files.append(f)
    for f in EXTERNAL:
        if f.exists():
            files.append(f)
    return files


def find_best_match(target: str, stem_index: dict) -> str | None:
    """
    Find best match for target in stem index.
    Returns the stem (key in stem_index) or None.
    """
    tl = target.lower().replace(".md", "")

    # Skip non-md references (JSON data files, URLs, etc)
    if not re.match(r'^[a-zA-Z0-9_\-/]+$', target) or any(ext in target.lower() for ext in ['.json', '.csv', '.xlsx', '.png', '.jpg', '.py']):
        return None

    # 1. Exact stem match
    if tl in stem_index:
        return tl

    # 2. With .md
    if tl + ".md" in stem_index:
        return tl + ".md"

    # 3. Fuzzy: word overlap (requires ≥3 overlapping words for safety)
    target_words = set(re.split(r'[-_\s]+', tl))
    best_score = 0
    best_match = None
    for stem in stem_index:
        stem_words = set(re.split(r'[-_\s]+', stem.lower().replace(".md", "")))
        overlap = len(target_words & stem_words)
        if overlap >= 3 and overlap > best_score:
            best_score = overlap
            best_match = stem

    if best_match and best_score >= 3:
        return best_match

    return None


# ── Fixer ───────────────────────────────────────────────────────────────
def fix_file(fp: Path, stem_index: dict) -> list[dict]:
    """Find and optionally fix ghost references in a file."""
    content = fp.read_text(encoding="utf-8", errors="ignore")
    changes = []

    def replace_link(match):
        full = match.group(0)
        target = match.group(1).strip()
        display = match.group(2) if match.group(2) else None

        # Check if target already resolves
        existing_stem = target.lower().replace(".md", "")
        if existing_stem in stem_index:
            return full  # no fix needed

        best_stem = find_best_match(target, stem_index)
        if best_stem:
            fixed_target = Path(stem_index[best_stem]).stem
            if display:
                new_link = f"[[{fixed_target}|{display}]]"
            else:
                new_link = f"[[{fixed_target}]]"
            changes.append({
                "file": str(fp),
                "old": full,
                "new": new_link,
                "target": target,
                "fixed_to": fixed_target,
            })
            return new_link
        return full

    # Matches [[target]] or [[target|display]]
    pattern = re.compile(r'\[\[([^\]]+?)(?:\|([^\]]+?))?\]\]')
    new_content = pattern.sub(replace_link, content)

    if changes and not DRY_RUN:
        fp.write_text(new_content, encoding="utf-8")
        print(f"  ✏️  {fp.name}: {len(changes)} 处修复")

    return changes


def main():
    stem_index = build_stem_index()
    files = collect_md_files = collect_all_md_files()

    total_changes = []
    orphan_targets = set()  # targets with no match at all

    for fp in files:
        if "MEMORY.md" in str(fp):
            continue
        changes = fix_file(fp, stem_index)
        total_changes.extend(changes)
        for c in changes:
            if not c.get("fixed_to"):
                orphan_targets.add(c["target"])

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n=== 幽灵引用修复: {'DRY RUN' if DRY_RUN else '已应用'} ===")
    print(f"总文件数: {len(files)}")
    print(f"总修复数: {len(total_changes)}")

    # Group by file
    by_file = defaultdict(list)
    for c in total_changes:
        by_file[c["file"]].append(c)

    for filepath, changes in sorted(by_file.items()):
        print(f"\n{Path(filepath).relative_to(BASE.parent) if BASE.parent in Path(filepath).parents else filepath}:")
        for c in changes:
            status = "✅" if c.get("fixed_to") else "❌"
            print(f"  {status} [[{c['target']}]] → [[{c.get('fixed_to', '???')}]]")

    if DRY_RUN:
        print(f"\n运行 'python fix_ghost_refs.py --apply' 应用修复")
    else:
        print(f"\n修复完成。重新运行 sel_lint.py 验证。")

    # Also generate a JSON report
    report = {
        "dry_run": DRY_RUN,
        "total_fixes": len(total_changes),
        "total_files": len(files),
        "unresolved": sorted(orphan_targets),
        "fixes": total_changes,
    }
    report_path = BASE / "daily" / "_fix_ghost_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告: {report_path}")


if __name__ == "__main__":
    main()
