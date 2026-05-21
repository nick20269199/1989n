#!/usr/bin/env python3
"""
SEL Prune v1 — 归档过期 draft/腐烂知识文件。
运行在 Connect 之后 (09:15 每日)。

动作:
  1. draft 超 14 天 → 移入 archive/
  2. knowledge/ 文件 > 30 天无 last_reviewed → 标记待审
  3. 空目录清理

用法:
  cd D:/1989n/stock_analysis && python sel_prune.py
"""

import json
import os
import re
import shutil
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

BASE = Path("D:/1989n/.claude/memory")
ARCHIVE_DIR = BASE / "archive"
LINT_HISTORY = BASE / "daily" / "_lint_history.json"
TODAY = date.today()
CUTOFF_14D = TODAY - timedelta(days=14)
CUTOFF_30D = TODAY - timedelta(days=30)
CST = timezone(timedelta(hours=8))

pruned = {"draft_archived": 0, "stale_flagged": 0, "empty_dirs": 0}


def _archive_file(fp: Path):
    """将文件移入 archive/ 子目录（保持相对路径结构）"""
    rel = fp.relative_to(BASE)
    dest = ARCHIVE_DIR / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(fp), str(dest))
    pruned["draft_archived"] += 1
    print(f"[prune] 归档 → archive/{rel}")


def _parse_frontmatter(content: str) -> dict:
    m = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).split("\n"):
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip().lower()] = v.strip().strip("\"'")
    return fm


def prune_drafts():
    """draft 超 14 天 → 归档"""
    for root, dirs, files in os.walk(str(BASE)):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fp = Path(root) / fname
            content = fp.read_text(encoding="utf-8", errors="ignore")
            fm = _parse_frontmatter(content)
            status = fm.get("status", "")
            if status.lower() in ("draft",):
                mtime = datetime.fromtimestamp(fp.stat().st_mtime).date()
                if mtime < CUTOFF_14D:
                    _archive_file(fp)


def flag_stale():
    """knowledge/ 中 > 30 天无 last_reviewed 的标记"""
    kbase = BASE / "knowledge"
    if not kbase.exists():
        return
    for root, dirs, files in os.walk(str(kbase)):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fp = Path(root) / fname
            content = fp.read_text(encoding="utf-8", errors="ignore")
            fm = _parse_frontmatter(content)
            last_reviewed = fm.get("last_reviewed", "")
            if not last_reviewed:
                mtime = datetime.fromtimestamp(fp.stat().st_mtime).date()
                if mtime < CUTOFF_30D:
                    pruned["stale_flagged"] += 1
                    rel = str(fp.relative_to(BASE))
                    print(f"[prune] 待审(超30天无review): {rel}")


def clean_empty_dirs():
    """删除空目录"""
    for root, dirs, files in os.walk(str(BASE), topdown=False):
        if root == str(BASE) or root.startswith(str(ARCHIVE_DIR)):
            continue
        if not os.listdir(root):
            os.rmdir(root)
            pruned["empty_dirs"] += 1
            print(f"[prune] 删除空目录: {os.path.relpath(root, str(BASE))}")


def main():
    print(f"[prune] === SEL Prune {TODAY} ===")

    prune_drafts()
    flag_stale()
    clean_empty_dirs()

    total = sum(pruned.values())
    print(f"[prune] 汇总: draft归档={pruned['draft_archived']} "
          f"待审标记={pruned['stale_flagged']} 空目录删除={pruned['empty_dirs']} "
          f"总计={total}")

    # 更新状态
    status_path = Path("D:/1989n/stock_data/status/engineering_status.json")
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["pipeline"]["prune"] = {
            "status": "ok",
            "at": TODAY.isoformat(),
            "draft_archived": pruned["draft_archived"],
            "stale_flagged": pruned["stale_flagged"],
        }
        status["timestamp"] = datetime.now(CST).isoformat()
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    # 正常完成（无论有无修剪），避免 Win 计划任务误报失败
    sys.exit(0)


if __name__ == "__main__":
    import sys
    main()
