#!/usr/bin/env python3
"""
SEL Maintain v1 — 自动修复 Lint 发现的常见问题。
在 Digest 完成后运行（09:05 每日）。

自动修复:
  1. 幽灵引用 → 调用 fix_ghost_refs.py
  2. frontmatter 缺少 last_reviewed → 补充
  3. 报告修复结果

用法:
  cd D:/1989n/stock_analysis && python sel_maintain.py
"""

import os
import re
import subprocess
import sys
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

BASE = Path("D:/1989n/.claude/memory")
TODAY = date.today()
CST = timezone(timedelta(hours=8))

fixed = {"frontmatter": 0, "ghost_refs": 0}


def fix_frontmatter():
    """为没有 last_reviewed 的 knowledge 文件补充该字段。"""
    for root, dirs, files in os.walk(str(BASE / "knowledge")):
        for fname in files:
            if not fname.endswith(".md"):
                continue
            fp = Path(root) / fname
            content = fp.read_text(encoding="utf-8", errors="ignore")
            if "last_reviewed" in content[:800]:
                continue

            # 检查是否有 frontmatter
            m = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
            if not m:
                continue  # 无 frontmatter，跳过

            fm_text = m.group(1)
            today_str = TODAY.isoformat()
            new_fm = fm_text + f"\nlast_reviewed: {today_str}"
            new_content = content.replace(fm_text, new_fm, 1)

            fp.write_text(new_content, encoding="utf-8")
            fixed["frontmatter"] += 1
            rel = str(fp.relative_to(BASE))
            print(f"[maintain] 补充 last_reviewed → {rel}")


def fix_ghost_refs():
    """调用 fix_ghost_refs.py 修复幽灵引用。"""
    fix_script = Path(__file__).parent / "fix_ghost_refs.py"
    if not fix_script.exists():
        print("[maintain] fix_ghost_refs.py 不存在，跳过")
        return
    result = subprocess.run(
        [sys.executable, str(fix_script)],
        capture_output=True, text=True, timeout=60,
    )
    if result.returncode == 0:
        fixed["ghost_refs"] = 1
        print("[maintain] 幽灵引用修复完成")
    else:
        print(f"[maintain] 幽灵引用修复失败: {result.stderr[:200]}")


def main():
    print(f"[maintain] === SEL Maintain {TODAY} ===")
    fix_frontmatter()
    fix_ghost_refs()

    total = sum(fixed.values())
    print(f"[maintain] 修复汇总: frontmatter={fixed['frontmatter']} "
          f"ghost_refs={fixed['ghost_refs']} 总计={total}")

    # 更新工程部状态
    status_file = Path("D:/1989n/stock_data/status/engineering_status.json")
    if status_file.exists():
        import json
        status = json.loads(status_file.read_text(encoding="utf-8"))
        status["pipeline"]["maintain"] = {
            "status": "ok",
            "at": TODAY.isoformat(),
            "fixed_frontmatter": fixed["frontmatter"],
            "fixed_ghost_refs": fixed["ghost_refs"],
        }
        status["timestamp"] = datetime.now(CST).isoformat()
        status_file.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    sys.exit(0 if total == 0 else 1)


if __name__ == "__main__":
    main()
