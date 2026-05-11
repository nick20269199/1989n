"""
一次性索引存量数据：stock_data JSON 文件 + memory markdown 文件

用法:
  python index_all.py                # 全量索引
  python index_all.py --stock-only   # 仅索引 stock_data
  python index_all.py --memory-only  # 仅索引 memory
  python index_all.py --stats        # 仅显示统计
"""
import sys
from pathlib import Path
from datetime import datetime
from knowledge_db import (
    init_knowledge_db, index_json_file, index_memory_file,
    file_index_stats, knowledge_stats, STOCK_DATA, MEMORY_DIRS,
)


def index_all_stock_data():
    """索引 stock_data/ 下所有 JSON 文件"""
    json_files = sorted(STOCK_DATA.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    total = len(json_files)
    indexed = 0
    skipped = 0

    for i, f in enumerate(json_files):
        try:
            result = index_json_file(str(f))
            if result:
                indexed += 1
            else:
                skipped += 1
        except Exception as e:
            print(f"  ERROR: {f.name}: {e}")
            skipped += 1

        if (i + 1) % 20 == 0:
            print(f"  ... {i+1}/{total}")

    return indexed, skipped, total


def index_all_memory():
    """索引 memory 目录下所有 markdown 文件"""
    indexed = 0
    skipped = 0
    total = 0

    # Exclude raw/ directory (too verbose and low signal)
    for mem_dir in MEMORY_DIRS:
        if not mem_dir.exists():
            print(f"  SKIP: {mem_dir} not found")
            continue

        for md_file in mem_dir.rglob("*.md"):
            # Skip files in raw/ subdirectory
            if "raw" in md_file.parts:
                continue
            # Skip very large files (>500KB)
            if md_file.stat().st_size > 500_000:
                continue

            total += 1
            try:
                n = index_memory_file(str(md_file))
                indexed += n
            except Exception as e:
                print(f"  ERROR: {md_file.name}: {e}")
                skipped += 1

            if total % 30 == 0:
                print(f"  ... {total} memory files scanned")

    return indexed, skipped, total


def main():
    init_knowledge_db()

    stock_only = "--stock-only" in sys.argv
    memory_only = "--memory-only" in sys.argv
    stats_only = "--stats" in sys.argv

    if stats_only:
        print("\n=== 文件索引统计 ===")
        fs = file_index_stats()
        print(f"  总文件: {fs['total_files']}")
        for item in fs['by_type']:
            print(f"    {item['file_type']}: {item['n']}")
        print(f"  最后索引: {fs['last_indexed']}")

        print("\n=== 知识条目统计 ===")
        ks = knowledge_stats()
        print(f"  总条目: {ks['total_entries']}")
        for item in ks['by_topic']:
            print(f"    {item['topic']}: {item['n']}")
        return

    start = datetime.now()

    if not memory_only:
        print("\n=== 索引 stock_data JSON 文件 ===")
        i1, s1, t1 = index_all_stock_data()
        print(f"  完成: {i1} 索引, {s1} 跳过, 共 {t1} 文件")

    if not stock_only:
        print("\n=== 索引 memory markdown 文件 ===")
        i2, s2, t2 = index_all_memory()
        print(f"  完成: {i2} 条目, {s2} 跳过, 扫描 {t2} 文件")

    elapsed = (datetime.now() - start).total_seconds()

    # Final stats
    print(f"\n=== 索引完成 ({elapsed:.1f}s) ===")
    fs = file_index_stats()
    ks = knowledge_stats()
    print(f"  文件索引: {fs['total_files']} 条")
    print(f"  知识条目: {ks['total_entries']} 条")
    print(f"  下次更新: python index_all.py")


if __name__ == "__main__":
    main()
