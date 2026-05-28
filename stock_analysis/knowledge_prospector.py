"""
knowledge_prospector.py — 知识勘探仪

主动搜索：根据知识缺口清单，去抖音/Web/GitHub 找有价值的内容。
核心逻辑不是"监控已知博主"，而是"带着需求清单去挖矿"。

工作流:
  1. 从 gap_registry 加载 open 缺口
  2. 对每个缺口，用其 search_queries 搜索多个源
  3. 评估每个发现的关联度
  4. 记录结果 → 供 absorber 读取

用法:
  python knowledge_prospector.py --plan          # 查看搜索计划
  python knowledge_prospector.py --run douyin    # 搜索抖音
  python knowledge_prospector.py --run all       # 全源搜索
  python knowledge_prospector.py --status        # 搜索状态
"""
import json
import logging
import os
import sys
import time
import re
import requests
from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from typing import Optional

load_dotenv(Path(__file__).parent / ".env")

logger = logging.getLogger("knowledge_prospector")

DATA_DIR = Path("D:/1989n/stock_data/knowledge")
GAP_REGISTRY_FILE = DATA_DIR / "gap_registry.json"
PROSPECTOR_LOG = DATA_DIR / "prospector_log.json"
FINDINGS_DIR = DATA_DIR / "findings"

# Douyin cookie + UA (复用以有登录态的 session)
DOUYIN_COOKIES = Path("D:/1989n/stock_data/douyin/cookies.json")
DOUYIN_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

FINDINGS_DIR.mkdir(parents=True, exist_ok=True)

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


# ── 缺口加载 ──


def _load_gaps(incremental_since: str = None) -> list[dict]:
    """加载所有 open/investigating 缺口。

    Args:
        incremental_since: ISO 时间戳，只返回在此之后创建的缺口。None=全部。
    """
    if not GAP_REGISTRY_FILE.exists():
        logger.error("缺口清单不存在: %s", GAP_REGISTRY_FILE)
        return []
    try:
        all_gaps = json.loads(GAP_REGISTRY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        logger.error("缺口文件损坏: %s", e)
        return []
    gaps = [g for g in all_gaps if g.get("status") in ("open", "investigating")]
    if incremental_since:
        gaps = [g for g in gaps if g.get("created_at", "2000-01-01") > incremental_since]
    return gaps


def _update_gap_status(gap_id: str, status: str):
    """更新缺口状态。"""
    try:
        gaps = json.loads(GAP_REGISTRY_FILE.read_text(encoding="utf-8"))
        for g in gaps:
            if g["gap_id"] == gap_id:
                g["status"] = status
                g["updated_at"] = datetime.now().isoformat()
                break
        GAP_REGISTRY_FILE.write_text(
            json.dumps(gaps, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("更新缺口状态失败: %s", e)


def _maybe_create_vv_gap(original_gap: dict, vv_findings: list[dict]):
    """vv_db 批量发现 >10 条时，自动创建聚焦子缺口。"""
    if not vv_findings:
        return

    # 统计博主覆盖
    vv_ids = set(f.get("vv_id", "") for f in vv_findings if f.get("vv_id"))
    title = original_gap.get("title", "")

    new_gap_id = f"vv-batch-{original_gap.get('gap_id', 'unknown')}-{int(time.time())}"
    new_gap = {
        "gap_id": new_gap_id,
        "title": f"大V线索: {title[:50]}",
        "description": (
            f"从 vv_db 转录中发现 {len(vv_findings)} 条相关讨论 "
            f"(覆盖 {len(vv_ids)} 位博主)，源自缺口 [{original_gap.get('gap_id','')}]"
        ),
        "priority": "P1" if len(vv_ids) >= 3 else "P2",
        "domain": original_gap.get("domain", "open-exploration"),
        "search_queries": original_gap.get("search_queries", [])[:3],
        "target_sources": ["vv_db", "web"],
        "status": "open",
        "parent_gap": original_gap.get("gap_id", ""),
    }

    try:
        gaps_file = GAP_REGISTRY_FILE.read_text(encoding="utf-8")
        all_gaps = json.loads(gaps_file)
        if any(g["gap_id"] == new_gap_id for g in all_gaps):
            logger.info("    vv 子缺口已存在: %s", new_gap_id)
            return
        all_gaps.append(new_gap)
        GAP_REGISTRY_FILE.write_text(json.dumps(all_gaps, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("    创建 vv 子缺口 [%s]: %d 条发现, %d 位博主", new_gap_id, len(vv_findings), len(vv_ids))
    except Exception as e:
        logger.warning("创建 vv 子缺口失败: %s", e)


# ── 发现记录 ──


def _load_log() -> list[dict]:
    if PROSPECTOR_LOG.exists():
        try:
            return json.loads(PROSPECTOR_LOG.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_log(log: list[dict]):
    PROSPECTOR_LOG.write_text(
        json.dumps(log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _record_finding(gap_id: str, source: str, title: str, url: str,
                     relevance: int, summary: str, detail: dict = None):
    """记录一条勘探发现。"""
    log = _load_log()
    finding = {
        "finding_id": f"{gap_id}_{int(time.time())}",
        "gap_id": gap_id,
        "source": source,
        "title": title,
        "url": url,
        "relevance": relevance,  # 1-5
        "summary": summary[:500],
        "detail": detail or {},
        "discovered_at": datetime.now().isoformat(),
        "absorbed": False,
    }
    log.append(finding)
    _save_log(log)
    return finding


def _save_detailed_finding(gap_id: str, source: str, title: str, raw_data: dict):
    """保存详细发现到文件。"""
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title)[:60]
    fname = f"{gap_id}_{source}_{int(time.time())}.json"
    fpath = FINDINGS_DIR / fname
    fpath.write_text(
        json.dumps({
            "gap_id": gap_id,
            "source": source,
            "title": title,
            "raw_data": raw_data,
            "discovered_at": datetime.now().isoformat(),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return fpath


# ── 搜索计划 ──


def generate_search_plan() -> list[dict]:
    """生成搜索计划：对每个 open 缺口，创建搜索任务。"""
    gaps = _load_gaps()
    tasks = []
    for g in sorted(gaps, key=lambda x: PRIORITY_ORDER.get(x.get("priority", "P3"), 99)):
        for i, query in enumerate(g.get("search_queries", [])[:3]):
            for source in g.get("target_sources", ["web"]):
                tasks.append({
                    "gap_id": g["gap_id"],
                    "priority": g.get("priority", "P3"),
                    "title": g["title"],
                    "query": query,
                    "target_source": source,
                    "task_id": f"{g['gap_id']}_{source}_{i}",
                })
    return tasks


def print_search_plan():
    """打印搜索计划。"""
    tasks = generate_search_plan()
    print(f"搜索计划 ({len(tasks)} 个任务):")
    print("=" * 80)
    for t in tasks:
        print(f"  [{t['priority']}] {t['title']}")
        print(f"      搜索: \"{t['query']}\" → {t['target_source']}")
    print()
    print(f"共 {len(tasks)} 个搜索任务, 覆盖 {len(set(t['gap_id'] for t in tasks))} 个缺口")


# ── 抖音搜索 — 搜索已有归档 + 新发现意图 ──

DOUYIN_ARCHIVE_DIR = Path("D:/1989n/stock_data/douyin/archive")


def search_douyin_topic(query: str, max_results: int = 10) -> list[dict]:
    """搜索抖音 — 两个途径:
    1. 在已有归档中搜索匹配内容 (可靠)
    2. 记录 Web 搜索意图 (需要 harness 执行 WebSearch)

    抖音搜索页反爬严重 (captcha)，不直接请求搜索页。
    """
    results = []

    # 途径1: 在已有归档中搜索
    archive_hits = _search_douyin_archives(query)
    for hit in archive_hits[:max_results]:
        results.append(hit)
        logger.info("  归档命中: %s — %s", hit["source"], hit["title"][:60])

    # 途径2: 记录 Web 搜索意图
    _record_finding(
        gap_id=f"search_{query[:20]}",
        source="douyin_search_intent",
        title=f"抖音搜索意图: {query}",
        url="",
        relevance=3,
        summary=f"在 {len(archive_hits)} 个归档命中 + 需执行 WebSearch 发现新内容",
        detail={"query": query, "archive_hits": len(archive_hits), "requires_websearch": True},
    )

    return results


def _search_douyin_archives(query: str) -> list[dict]:
    """在已有抖音归档中搜索匹配内容。"""
    if not DOUYIN_ARCHIVE_DIR.exists():
        return []

    query_l = query.lower()
    query_words = set(query_l.split())

    hits = []
    for fp in sorted(DOUYIN_ARCHIVE_DIR.glob("*.json")):
        if fp.name == "synthesis_20260527.md":
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        nickname = data.get("nickname", fp.stem)
        for v in data.get("videos", []):
            search_text = (
                (v.get("desc", "") + " " +
                 v.get("chapter_content", "") + " " +
                 v.get("caption", "") + " " +
                 str(v.get("stats", {}))
                ).lower()
            )

            # 计算匹配度
            word_hits = sum(1 for w in query_words if len(w) > 3 and w in search_text)
            if word_hits == 0:
                continue

            # 生成章节摘要
            chapter_list = v.get("chapter_list", [])
            chapter_summary = " | ".join(
                ch.get("detail", "") for ch in chapter_list[:5] if ch.get("detail")
            )[:300]

            score = word_hits / max(len(query_words), 1)
            hits.append({
                "title": (v.get("desc", "") or "")[:150],
                "url": f"https://www.douyin.com/video/{v.get('aweme_id', '')}",
                "source": f"archive_{nickname}",
                "query": query,
                "match_score": round(score, 2),
                "chapter_content": chapter_summary,
                "stats": v.get("stats", {}),
            })

    hits.sort(key=lambda x: x["match_score"], reverse=True)
    return hits


# ── 评估发现 ──


def _build_tfidf(gap_texts: list[str]) -> tuple:
    """为缺口文本构建 TF-IDF 向量化器，返回 (vectorizer, tfidf_matrix)。"""
    from sklearn.feature_extraction.text import TfidfVectorizer
    vectorizer = TfidfVectorizer(
        analyzer="char_wb",
        ngram_range=(2, 4),
        max_features=5000,
        lowercase=True,
        strip_accents="unicode",
    )
    if not gap_texts:
        gap_texts = [""]
    tfidf_matrix = vectorizer.fit_transform(gap_texts)
    return vectorizer, tfidf_matrix


def evaluate_finding(result: dict, gap: dict) -> dict:
    """评估一条发现对缺口的关联度 — 基于 TF-IDF 余弦相似度。

    返回:
      relevance: 1(弱相关)-5(强相关)
      reason: 评估理由
    """
    title = (result.get("title", "") or "").strip()
    desc = (result.get("description", "") or "").strip()
    finding_text = title + " " + desc

    if not finding_text.strip():
        return {"relevance": 1, "reason": "空内容", "similarity": 0.0, "keyword_hits": 0}

    # 缺口文本语料：title + description + search_queries
    gap_corpus = [
        gap.get("title", ""),
        gap.get("description", ""),
        " ".join(gap.get("search_queries", [])),
    ]
    gap_corpus = [t for t in gap_corpus if t.strip()]

    # TF-IDF 向量化 + 余弦相似度
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        all_texts = gap_corpus + [finding_text]
        vectorizer = TfidfVectorizer(
            analyzer="char_wb", ngram_range=(2, 4),
            max_features=5000, lowercase=True, strip_accents="unicode",
        )
        tfidf = vectorizer.fit_transform(all_texts)
        gap_vec = np.asarray(tfidf[:-1].mean(axis=0))
        finding_vec = tfidf[-1]
        sim = float(cosine_similarity(gap_vec, finding_vec)[0, 0])
    except Exception:
        sim = 0.0

    # 关键词命中（保底）
    gap_keywords = gap.get("title", "").lower().split()
    text_lower = finding_text.lower()
    hits = sum(1 for kw in gap_keywords if len(kw) > 2 and kw in text_lower)

    # 综合评分：相似度 0-1 → relevance 1-5
    sim_score = min(int(sim * 8) + 1, 5)
    hit_bonus = 1 if hits >= 3 else (0.5 if hits >= 1 else 0)

    # 来源加分
    source_bonus = 0
    source = result.get("source", "")
    if "douyin" in source and sim > 0.15:
        source_bonus = 1
    if "github" in source:
        stars = result.get("stars", 0)
        if stars > 1000:
            source_bonus = 2
        elif stars > 100:
            source_bonus = 1
    if "vv_" in source:
        source_bonus = max(source_bonus, 1)
    if source in ("arxiv_api", "semantic_scholar_api"):
        source_bonus = max(source_bonus, 1)

    raw_relevance = min(sim_score + int(hit_bonus) + source_bonus, 5)
    relevance = max(raw_relevance, 1)

    if relevance >= 4:
        reason = "强关联: TF-IDF 高相似度"
    elif relevance >= 3:
        reason = "中关联: TF-IDF 部分匹配"
    elif relevance >= 2:
        reason = "弱关联: 少量匹配"
    else:
        reason = "低关联: 基本不匹配"

    return {
        "relevance": relevance,
        "reason": reason,
        "similarity": round(sim, 4),
        "keyword_hits": hits,
    }


def filter_findings(findings: list[dict], min_relevance: int = 3) -> list[dict]:
    """过滤低质量发现。"""
    return [f for f in findings if f.get("_evaluation", {}).get("relevance", 0) >= min_relevance]


# ── 创作者发现 — 从归档命中自动发现新博主 ──


def discover_creators_from_archives(gap_queries: list[str] = None) -> list[dict]:
    """扫描抖音归档，找出尚未纳入监控但有价值内容的创作者。

    流程:
      1. 遍历所有归档 JSON，提取 distinct nickname + sec_uid
      2. 与 creators.json 比对，排除已有博主
      3. 对新博主，统计其视频命中缺口查询的关键词
      4. 为每位新博主生成 creators.json 配置项（含 high_value_keywords）

    Args:
        gap_queries: 缺口查询词列表，用于评估匹配度。None 时用 gap_registry 的 search_queries

    Returns:
        新发现的博主配置列表，每条含 {label, nickname, sec_uid, high_value_keywords, matched_gaps, score}
    """
    CREATORS_FILE = DOUYIN_ARCHIVE_DIR.parent / "creators.json"

    # 1. 加载已有的 creators.json
    existing = set()
    if CREATORS_FILE.exists():
        raw = json.loads(CREATORS_FILE.read_text(encoding="utf-8"))
        for _cat, members in raw.items():
            if _cat.startswith("_"):
                continue
            if isinstance(members, dict):
                existing.update(members.keys())

    # 2. 收集缺口查询词
    if not gap_queries:
        gaps = _load_gaps()
        gap_queries = list(set(
            q for g in gaps for q in g.get("search_queries", [])
        ))

    query_words = set()
    for q in gap_queries:
        query_words.update(w.lower() for w in q.split() if len(w) > 2)

    # 3. 遍历归档，统计创作者
    creator_hits = {}  # nickname -> {sec_uid, hit_count, matched_queries, videos}
    for fp in sorted(DOUYIN_ARCHIVE_DIR.glob("*.json")):
        if fp.name == "synthesis_20260527.md":
            continue
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue

        nickname = data.get("nickname", fp.stem)
        sec_uid = data.get("sec_uid", "")

        if nickname in existing:
            continue
        if nickname not in creator_hits:
            creator_hits[nickname] = {
                "sec_uid": sec_uid,
                "hit_count": 0,
                "matched_words": set(),
                "matched_queries": set(),
                "video_count": len(data.get("videos", [])),
            }

        for v in data.get("videos", []):
            search_text = (
                v.get("desc", "") + " " +
                v.get("chapter_content", "") + " " +
                v.get("caption", "")
            ).lower()

            for w in query_words:
                if w in search_text:
                    creator_hits[nickname]["matched_words"].add(w)
                    creator_hits[nickname]["hit_count"] += 1

            for q in gap_queries:
                if q.lower() in search_text:
                    creator_hits[nickname]["matched_queries"].add(q)

    # 4. 生成配置
    discoveries = []
    for nickname, info in sorted(creator_hits.items(), key=lambda x: -x[1]["hit_count"]):
        if info["hit_count"] < 2 or len(info["matched_words"]) < 2:
            continue
        keywords = sorted(info["matched_words"])[:15]
        discoveries.append({
            "label": nickname,
            "nickname": nickname,
            "sec_uid": info["sec_uid"],
            "high_value_keywords": keywords,
            "matched_gaps": sorted(info["matched_queries"])[:10],
            "score": round(info["hit_count"] / max(info["video_count"], 1), 2),
            "video_count": info["video_count"],
        })

    return discoveries


def print_creator_discoveries(discoveries: list[dict]):
    """打印新发现的博主。"""
    if not discoveries:
        print("无新发现的博主。")
        return
    print(f"\n新发现 {len(discoveries)} 位潜在博主:")
    print("=" * 70)
    for d in discoveries:
        print(f"  {d['nickname']}")
        print(f"    sec_uid: {d['sec_uid'][:30]}...")
        print(f"    匹配度: {d['score']} ({d['video_count']} 视频, {len(d['matched_gaps'])} 缺口匹配)")
        if d.get("high_value_keywords"):
            print(f"    关键词: {', '.join(d['high_value_keywords'][:8])}")
        print()


# ── 主勘探流程 ──


def run_prospecting(target_source: str = "all", dry_run: bool = False,
                    incremental_since: str = None) -> dict:
    """执行一次全量勘探。

    Args:
        target_source: "all" / "douyin" / "web" / "github"
        dry_run: 只打印计划，不执行搜索
        incremental_since: ISO 时间戳，只搜索此时间后创建的缺口

    Returns:
        统计字典
    """
    gaps = _load_gaps(incremental_since=incremental_since)
    if not gaps:
        logger.info("无开放缺口，跳过勘探")
        return {"gaps_checked": 0, "searches_done": 0, "findings": 0}

    logger.info("开始知识勘探: %d 个开放缺口, 目标=%s", len(gaps), target_source)
    total_searches = 0
    total_findings = 0
    gap_findings = {}

    for gap in gaps:
        gap_id = gap["gap_id"]
        queries = gap.get("search_queries", [])[:3]
        sources = gap.get("target_sources", [])

        if target_source != "all":
            if target_source == "vv_db":
                sources = ["vv_db"]  # vv_db 单独搜索时只搜转录
            else:
                sources = [s for s in sources if s == target_source]
        elif "vv_db" not in sources:
            sources.append("vv_db")  # 全量勘探自动含大V转录搜索
        if "arxiv" not in sources and target_source == "all":
            sources.append("arxiv")  # 全量勘探自动含论文搜索
        if "semantic_scholar" not in sources and target_source == "all":
            sources.append("semantic_scholar")  # 全量勘探自动含 Semantic Scholar
        if not queries or not sources:
            continue

        gap_findings[gap_id] = []
        logger.info("  ── 勘探缺口: %s [%s]", gap["title"], gap_id)

        for query in queries:
            for source in sources:
                logger.info("    搜索: \"%s\" → %s", query, source)
                total_searches += 1

                if dry_run:
                    continue

                findings = _search_source(source, query, gap)
                for f in findings:
                    evaluation = evaluate_finding(f, gap)
                    f["_evaluation"] = evaluation
                    gap_findings[gap_id].append(f)

                    if evaluation["relevance"] >= 3:
                        total_findings += 1
                        _record_finding(
                            gap_id=gap_id,
                            source=source,
                            title=f.get("title", "?"),
                            url=f.get("url", ""),
                            relevance=evaluation["relevance"],
                            summary=f"{evaluation['reason']}: {f.get('title', '?')}",
                            detail={"query": query, "evaluation": evaluation},
                        )
                        logger.info("      → 发现 [rel=%d]: %s", evaluation["relevance"], f.get("title", "?")[:80])

                # 搜索间隔
                if not dry_run and target_source == "all":
                    time.sleep(1)

        # 更新缺口状态：如果有高价值发现
        high_value = sum(1 for f in gap_findings[gap_id]
                         if f.get("_evaluation", {}).get("relevance", 0) >= 4)
        if high_value >= 2:
            _update_gap_status(gap_id, "investigating")
            logger.info("    缺口 %s → 状态更新为 investigating (高价值发现 %d 条)", gap_id, high_value)

        # vv_db 批量发现：转录命中>10条时自动创建子缺口
        vv_findings = [f for f in gap_findings[gap_id]
                       if f.get("source", "").startswith("vv_")
                       and f.get("_evaluation", {}).get("relevance", 0) >= 3]
        if len(vv_findings) > 10:
            _maybe_create_vv_gap(gap, vv_findings)

    summary = {
        "target_source": target_source,
        "dry_run": dry_run,
        "gaps_checked": len(gaps),
        "searches_done": total_searches,
        "findings": total_findings,
        "timestamp": datetime.now().isoformat(),
    }
    logger.info("勘探完成: %d 次搜索, 发现 %d 条有价值内容", total_searches, total_findings)
    return summary


def _search_source(source: str, query: str, gap: dict) -> list[dict]:
    """在指定源上搜索。"""
    if source == "douyin":
        return search_douyin_topic(query, max_results=10)
    elif source == "web":
        return _search_web(query, gap)
    elif source == "github":
        return _search_github(query, gap)
    elif source == "vv_db":
        return _search_vv_db(query, gap)
    elif source == "arxiv":
        return _search_arxiv(query, gap)
    elif source == "semantic_scholar":
        return _search_semantic_scholar(query, gap)
    return []


def _search_arxiv(query: str, gap: dict, max_results: int = 10) -> list[dict]:
    """搜索 arXiv 论文数据库。"""
    import xml.etree.ElementTree as ET
    results = []
    try:
        logger.info("    arxiv 搜索: arXiv API — \"%s\"", query)
        r = requests.get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "start": "0",
                "max_results": str(max_results),
                "sortBy": "relevance",
                "sortOrder": "descending",
            },
            headers={"User-Agent": "knowledge-prospector/1.0"},
            timeout=30,
        )
        r.raise_for_status()

        ns = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}
        root = ET.fromstring(r.text)

        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).replace("\n", " ").strip()
            summary = entry.findtext("atom:summary", "", ns).replace("\n", " ").strip()
            paper_id = entry.findtext("atom:id", "", ns).strip()
            published = entry.findtext("atom:published", "", ns)[:10]
            authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
            author_str = ", ".join(authors[:3])
            if len(authors) > 3:
                author_str += " et al."
            category_tag = entry.find("arxiv:primary_category", ns)
            category = category_tag.attrib.get("term", "") if category_tag is not None else ""

            results.append({
                "title": title[:200],
                "url": paper_id,
                "description": summary[:300],
                "source": "arxiv_api",
                "authors": author_str,
                "published": published,
                "category": category,
            })

        logger.info("    arxiv 搜索完成: %d 篇论文", len(results))
        for r2 in results:
            evaluation = evaluate_finding(r2, gap)
            r2["_evaluation"] = evaluation
            if evaluation["relevance"] >= 3:
                _record_finding(
                    gap_id=gap["gap_id"],
                    source="arxiv_api",
                    title=r2["title"],
                    url=r2["url"],
                    relevance=evaluation["relevance"],
                    summary=f"{evaluation['reason']}: {r2['title'][:80]} ({r2.get('published','')})",
                    detail={"query": query, "authors": r2.get("authors", ""),
                            "category": r2.get("category", ""), "evaluation": evaluation},
                )

    except requests.Timeout:
        logger.warning("    arxiv 搜索超时 (30s), 标记为空")
        _record_finding(gap["gap_id"], "arxiv_api",
                        f"arXiv搜索超时: {query}", "",
                        1, "arXiv API timeout", {"status": "timeout"})
    except ET.ParseError as e:
        logger.warning("    arxiv XML 解析失败: %s", e)
    except Exception as e:
        logger.warning("    arxiv 搜索异常: %s", e)

    return results


def _search_semantic_scholar(query: str, gap: dict, max_results: int = 10) -> list[dict]:
    """搜索 Semantic Scholar 论文数据库。

    覆盖 arXiv 没有的会议论文、期刊文章，引用数排序。
    API: https://api.semanticscholar.org/graph/v1/paper/search
    无需认证，免费使用。
    """
    results = []
    try:
        logger.info("    semantic_scholar 搜索: API — \"%s\"", query)
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": query,
                "limit": str(max_results),
                "fields": "title,url,abstract,authors,year,venue,citationCount,publicationDate",
            },
            headers={"User-Agent": "knowledge-prospector/1.0"},
            timeout=30,
        )
        if r.status_code == 429:
            logger.warning("    semantic_scholar 速率限制 (429), 跳过")
            return results
        r.raise_for_status()

        data = r.json()
        papers = data.get("data", [])
        for paper in papers:
            title = (paper.get("title") or "").strip()
            abstract = (paper.get("abstract") or "").strip()
            paper_url = paper.get("url") or ""
            year = paper.get("year")
            venue = (paper.get("venue") or "") or ""
            citations = paper.get("citationCount", 0) or 0
            pub_date = (paper.get("publicationDate") or "") or ""

            authors_list = paper.get("authors", [])
            author_str = ", ".join(a.get("name", "") for a in authors_list[:3])
            if len(authors_list) > 3:
                author_str += " et al."

            results.append({
                "title": title[:200],
                "url": paper_url or f"https://www.semanticscholar.org/search?q={query}",
                "description": abstract[:300] if abstract else "",
                "source": "semantic_scholar_api",
                "authors": author_str,
                "published": str(pub_date or year or ""),
                "venue": venue,
                "citations": citations,
            })

        logger.info("    semantic_scholar 搜索完成: %d 篇论文", len(results))
        for r2 in results:
            evaluation = evaluate_finding(r2, gap)
            r2["_evaluation"] = evaluation
            if evaluation["relevance"] >= 3:
                _record_finding(
                    gap_id=gap["gap_id"],
                    source="semantic_scholar_api",
                    title=r2["title"],
                    url=r2["url"],
                    relevance=evaluation["relevance"],
                    summary=f"{evaluation['reason']}: {r2['title'][:80]} ({r2.get('published','')})",
                    detail={"query": query, "authors": r2.get("authors", ""),
                            "venue": r2.get("venue", ""), "citations": r2.get("citations", 0),
                            "evaluation": evaluation},
                )

    except requests.Timeout:
        logger.warning("    semantic_scholar 搜索超时 (30s)")
    except Exception as e:
        logger.warning("    semantic_scholar 搜索异常: %s", e)

    return results


def _search_vv_db(query: str, gap: dict, max_results: int = 20) -> list[dict]:
    """搜索大V视频转录文本，挖掘博主观点与知识缺口关联。"""
    import sqlite3
    results = []
    vv_db = Path("D:/1989n/stock_data/vv_radar.db")
    if not vv_db.exists():
        logger.warning("vv_radar.db 不存在: %s", vv_db)
        return results

    try:
        conn = sqlite3.connect(str(vv_db))
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        c.execute("""
            SELECT v.aweme_id, v.vv_id, v.desc, v.transcript_text, v.duration
            FROM vv_videos v
            WHERE v.transcript_text IS NOT NULL AND v.transcript_text != ''
        """)

        query_lower = query.lower()
        for row in c.fetchall():
            text = (row["transcript_text"] or "") + " " + (row["desc"] or "")
            if query_lower in text.lower():
                transcript = row["transcript_text"] or ""
                snippet = transcript[:300] if transcript else (row["desc"] or "无描述")[:100]
                results.append({
                    "title": (row["desc"] or "无描述")[:100],
                    "url": f"https://www.douyin.com/video/{row['aweme_id']}",
                    "description": snippet[:300],
                    "source": "vv_transcript",
                    "aweme_id": row["aweme_id"],
                    "vv_id": row["vv_id"],
                    "duration": row["duration"],
                })

        c.execute("""
            SELECT a.aweme_id, a.vv_id, a.vv_name, a.topics, a.logic_why,
                   a.tickers, a.upside_analysis, a.confidence
            FROM vv_analysis a
            WHERE a.topics IS NOT NULL OR a.logic_why IS NOT NULL
        """)
        for row in c.fetchall():
            search_text = " ".join(filter(None, [
                row["topics"], row["logic_why"], row["tickers"],
                row["upside_analysis"], row["vv_name"],
            ]))
            if query_lower in search_text.lower():
                results.append({
                    "title": f"[分析] {row['vv_name'] or '?'}: {(row['topics'] or '')[:60]}",
                    "url": f"https://www.douyin.com/video/{row['aweme_id']}",
                    "description": (row["logic_why"] or row["topics"] or "")[:300],
                    "source": "vv_analysis",
                    "aweme_id": row["aweme_id"],
                    "vv_id": row["vv_id"],
                    "tickers": row["tickers"],
                    "confidence": row["confidence"],
                })

        conn.close()
    except Exception as e:
        logger.warning("vv_db 搜索异常: %s", e)

    seen = set()
    deduped = []
    for r in results:
        if r["aweme_id"] not in seen:
            seen.add(r["aweme_id"])
            deduped.append(r)

    logger.info("    vv_db 搜索完成: %d 条结果 (去重后)", len(deduped))
    return deduped[:max_results]


def _search_web(query: str, gap: dict, timeout: int = 30) -> list[dict]:
    """通过Bing搜索执行Web搜索，30秒超时。"""
    import re as _re
    from html import unescape as _unescape

    results = []
    try:
        logger.info("    web 搜索真实执行: Bing — \"%s\"", query)
        headers = {"User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )}
        r = requests.get(
            "https://www.bing.com/search",
            params={"q": query, "count": "10"},
            headers=headers,
            timeout=timeout,
        )
        r.raise_for_status()

        for block in _re.findall(r'<li class="b_algo"[^>]*>.*?</li>', r.text, _re.DOTALL):
            m = _re.search(r'<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', block, _re.DOTALL)
            if not m:
                continue
            url = _unescape(m.group(1))
            title = _re.sub(r'<[^>]+>', "", m.group(2)).strip()
            if not title or not url:
                continue

            sm = _re.search(r'<p[^>]*>(.*?)</p>', block, _re.DOTALL)
            snippet = _re.sub(r'<[^>]+>', "", sm.group(1)).strip() if sm else ""

            results.append({
                "title": title[:200],
                "url": url,
                "description": snippet[:300],
                "source": "web_bing",
            })

        logger.info("    web 搜索完成: %d 条结果", len(results))

        # 记录 findings
        for r2 in results:
            evaluation = evaluate_finding(r2, gap)
            r2["_evaluation"] = evaluation
            if evaluation["relevance"] >= 3:
                _record_finding(
                    gap_id=gap["gap_id"],
                    source="web_bing",
                    title=r2["title"],
                    url=r2["url"],
                    relevance=evaluation["relevance"],
                    summary=f"{evaluation['reason']}: {r2['title']}",
                    detail={"query": query, "evaluation": evaluation},
                )

    except requests.Timeout:
        logger.warning("    web 搜索超时 (%ds), 标记为空", timeout)
        _record_finding(
            gap_id=gap["gap_id"], source="web_bing",
            title=f"Web搜索超时: {query}", url="",
            relevance=1,
            summary=f"Bing搜索超时 ({timeout}s)",
            detail={"query": query, "status": "timeout"},
        )
    except Exception as e:
        logger.warning("    web 搜索异常: %s, 标记为空", e)
        _record_finding(
            gap_id=gap["gap_id"], source="web_bing",
            title=f"Web搜索失败: {query}", url="",
            relevance=1,
            summary=f"Bing搜索异常: {e}",
            detail={"query": query, "status": "error", "error": str(e)},
        )

    return results


def _search_github(query: str, gap: dict, timeout: int = 30) -> list[dict]:
    """通过GitHub Search API执行搜索，30秒超时。"""
    results = []
    try:
        logger.info("    github 搜索真实执行: GitHub Search API — \"%s\"", query)
        gh_headers = {"Accept": "application/vnd.github.v3+json",
                       "User-Agent": "knowledge-prospector/1.0"}
        github_token = os.getenv("GITHUB_TOKEN", "")
        if github_token:
            gh_headers["Authorization"] = f"Bearer {github_token}"
        r = requests.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": 10},
            headers=gh_headers,
            timeout=timeout,
        )

        if r.status_code == 403 and "rate limit" in r.text.lower():
            logger.warning("    GitHub API 速率限制, 标记为空")
            _record_finding(
                gap_id=gap["gap_id"], source="github_api",
                title=f"GitHub速率限制: {query}", url="",
                relevance=1,
                summary="GitHub API rate limit exceeded",
                detail={"query": query, "status": "rate_limited"},
            )
            return []

        r.raise_for_status()
        data = r.json()

        for item in data.get("items", [])[:10]:
            results.append({
                "title": item.get("full_name", item.get("name", "?")),
                "url": item.get("html_url", ""),
                "description": (item.get("description") or "")[:300],
                "source": "github_api",
                "stars": item.get("stargazers_count", 0),
                "language": item.get("language", ""),
                "topics": item.get("topics", []),
            })

        logger.info("    github 搜索完成: %d 条结果", len(results))

        # 记录 findings
        for r2 in results:
            evaluation = evaluate_finding(r2, gap)
            r2["_evaluation"] = evaluation
            if evaluation["relevance"] >= 3:
                _record_finding(
                    gap_id=gap["gap_id"],
                    source="github_api",
                    title=r2["title"],
                    url=r2["url"],
                    relevance=evaluation["relevance"],
                    summary=f"{evaluation['reason']}: {r2['title']} (★{r2.get('stars', 0)})",
                    detail={"query": query, "stars": r2.get("stars", 0),
                            "evaluation": evaluation},
                )

    except requests.Timeout:
        logger.warning("    github 搜索超时 (%ds), 标记为空", timeout)
        _record_finding(
            gap_id=gap["gap_id"], source="github_api",
            title=f"GitHub搜索超时: {query}", url="",
            relevance=1,
            summary=f"GitHub API超时 ({timeout}s)",
            detail={"query": query, "status": "timeout"},
        )
    except Exception as e:
        logger.warning("    github 搜索异常: %s, 标记为空", e)
        _record_finding(
            gap_id=gap["gap_id"], source="github_api",
            title=f"GitHub搜索失败: {query}", url="",
            relevance=1,
            summary=f"GitHub API异常: {e}",
            detail={"query": query, "status": "error", "error": str(e)},
        )

    return results


# ── 状态报告 ──


def print_status():
    """打印勘探状态。"""
    log = _load_log()
    gaps = _load_gaps()

    print("知识勘探状态")
    print("=" * 60)

    # 按缺口统计
    by_gap = {}
    for f in log:
        gid = f.get("gap_id", "?")
        if gid not in by_gap:
            by_gap[gid] = {"total": 0, "high": 0, "absorbed": 0, "findings": []}
        by_gap[gid]["total"] += 1
        by_gap[gid]["findings"].append(f)
        if f.get("relevance", 0) >= 4:
            by_gap[gid]["high"] += 1
        if f.get("absorbed"):
            by_gap[gid]["absorbed"] += 1

    print(f"总发现: {len(log)} 条")
    print(f"开放缺口: {len(gaps)} 个")
    print()

    for gid, stats in sorted(by_gap.items()):
        gap_title = "?"
        for g in gaps:
            if g["gap_id"] == gid:
                gap_title = g["title"]
                break
        print(f"  {gid}:")
        print(f"    标题: {gap_title}")
        print(f"    发现: {stats['total']} 条 (高价值: {stats['high']}, 已吸收: {stats['absorbed']})")

    print()

    # 最新发现
    recent = sorted(log, key=lambda x: x.get("discovered_at", ""), reverse=True)[:5]
    if recent:
        print("最近发现:")
        for f in recent:
            print(f"  [{f.get('relevance', '?')}★] {f.get('title', '?')[:60]}")
            print(f"      源: {f.get('source', '?')} | 缺口: {f.get('gap_id', '?')}")


# ── CLI ──


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if not args or args[0] in ("--plan", "-p"):
        print_search_plan()
    elif args[0] in ("--status", "-s"):
        print_status()
    elif args[0] in ("--run", "-r"):
        target = args[1] if len(args) > 1 else "all"
        if target not in ("all", "douyin", "web", "github"):
            print("支持的目标: all, douyin, web, github")
            sys.exit(1)
        dry_run = "--dry" in args
        result = run_prospecting(target_source=target, dry_run=dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("用法: python knowledge_prospector.py [--plan|--status|--run <target>|--dry]")


if __name__ == "__main__":
    main()
