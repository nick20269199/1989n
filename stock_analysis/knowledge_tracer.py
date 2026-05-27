"""
knowledge_tracer.py — 上游追溯模块

不是搜关键词，是追源头：
  抖音博主引用/解读的内容 → 识别原始来源 (论文/GitHub/演讲/博客)
  → 评估价值 → 记录为发现 → 进入吸收管线

工作流:
  1. 扫描抖音归档，提取所有引用痕迹
  2. 分类：论文 / GitHub / 演讲 / 工具框架 / 博主推荐
  3. 关联到知识缺口（匹配优先级）
  4. 为高价值引用记录 web 搜索意图（供 deep-research 执行）
  5. 结果写 prospector_log.json → absorber 自动处理

用法:
  python knowledge_tracer.py --scan          # 扫描归档提取引用
  python knowledge_tracer.py --trace         # 扫描 + 追溯评估
  python knowledge_tracer.py --report        # 报告追溯结果
  python knowledge_tracer.py --gaps          # 缺口关联分析
"""
import json
import logging
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger("knowledge_tracer")

DATA_DIR = Path("D:/1989n/stock_data/knowledge")
ARCHIVE_DIR = Path("D:/1989n/stock_data/douyin/archive")
GAP_REGISTRY_FILE = DATA_DIR / "gap_registry.json"
PROSPECTOR_LOG = DATA_DIR / "prospector_log.json"

# ── 引用提取模式 ──

# arXiv 论文: arXiv:XXXX.XXXXX 或 arxiv.org/abs/XXXX.XXXXX
ARXIV_PATTERN = re.compile(r'arxiv[\s:]*(?:\/\/arxiv\.org\/abs\/)?\s*(\d{4}\.\d{4,5})(?:v\d+)?', re.IGNORECASE)

# GitHub 仓库: github.com/owner/repo 或 github.com/owner/repo.git
GITHUB_PATTERN = re.compile(r'github\.com[/:]([\w.-]+/[\w.-]+?)(?:\.git|/|\)|$|\s)', re.IGNORECASE)

# 中文风格 GitHub: "github🔍owner/repo" 或 "github🔍 owner/repo" 或 "github搜 owner/repo"
GITHUB_CN_PATTERN = re.compile(r'github[：:\s]*[🔍搜索]*\s*([A-Za-z][\w.-]+/[\w.-]+)', re.IGNORECASE)

# 常见 AI 论文关键词 + 标题 (引号内的英文内容)
QUOTED_TITLE_PATTERN = re.compile(r'[""]([A-Z][A-Za-z\s\d\-]{10,80})[""]')

# 中文论文描述: "XX最新论文" / "XX论文YY" / "论文解读: ZZ"
PAPER_CN_PATTERN = re.compile(
    r'(?:最新论文|新论文|论文解读|读论文|发论文|发表论文|开源论文)'
    r'[：:\s]*'
    r'([\w\s\-]{4,60}?)'
    r'(?:\s*[#，,。\.\!\?]|\s*$)',
    re.IGNORECASE
)

# 知名会议演讲: NeurIPS / ICML / ICLR / CVPR / ACL / EMNLP / WWW / KDD + 年份
CONFERENCE_PATTERN = re.compile(
    r'(NeurIPS|ICML|ICLR|CVPR|ACL|EMNLP|KDD|WWW|AAAI|IJCAI|ECCV|ICCV|SIGGRAPH|OSDI|SOSP|PLDI|POPL|ISCA|MICRO)\s*(?:19|20)\d{2}',
    re.IGNORECASE
)

# OpenAI / Anthropic / Google / Meta / DeepSeek 官方发布
ORG_RELEASE_PATTERN = re.compile(
    r'(OpenAI|Anthropic|Google|Meta|DeepSeek|Microsoft|Apple|Amazon|Mistral|Hugging Face)\s.*?(发布|开源|推出|论文|报告|blog|announce)',
    re.IGNORECASE
)

# 知名工具/框架
TOOL_PATTERN = re.compile(
    r'\b(Gbrain|LangChain|LlamaIndex|AutoGPT|BabyAGI|Chroma|Pinecone|Weaviate|Qdrant|Milvus|'
    r'vLLM|TensorRT|ONNX|Triton|Kubernetes|Docker|Ray|Dify|Flowise|n8n|'
    r'Claude Code|Codex|Cursor|Windsurf|Copilot|Devon|Devin|'
    r'Transformers|Diffusers|PEFT|LoRA|QLoRA|vLLM|SGLang)\b',
    re.IGNORECASE
)

# 著名 AI 研究者
PERSON_PATTERN = re.compile(
    r'\b(Andrej Karpathy|Geoffrey Hinton|Yann LeCun|Andrew Ng|Fei-Fei Li|Ian Goodfellow|'
    r'Demis Hassabis|Ilya Sutskever|Gary Tan|Sam Altman|Dario Amodei|'
    r'Jensen Huang|Elon Musk|Mark Chen|Jim Fan|Lex Fridman)\b',
    re.IGNORECASE
)


def extract_references(text: str) -> list[dict]:
    """从单段文本中提取所有引用痕迹。"""
    refs = []

    for m in ARXIV_PATTERN.finditer(text):
        refs.append({
            "ref_type": "paper_arxiv",
            "ref_name": f"arXiv:{m.group(1)}",
            "ref_url": f"https://arxiv.org/abs/{m.group(1)}",
            "confidence": 0.95,
            "context": _extract_context(text, m.start(), m.end()),
        })

    for m in GITHUB_PATTERN.finditer(text):
        repo = m.group(1).strip().rstrip("/)")
        refs.append({
            "ref_type": "github",
            "ref_name": repo,
            "ref_url": f"https://github.com/{repo}",
            "confidence": 0.95,
            "context": _extract_context(text, m.start(), m.end()),
        })

    for m in GITHUB_CN_PATTERN.finditer(text):
        repo = m.group(1).strip().rstrip("/)")
        refs.append({
            "ref_type": "github",
            "ref_name": repo,
            "ref_url": f"https://github.com/{repo}",
            "confidence": 0.85,
            "context": _extract_context(text, m.start(), m.end()),
        })

    for m in PAPER_CN_PATTERN.finditer(text):
        title = m.group(1).strip()
        if len(title) >= 4:
            refs.append({
                "ref_type": "paper_named",
                "ref_name": title,
                "ref_url": "",
                "confidence": 0.65,
                "context": _extract_context(text, m.start(), m.end()),
            })

    for m in QUOTED_TITLE_PATTERN.finditer(text):
        title = m.group(1).strip()
        # 过滤掉非论文/非引用的普通引号内容
        if any(kw in text[m.start()-80:m.end()+80].lower() for kw in ["paper", "论文", "提出", "published", "read"]):
            refs.append({
                "ref_type": "paper_named",
                "ref_name": title,
                "ref_url": "",
                "confidence": 0.7,
                "context": _extract_context(text, m.start(), m.end()),
            })

    for m in CONFERENCE_PATTERN.finditer(text):
        refs.append({
            "ref_type": "conference",
            "ref_name": m.group(0).upper(),
            "ref_url": "",
            "confidence": 0.8,
            "context": _extract_context(text, m.start(), m.end()),
        })

    for m in ORG_RELEASE_PATTERN.finditer(text):
        raw = m.group(0).strip()[:120]
        # 去 hashtags 和多余标点，保留核心内容
        cleaned = re.sub(r'#[^\s#]+', '', raw).strip()
        cleaned = re.sub(r'[\s,;:]+', ' ', cleaned).strip()
        refs.append({
            "ref_type": "org_release",
            "ref_name": cleaned[:100],
            "ref_url": "",
            "confidence": 0.7,
            "context": _extract_context(text, m.start(), m.end()),
        })

    for m in TOOL_PATTERN.finditer(text):
        refs.append({
            "ref_type": "tool_framework",
            "ref_name": m.group(0),
            "ref_url": "",
            "confidence": 0.85,
            "context": _extract_context(text, m.start(), m.end()),
        })

    for m in PERSON_PATTERN.finditer(text):
        refs.append({
            "ref_type": "person",
            "ref_name": m.group(0),
            "ref_url": "",
            "confidence": 0.9,
            "context": _extract_context(text, m.start(), m.end()),
        })

    return refs


def _extract_context(text: str, start: int, end: int, width: int = 80) -> str:
    """提取引用周围的上下文。"""
    ctx_start = max(0, start - width)
    ctx_end = min(len(text), end + width)
    prefix = "..." if ctx_start > 0 else ""
    suffix = "..." if ctx_end < len(text) else ""
    return f"{prefix}{text[ctx_start:ctx_end].strip()}{suffix}"


# ── 归档扫描 ──


def scan_archives(max_videos: int = None) -> list[dict]:
    """扫描所有抖音归档，提取引用痕迹。

    Args:
        max_videos: 每个归档最多处理的视频数（None=全部）

    Returns:
        引用列表 [{creator, ref_type, ref_name, ref_url, confidence, context, source_video}]
    """
    all_refs = []
    if not ARCHIVE_DIR.exists():
        logger.warning("归档目录不存在: %s", ARCHIVE_DIR)
        return all_refs

    for fp in sorted(ARCHIVE_DIR.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("跳过 %s: %s", fp.name, e)
            continue

        nickname = data.get("nickname", fp.stem)
        videos = data.get("videos", [])
        if max_videos:
            videos = videos[:max_videos]

        for v in videos:
            # 合并所有文本字段
            text = " ".join(filter(None, [
                v.get("desc", ""),
                v.get("caption", ""),
                v.get("chapter_content", ""),
            ]))
            if not text.strip():
                continue

            refs = extract_references(text)
            for r in refs:
                r["creator"] = nickname
                r["source_video"] = v.get("aweme_id", "")
                r["source_url"] = f"https://www.douyin.com/video/{v.get('aweme_id', '')}"
                r["discovered_at"] = datetime.now().isoformat()
            all_refs.extend(refs)

    logger.info("归档扫描完成: %d 条引用 (来自 %d 个博主)", len(all_refs), len(set(r["creator"] for r in all_refs)))
    return all_refs


# ── 缺口关联评分 ──


def _load_gaps() -> list[dict]:
    if GAP_REGISTRY_FILE.exists():
        try:
            return json.loads(GAP_REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def score_reference(ref: dict) -> dict:
    """评估引用对知识缺口的价值。

    使用三层匹配:
      1. 搜索查询匹配 — ref 文本 vs gap['search_queries']
      2. 关键词匹配 — ref 文本 vs gap['title']+['description']
      3. 类型路由 — ref_type 自动映射到最相关的 gap

    返回:
      score: 1(低)-5(高)
      matched_gaps: 匹配的缺口 ID 列表
      reason: 评分理由
    """
    gaps = _load_gaps()
    active_gaps = [g for g in gaps if g.get("status") in ("open", "investigating")]

    if not active_gaps:
        return {"score": 3, "matched_gaps": [], "reason": "无活跃缺口，默认中等价值"}

    ref_text = f"{ref.get('ref_name', '')} {ref.get('context', '')}".lower()
    ref_type = ref.get("ref_type", "")

    # 类型 → 缺口域名路由（引用类型天然指向某些缺口）
    type_to_domain = {
        "paper_arxiv": ["knowledge-ai-design-philosophy", "architecture", "pipeline"],
        "paper_named": ["knowledge-ai-design-philosophy", "architecture"],
        "github": ["knowledge-ai-design-philosophy", "knowledge-upstream-tracing"],
        "conference": ["knowledge-ai-design-philosophy"],
        "org_release": ["knowledge-upstream-tracing"],
        "tool_framework": ["knowledge-upstream-tracing"],
        "person": ["knowledge-ai-design-philosophy"],
    }

    matched_gaps = []
    match_score = 0

    for gap in active_gaps:
        gap_id = gap["gap_id"]

        # 匹配文本来源：title + description + search_queries
        gap_text = (
            gap.get("title", "") + " " +
            gap.get("description", "") + " " +
            " ".join(gap.get("search_queries", []))
        ).lower()

        gap_keywords = set(w for w in gap_text.split() if len(w) > 2)

        hits = sum(1 for kw in gap_keywords if kw in ref_text)
        if hits > 0:
            matched_gaps.append({
                "gap_id": gap_id,
                "title": gap.get("title", ""),
                "match_hits": hits,
            })
            match_score += hits

        # 类型路由加分：如果引用类型属于这个缺口的域名
        routed = type_to_domain.get(ref_type, [])
        if gap_id in routed:
            match_score += 0.5  # 半匹配分

    # 来源类型加分
    type_bonus = {
        "paper_arxiv": 2,      # 论文 = 最权威
        "paper_named": 2,
        "github": 1,           # 开源项目
        "conference": 1,       # 学术演讲
        "org_release": 1,      # 官方发布
        "tool_framework": 1,   # 工具框架
        "person": 0,           # 人物提及
    }.get(ref_type, 0)

    # 综合评分
    if matched_gaps or type_to_domain.get(ref_type):
        raw_score = 2 + type_bonus
        if matched_gaps:
            raw_score += min(match_score * 0.5, 1)  # 最多加1分
    else:
        raw_score = 2

    score = min(raw_score, 5)

    reason_parts = []
    if matched_gaps:
        reason_parts.append(f"匹配 {len(matched_gaps)} 个缺口 ({int(match_score)} 命中)")
    if type_bonus > 0:
        reason_parts.append(f"来源类型加分 (+{type_bonus})")
    if not matched_gaps and score >= 3:
        reason_parts.append("类型路由匹配")

    return {
        "score": score,
        "matched_gaps": matched_gaps,
        "reason": ", ".join(reason_parts) if reason_parts else "低关联度",
    }


# ── 记录发现 ──


def _load_log() -> list[dict]:
    if PROSPECTOR_LOG.exists():
        try:
            return json.loads(PROSPECTOR_LOG.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_log(log: list[dict]):
    PROSPECTOR_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def record_trace_findings(refs: list[dict], min_score: int = 3) -> list[dict]:
    """把高价值引用记录为勘探发现。

    去重逻辑：同 ref_name + 同 gap_id 不重复记录。
    """
    log = _load_log()
    existing_keys = set()
    for entry in log:
        if entry.get("source") == "upstream_trace":
            existing_keys.add(f"{entry.get('_ref_name','')}_{entry.get('gap_id','')}")

    new_findings = []
    for ref in refs:
        scoring = score_reference(ref)
        if scoring["score"] < min_score:
            continue

        # 按缺口匹配 + 类型路由确定目标缺口
        target_gaps = [m["gap_id"] for m in scoring.get("matched_gaps", [])]
        if not target_gaps:
            type_fallback = {
                "paper_arxiv": "knowledge-ai-design-philosophy",
                "paper_named": "knowledge-ai-design-philosophy",
                "github": "knowledge-upstream-tracing",
                "conference": "knowledge-ai-design-philosophy",
                "org_release": "knowledge-upstream-tracing",
                "tool_framework": "knowledge-upstream-tracing",
                "person": "knowledge-ai-design-philosophy",
            }
            target_gaps = [type_fallback.get(ref.get("ref_type", ""), "knowledge-creator-discovery")]

        for gap_id in target_gaps:
            dedup_key = f"{ref.get('ref_name','')}_{gap_id}"
            if dedup_key in existing_keys:
                continue

            title = self_repr(ref)
            summary = (
                f"[上游追溯] {ref.get('ref_type','')}: {ref.get('ref_name','')} | "
                f"来自 {ref.get('creator','')} | "
                f"评分: {scoring['score']}/5 | "
                f"{scoring['reason']} | "
                f"上下文: {ref.get('context','')[:200]}"
            )

            finding = {
                "finding_id": f"trace_{int(datetime.now().timestamp())}_{len(new_findings)}",
                "gap_id": gap_id,
                "source": "upstream_trace",
                "title": title[:200],
                "url": ref.get("ref_url", "") or ref.get("source_url", ""),
                "relevance": scoring["score"],
                "summary": summary[:500],
                "absorbed": False,
                "discovered_at": datetime.now().isoformat(),
                "_ref_name": ref.get("ref_name", ""),
                "_ref_type": ref.get("ref_type", ""),
                "_creator": ref.get("creator", ""),
                "_scoring": scoring,
            }

            # 如果是论文/GitHub/官方发布，记录 web 搜索意图
            if ref.get("ref_type") in ("paper_arxiv", "paper_named", "github", "org_release"):
                finding["_search_intent"] = {
                    "type": "fetch_source",
                    "ref_type": ref["ref_type"],
                    "ref_name": ref["ref_name"],
                    "ref_url": ref.get("ref_url", ""),
                    "priority": "high" if scoring["score"] >= 4 else "medium",
                    "status": "pending",
                }

            log.append(finding)
            new_findings.append(finding)
            existing_keys.add(dedup_key)

    _save_log(log)
    return new_findings


def self_repr(ref: dict) -> str:
    """生成人类可读的引用标题。"""
    prefix = {
        "paper_arxiv": "论文",
        "paper_named": "论文",
        "github": "GitHub",
        "conference": "会议",
        "org_release": "官方发布",
        "tool_framework": "工具",
        "person": "人物",
    }.get(ref.get("ref_type", ""), "引用")

    return f"[{prefix}] {ref.get('ref_name', '?')} (via {ref.get('creator', '?')})"


# ── 主追溯流程 ──


def run_tracing(dry_run: bool = False) -> dict:
    """执行一次完整的上游追溯。

    流程:
      1. 扫描所有归档提取引用
      2. 评估引用价值
      3. 记录高价值引用为发现

    Returns:
        统计字典
    """
    logger.info("开始上游追溯...")

    # Step 1: 扫描引用
    refs = scan_archives()
    logger.info("Step 1 ✓ 提取 %d 条引用痕迹", len(refs))

    if not refs:
        return {"archives_scanned": 0, "refs_extracted": 0, "findings_recorded": 0}

    # Step 2: 统计
    by_type = {}
    for r in refs:
        by_type.setdefault(r["ref_type"], 0)
        by_type[r["ref_type"]] += 1

    # Step 3: 记录发现
    if not dry_run:
        findings = record_trace_findings(refs, min_score=3)
        logger.info("Step 2 ✓ 记录 %d 条高价值发现", len(findings))
    else:
        findings = []
        logger.info("Step 2 - dry run, 不写入")

    return {
        "archives_scanned": len(list(ARCHIVE_DIR.glob("*.json"))) if ARCHIVE_DIR.exists() else 0,
        "refs_extracted": len(refs),
        "refs_by_type": by_type,
        "findings_recorded": len(findings),
        "dry_run": dry_run,
    }


# ── 缺口关联分析 ──


def analyze_gap_coverage() -> dict:
    """分析追溯发现的缺口覆盖情况。"""
    log = _load_log()
    trace_findings = [f for f in log if f.get("source") == "upstream_trace"]
    gaps = _load_gaps()

    by_gap = {}
    for f in trace_findings:
        gid = f.get("gap_id", "?")
        if gid not in by_gap:
            by_gap[gid] = {"count": 0, "high_value": 0, "items": []}
        by_gap[gid]["count"] += 1
        if f.get("relevance", 0) >= 4:
            by_gap[gid]["high_value"] += 1
        by_gap[gid]["items"].append(f)

    # 找未被追溯覆盖的缺口
    gap_map = {g["gap_id"]: g for g in gaps}
    uncovered = [
        {"gap_id": gid, "title": g["title"]}
        for gid, g in gap_map.items()
        if g.get("status") in ("open", "investigating") and gid not in by_gap
    ]

    return {
        "total_trace_findings": len(trace_findings),
        "covered_gaps": len(by_gap),
        "uncovered_gaps": len(uncovered),
        "by_gap": {gid: {"count": s["count"], "high_value": s["high_value"]} for gid, s in by_gap.items()},
        "uncovered_list": uncovered,
    }


# ── 报告 ──


def print_trace_report():
    """打印上游追溯报告。"""
    log = _load_log()
    trace_findings = [f for f in log if f.get("source") == "upstream_trace"]

    print("上游追溯报告")
    print("=" * 60)
    print(f"追溯发现总数: {len(trace_findings)}")
    print()

    # 按类型统计
    by_type = {}
    for f in trace_findings:
        t = f.get("_ref_type", "unknown")
        by_type.setdefault(t, 0)
        by_type[t] += 1

    print("引用类型分布:")
    for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
        print(f"  {t}: {c}")
    print()

    # 按创作者统计
    by_creator = {}
    for f in trace_findings:
        c = f.get("_creator", "unknown")
        by_creator.setdefault(c, 0)
        by_creator[c] += 1

    print("创作者引用量:")
    for c, n in sorted(by_creator.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}")
    print()

    # 按价值评分
    high_value = [f for f in trace_findings if f.get("relevance", 0) >= 4]
    print(f"高价值发现 (≥4★): {len(high_value)}")

    # 待处理
    with_search_intent = [f for f in trace_findings if f.get("_search_intent", {}).get("status") == "pending"]
    print(f"待执行 web 搜索: {len(with_search_intent)}")
    print()

    # 待搜索的上游来源
    if with_search_intent:
        print("待搜索的上游来源 (供 deep-research 执行):")
        for f in sorted(with_search_intent, key=lambda x: x.get("relevance", 0), reverse=True)[:10]:
            intent = f["_search_intent"]
            print(f"  [{f['relevance']}★] {intent['ref_name']}")
            print(f"       类型: {intent['ref_type']} | 来自: {f.get('_creator','?')}")
            if intent.get("ref_url"):
                print(f"       URL: {intent['ref_url']}")
        print()

    # 缺口覆盖
    coverage = analyze_gap_coverage()
    print(f"缺口覆盖: {coverage['covered_gaps']} 个有追溯发现, {coverage['uncovered_gaps']} 个无覆盖")
    if coverage.get("uncovered_list"):
        for ug in coverage["uncovered_list"][:5]:
            print(f"  ○ {ug['title']}")


def print_trace_refs(refs: list[dict]):
    """打印原始引用列表。"""
    if not refs:
        print("无引用痕迹。")
        return

    by_type = {}
    for r in refs:
        by_type.setdefault(r["ref_type"], []).append(r)

    print(f"共 {len(refs)} 条引用痕迹:")
    print("=" * 70)
    for t, items in sorted(by_type.items(), key=lambda x: -len(x[1])):
        print(f"\n[{t}] {len(items)} 条:")
        for item in items[:5]:
            print(f"  {item['ref_name']}")
            print(f"    来自: {item['creator']}")
            print(f"    上下文: {item.get('context', '')[:100]}")
        if len(items) > 5:
            print(f"  ... 还有 {len(items)-5} 条")


def print_gap_analysis():
    """打印缺口覆盖分析。"""
    coverage = analyze_gap_coverage()
    gaps = _load_gaps()

    print("缺口覆盖分析")
    print("=" * 60)

    for g in sorted(gaps, key=lambda x: x.get("priority", "Z")):
        gid = g["gap_id"]
        info = coverage["by_gap"].get(gid, {"count": 0, "high_value": 0})
        status_icon = {
            "open": "○", "investigating": "◎", "solution_found": "◉", "absorbed": "●",
        }.get(g.get("status", ""), "?")

        if info["count"] > 0:
            print(f"  {status_icon} [{g['priority']}] {g['title']}")
            print(f"      追溯: {info['count']} 发现 (高价值: {info['high_value']})")
        else:
            if g.get("status") in ("open", "investigating"):
                print(f"  {status_icon} [{g['priority']}] {g['title']} — ⚠️ 无上游追溯覆盖")


# ── CLI ──


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if not args or args[0] in ("--scan", "-s"):
        refs = scan_archives()
        print_trace_refs(refs)
    elif args[0] in ("--trace", "-t"):
        dry_run = "--dry" in args
        result = run_tracing(dry_run=dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if not dry_run:
            print()
            print_trace_report()
    elif args[0] in ("--report", "-r"):
        print_trace_report()
    elif args[0] in ("--gaps", "-g"):
        print_gap_analysis()
    else:
        print("用法:")
        print("  python knowledge_tracer.py --scan          # 扫描归档提取引用")
        print("  python knowledge_tracer.py --trace         # 全流程追溯")
        print("  python knowledge_tracer.py --report        # 追溯报告")
        print("  python knowledge_tracer.py --gaps          # 缺口覆盖分析")
        print("  python knowledge_tracer.py --trace --dry   # 预览不写入")


if __name__ == "__main__":
    main()
