#!/usr/bin/env python3
"""
SEL Connect v1 — 自动添加缺失的 [[wiki-links]]。
运行在 Maintain 之后 (09:10 每日)。

从 Lint scan 6（缺失连接）读数 → 往文件里加 [[交叉引用]]。
只加双向缺的，已有单向的不动。改前备份。

用法:
  cd D:/1989n/stock_analysis && python sel_connect.py
"""

import json
import re
import shutil
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

BASE = Path("D:/1989n/.claude/memory")
DAILY_DIR = BASE / "daily"
BACKUP_DIR = Path("D:/1989n/.claude/backups")
TODAY = date.today()
CST = timezone(timedelta(hours=8))

linked = 0
errors = 0


def _backup(fp: Path):
    """改前备份到 ~/.claude/backups/YYYY-MM-DD/"""
    bak_dir = BACKUP_DIR / TODAY.isoformat()
    bak_dir.mkdir(parents=True, exist_ok=True)
    rel = str(fp.relative_to(BASE)).replace("\\", "_").replace("/", "_")
    shutil.copy2(fp, bak_dir / f"{rel}.bak")


def _update_status(linked_count: int, errors_count: int):
    """发布连接状态到工程部状态文件。"""
    status_path = Path("D:/1989n/stock_data/status/engineering_status.json")
    if not status_path.exists():
        return
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["pipeline"]["connect"] = {
        "status": "ok",
        "at": TODAY.isoformat(),
        "links_added": linked_count,
        "errors": errors_count,
    }
    status["timestamp"] = datetime.now(CST).isoformat()
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _add_link(content: str, stem_a: str, stem_b: str) -> str:
    """在 content 中找一个合适的位置添加 [[stem_b]] 链接。
    优先加在 ## See Also / ## 相关 / ## 参考 小节里，否则加在末尾。"""
    see_also_patterns = [
        r'^##\s*(See Also|相关|参考|关联|交叉引用)',
    ]
    lines = content.split("\n")
    inserted = False

    for i, line in enumerate(lines):
        for pat in see_also_patterns:
            if re.match(pat, line, re.IGNORECASE):
                # 在 this section, after blank line if any
                insert_at = i + 1
                while insert_at < len(lines) and lines[insert_at].strip() == "":
                    insert_at += 1
                indent = " " if not lines[insert_at].startswith("-") else ""
                lines.insert(insert_at, f"- [[{stem_b}]]")
                inserted = True
                break
        if inserted:
            break

    if not inserted:
        lines.append("")
        lines.append("## See Also")
        lines.append("")
        lines.append(f"- [[{stem_b}]]")

    return "\n".join(lines)


def main():
    global linked, errors

    # 1) 读今日 lint 报告
    lint_file = DAILY_DIR / f"{TODAY}_lint.md"
    if not lint_file.exists():
        print("[connect] 今日无 lint 报告")
        return

    report = lint_file.read_text(encoding="utf-8")

    # 2) 解析 scan 6 的缺失连接
    pairs = []
    lines = report.split("\n")
    in_scan6 = False
    for line in lines:
        if "## 6. 缺失连接" in line:
            in_scan6 = True
            continue
        if in_scan6 and line.startswith("## "):
            in_scan6 = False
            continue
        if in_scan6 and "↔" in line:
            parts = line.split("↔")
            if len(parts) == 2:
                a = parts[0].strip().lstrip("- [").split("]")[-1].strip("** ")
                b = parts[1].strip().rstrip("** ").strip()
                pairs.append((a, b))

    if not pairs:
        print("[connect] 无缺失连接需要修复")
        _update_status(0, 0)
        return

    print(f"[connect] 发现 {len(pairs)} 对缺失连接")

    # 3) 遍历每一对，加链接
    for fname_a, fname_b in pairs:
        # 找文件
        candidates_a = list(BASE.rglob(fname_a)) + list(BASE.rglob(f"{fname_a}*"))
        candidates_b = list(BASE.rglob(fname_b)) + list(BASE.rglob(f"{fname_b}*"))

        if not candidates_a:
            print(f"[connect] 找不到文件: {fname_a}")
            errors += 1
            continue
        if not candidates_b:
            print(f"[connect] 找不到文件: {fname_b}")
            errors += 1
            continue

        fp_a = candidates_a[0]
        fp_b = candidates_b[0]
        stem_a = fp_a.stem
        stem_b = fp_b.stem

        # 读内容
        text_a = fp_a.read_text(encoding="utf-8", errors="ignore")
        text_b = fp_b.read_text(encoding="utf-8", errors="ignore")

        # 检查是否已互引
        a_refs_b = stem_b.lower() in text_a.lower()
        b_refs_a = stem_a.lower() in text_b.lower()

        changed = False

        if not a_refs_b:
            _backup(fp_a)
            new_text = _add_link(text_a, stem_a, stem_b)
            fp_a.write_text(new_text, encoding="utf-8")
            changed = True
            linked += 1

        if not b_refs_a:
            _backup(fp_b)
            new_text = _add_link(text_b, stem_b, stem_a)
            fp_b.write_text(new_text, encoding="utf-8")
            changed = True
            linked += 1

        if changed:
            print(f"[connect] +链接: {fname_a} ↔ {fname_b}")

    # 4) 更新工程部状态
    _update_status(linked, errors)

    print(f"[connect] 完成: 添加 {linked} 个链接, {errors} 个错误")


if __name__ == "__main__":
    main()
