#!/usr/bin/env python3
"""
SEL Evolve Read+Extract v1 — 扫描新内容源，提取结构化知识。
运行在中午休盘时段 (12:00 每日)。

扫描:
  1. stock_data/reading_notes/ — 读书笔记新文件
  2. stock_data/distillery/ — 蒸馏产出新文件
  3. inbox/ — 手机端投递的新想法

输出: stock_data/learning/pending_ingest.json — 待注入列表

用法:
  cd D:/1989n/stock_analysis && python sel_evolve_read.py
"""

import json
import os
from datetime import date, datetime, timezone, timedelta
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
LEARNING = STOCK_DATA / "learning"
PENDING_FILE = LEARNING / "pending_ingest.json"
INDEX_FILE = LEARNING / "ingest_index.json"
TODAY = date.today()
CST = timezone(timedelta(hours=8))

SCAN_DIRS = [
    ("reading_notes", STOCK_DATA / "reading_notes"),
    ("distillery", STOCK_DATA / "distillery"),
]

# 已摄入索引
ingest_index = {}
if INDEX_FILE.exists():
    try:
        ingest_index = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
    except Exception:
        ingest_index = {}


def _is_ingested(file_path: str) -> bool:
    """检查文件是否已被摄入"""
    return file_path in ingest_index


def _mark_ingested(file_path: str):
    ingest_index[file_path] = TODAY.isoformat()


def _extract_title(content: str, fpath: str) -> str:
    """从 frontmatter 或文件名提取标题"""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            for line in content[3:end].strip().split("\n"):
                if ":" in line:
                    k, _, v = line.partition(":")
                    if k.strip().lower() in ("title", "名称", "书名"):
                        return v.strip().strip("\"'")
    return Path(fpath).stem


def _extract_tags(content: str) -> list:
    """从 frontmatter 提取标签"""
    tags = []
    if content.startswith("---"):
        end = content.find("---", 3)
        if end > 0:
            for line in content[3:end].strip().split("\n"):
                if ":" in line:
                    k, _, v = line.partition(":")
                    key = k.strip().lower()
                    if key in ("tags", "keywords", "主题", "分类", "categories"):
                        vals = v.strip().strip("[]\"'").split(",")
                        tags.extend(t.strip().strip("\"'") for t in vals if t.strip())
    return tags


def main():
    pending = []

    for source_name, scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            print(f"[evolve-read] 扫描目录不存在: {scan_dir}")
            continue

        for root, dirs, files in os.walk(str(scan_dir)):
            for fname in files:
                if not fname.endswith((".md", ".txt", ".json")):
                    continue
                fpath = os.path.join(root, fname)
                if _is_ingested(fpath):
                    continue

                content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                title = _extract_title(content, fpath)
                tags = _extract_tags(content)

                stat = os.stat(fpath)
                entry = {
                    "source": source_name,
                    "file_path": fpath,
                    "title": title,
                    "tags": tags,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    "discovered": TODAY.isoformat(),
                }
                pending.append(entry)
                _mark_ingested(fpath)
                print(f"[evolve-read] 新: [{source_name}] {title}")

    # 写 pending_ingest.json
    LEARNING.mkdir(parents=True, exist_ok=True)
    if pending:
        existing = []
        if PENDING_FILE.exists():
            try:
                existing = json.loads(PENDING_FILE.read_text(encoding="utf-8"))
            except Exception:
                existing = []
        existing.extend(pending)
        PENDING_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    # 更新索引
    INDEX_FILE.write_text(json.dumps(ingest_index, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[evolve-read] 发现 {len(pending)} 条新内容, 总待注入: {len(pending)}")

    # 更新工程部状态
    status_path = Path("D:/1989n/stock_data/status/engineering_status.json")
    if status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["pipeline"]["evolve_read"] = {
            "status": "ok",
            "at": TODAY.isoformat(),
            "new_items": len(pending),
        }
        status["timestamp"] = datetime.now(CST).isoformat()
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
