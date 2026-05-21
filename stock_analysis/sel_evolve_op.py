#!/usr/bin/env python3
"""
SEL Evolve Operationalize+Inject v1 — 将待注入知识写入知识库。
运行在 Evolve Read 之后 (12:15 每日)。

读取 pending_ingest.json → 为每条内容创建 knowledge/ 文件 → 更新索引。

用法:
  cd D:/1989n/stock_analysis && python sel_evolve_op.py
"""

import json
import os
import re
import shutil
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

BASE = Path("D:/1989n/.claude/memory")
KNOWLEDGE = BASE / "knowledge"
STOCK_DATA = Path("D:/1989n/stock_data")
LEARNING = STOCK_DATA / "learning"
PENDING_FILE = LEARNING / "pending_ingest.json"
READING_INDEX = STOCK_DATA / "status" / "reading_index.json"
TODAY = date.today()
CST = timezone(timedelta(hours=8))

injected = 0
errors = 0


def _path_to_knowledge(entry: dict) -> str:
    """根据 source 和 tags 决定 knowledge/ 下的目标路径"""
    source = entry.get("source", "unknown")
    tags = entry.get("tags", [])

    # 注意: KNOWLEDGE = BASE/knowledge, 所以这里只返回子目录名, 不含 knowledge/
    if source == "reading_notes":
        return "economics" if any(
            t in str(entry) for t in ["经济学", "经济", "市场", "投资", "交易"]) else "general"
    elif source == "distillery":
        return "trading"
    else:
        return "general"


def _slug(title: str) -> str:
    """中文标题转短横线式 slug"""
    s = re.sub(r"[^\w一-鿿\s-]", "", title)
    s = re.sub(r"\s+", "-", s)
    s = s.lower()[:60]
    return s or "untitled"


def _inject_file(entry: dict) -> bool:
    """为一条待注入内容创建 knowledge/ 文件"""
    try:
        subdir = _path_to_knowledge(entry)
        target_dir = KNOWLEDGE / subdir
        target_dir.mkdir(parents=True, exist_ok=True)

        slug = _slug(entry.get("title", "untitled"))
        target_path = target_dir / f"{slug}.md"

        if target_path.exists():
            print(f"[evolve-op] 跳过(已存在): {target_path.name}")
            return True

        # 读取原文
        src_path = entry.get("file_path", "")
        src_content = ""
        if src_path and Path(src_path).exists():
            src_content = Path(src_path).read_text(encoding="utf-8", errors="ignore")
        elif src_path:
            print(f"[evolve-op] 源文件不存在: {src_path}")
            return False

        # 提取前 200 字作为摘要
        plain = re.sub(r"^---.*?---", "", src_content, flags=re.DOTALL).strip()
        summary = plain[:200].replace("\n", " ").strip()

        # 生成 knowledge 文件
        fm = {
            "title": entry.get("title", "untitled"),
            "source": entry.get("source", "unknown"),
            "tags": entry.get("tags", []),
            "created": TODAY.isoformat(),
            "last_reviewed": TODAY.isoformat(),
            "status": "active",
        }
        fm_lines = "\n".join(f"{k}: {v if not isinstance(v, list) else ', '.join(v)}"
                             for k, v in fm.items() if v)
        content = f"---\n{fm_lines}\n---\n\n# {entry['title']}\n\n{summary}\n"
        if len(plain) > 200:
            content += f"\n---\n\n完整内容见: `{src_path}`\n"

        target_path.write_text(content, encoding="utf-8")
        print(f"[evolve-op] 注入: {subdir}/{target_path.name}")
        return True

    except Exception as e:
        print(f"[evolve-op] 错误: {entry.get('title', '?')}: {e}")
        return False


def main():
    global injected, errors

    if not PENDING_FILE.exists():
        print("[evolve-op] pending_ingest.json 不存在，无待注入内容")
        return

    pending = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
    if not pending:
        print("[evolve-op] 待注入列表为空")
        return

    print(f"[evolve-op] 待注入: {len(pending)} 条")

    # 注入
    remaining = []
    for entry in pending:
        if _inject_file(entry):
            injected += 1
        else:
            errors += 1
            remaining.append(entry)

    # 写回未成功的
    if remaining:
        PENDING_FILE.write_text(json.dumps(remaining, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[evolve-op] {len(remaining)} 条未成功，保留在 pending_ingest.json")
    else:
        PENDING_FILE.write_text("[]\n", encoding="utf-8")

    # 更新 reading_index.json
    if READING_INDEX.exists():
        try:
            idx = json.loads(READING_INDEX.read_text(encoding="utf-8"))
            idx["last_evolve_inject"] = TODAY.isoformat()
            idx["total_injected"] = idx.get("total_injected", 0) + injected
            READING_INDEX.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # 更新工程部状态
    status_path = Path("D:/1989n/stock_data/status/engineering_status.json")
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["pipeline"]["evolve_op"] = {
            "status": "ok",
            "at": TODAY.isoformat(),
            "injected": injected,
            "errors": errors,
        }
        status["timestamp"] = datetime.now(CST).isoformat()
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[evolve-op] 完成: 注入 {injected}, 错误 {errors}")


if __name__ == "__main__":
    main()
