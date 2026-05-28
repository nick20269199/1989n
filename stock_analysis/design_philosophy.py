"""
design_philosophy.py — AI 设计哲学采集器

从上游追溯发现的高价值源中提取架构设计理念。

用法:
  python design_philosophy.py --list          # 列出待采集的设计哲学源
  python design_philosophy.py --digest        # 从已缓存源生成本地摘要
  python design_philosophy.py --status        # 采集进度
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

STOCK_DATA = Path("D:/1989n/stock_data")
KNOWLEDGE_DIR = STOCK_DATA / "knowledge"
ARCHIVE_DIR = STOCK_DATA / "douyin" / "archive"
PROSPECTOR_LOG = KNOWLEDGE_DIR / "prospector_log.json"
GAP_REGISTRY = KNOWLEDGE_DIR / "gap_registry.json"
PHILOSOPHY_DIR = KNOWLEDGE_DIR / "design_philosophy"
FINDINGS_DIR = KNOWLEDGE_DIR / "findings"

# 设计哲学重点关注: 从设计哲学缺口搜索词反推的源类型
DESIGN_SOURCES = [
    {"pattern": "Gbrain", "type": "tool", "philosopher": "Gbrain Team"},
    {"pattern": "DeepSeek", "type": "paper", "philosopher": "DeepSeek"},
    {"pattern": "Karpathy", "type": "person", "philosopher": "Andrej Karpathy"},
    {"pattern": "Gary Tan", "type": "person", "philosopher": "Gary Tan"},
]


def _load_log() -> list[dict]:
    if PROSPECTOR_LOG.exists():
        try:
            return json.loads(PROSPECTOR_LOG.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def list_sources():
    """列出待采集的设计哲学源。"""
    log = _load_log()
    design_findings = [
        f for f in log
        if f.get("gap_id") == "knowledge-ai-design-philosophy"
        and f.get("relevance", 0) >= 4
    ]

    print(f"设计哲学源 ({len(design_findings)} 条高价值发现):")
    print("=" * 60)
    for f in sorted(design_findings, key=lambda x: -x.get("relevance", 0)):
        ref_type = f.get("_ref_type", f.get("source", "?"))
        title = f.get("title", "?")[:60]
        creator = f.get("_creator", f.get("source", "?"))
        absorbed = "✓" if f.get("absorbed") else "○"
        print(f"  [{f['relevance']}★][{absorbed}] [{ref_type}] {title}")
        print(f"        来源: {creator}")
        si = f.get("_search_intent", {})
        if si.get("status") == "pending":
            print(f"        待搜索: {si.get('ref_name', '')[:60]}")


def digest():
    """从已有归档 + 发现日志中提取设计哲学片段。

    扫描抖音归档中涉及设计哲学的内容，
    提取引用原文、演讲核心论点、设计决策思路。
    """
    PHILOSOPHY_DIR.mkdir(parents=True, exist_ok=True)

    # 1. 从抖音归档扫描
    papers = []
    for fp in sorted(ARCHIVE_DIR.glob("*.json")):
        nickname = fp.stem
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        videos = data.get("videos", [])
        for v in videos:
            text = " ".join(filter(None, [v.get("desc", ""), v.get("chapter_content", "")]))
            # 设计哲学关键词检测
            if any(kw in text for kw in ["设计理念", "架构哲学", "design", "philosophy",
                                          "为什么这样设计", "架构思路", "设计决策",
                                          "trade-off", "取舍", "Karpathy", "Gbrain",
                                          "thinking", "mindset"]):
                papers.append({
                    "creator": nickname,
                    "title": v.get("desc", "")[:100],
                    "content": text[:500],
                    "url": f"https://www.douyin.com/video/{v.get('aweme_id', '')}",
                    "extracted_at": datetime.now().isoformat(),
                })

    # 2. 写设计哲学文件
    digest_file = PHILOSOPHY_DIR / "design_philosophy_digest.json"
    existing = []
    if digest_file.exists():
        try:
            existing = json.loads(digest_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 去重
    existing_urls = {e.get("url", "") for e in existing}
    new_papers = [p for p in papers if p["url"] not in existing_urls]

    all_papers = existing + new_papers
    digest_file.write_text(
        json.dumps(all_papers, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print(f"设计哲学摘要已更新")
    print(f"  已有: {len(existing)} 条")
    print(f"  新增: {len(new_papers)} 条 (从 {len(list(ARCHIVE_DIR.glob('*.json')))} 个归档)")
    print(f"  总计: {len(all_papers)} 条")
    print(f"  文件: {digest_file}")

    # 按创作者分组统计
    by_creator = {}
    for p in all_papers:
        by_creator.setdefault(p["creator"], 0)
        by_creator[p["creator"]] += 1
    if by_creator:
        print("\n创作者分布:")
        for c, n in sorted(by_creator.items(), key=lambda x: -x[1]):
            print(f"  {c}: {n} 条")

    return all_papers


def print_status():
    """采集进度。"""
    log = _load_log()
    design_findings = [f for f in log if f.get("gap_id") == "knowledge-ai-design-philosophy"]
    absorbed = sum(1 for f in design_findings if f.get("absorbed"))

    digest_file = PHILOSOPHY_DIR / "design_philosophy_digest.json"
    digested = 0
    if digest_file.exists():
        try:
            digested = len(json.loads(digest_file.read_text(encoding="utf-8")))
        except Exception:
            pass

    available_for_digest = sum(1 for f in design_findings if f.get("relevance", 0) >= 4)

    print("AI 设计哲学 — 采集进度")
    print("=" * 60)
    print(f"  追溯发现: {len(design_findings)} 条")
    print(f"  已吸收:   {absorbed} 条")
    print(f"  高价值可采集: {available_for_digest} 条")
    print(f"  已摘要:   {digested} 条")


def main():
    args = sys.argv[1:] if len(sys.argv) > 1 else ["status"]

    if args[0] == "--list":
        list_sources()
    elif args[0] == "--digest":
        digest()
    elif args[0] == "--status":
        print_status()
    else:
        print("用法: python design_philosophy.py [--list|--digest|--status]")


if __name__ == "__main__":
    main()
