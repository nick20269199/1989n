"""
新闻增强器 — CLS详情页正文提取 + 分类 + 重要性评分
===================================================
设计原则:
  1. 正文提取是标题采集的后置钩子, 失败不影响主流程
  2. 每条正文提取超时5s, 异常则 content=null
  3. 每次最多增强10条, 选持仓相关+重要标记的条目优先

调用方 (news_scheduler.py) 需在 try/except 中调用, 确保隔离。
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("news_enricher")

# === 路径配置 ===
STOCK_DATA_DIR = Path("D:/1989n/stock_data")
CONCEPT_MAPPING_PATH = STOCK_DATA_DIR / "concept_mapping.json"
BS_ANALYSIS_PATH = STOCK_DATA_DIR / "bs_analysis.json"

# === 参数 ===
CLS_DETAIL_TIMEOUT = 8        # 单条正文超时
MAX_ENRICH_PER_RUN = 30       # 每次最多提取N条正文
ENRICH_WORKERS = 5            # 并发线程数
CST = timezone(timedelta(hours=8))

# === 分类关键词映射 ===
CATEGORY_RULES = {
    "policy": [
        "政策", "规划", "发改委", "国务院", "央行", "证监会", "工信部",
        "商务部", "政治局", "中央", "国家", "监管", "法规", "补贴",
        "税收", "信贷", "专项债", "国债", "十四五", "供给侧",
        "国家数据局", "金融监管", "财政部", "人大", "立法",
    ],
    "macro": [
        "GDP", "CPI", "PMI", "经济数据", "通胀", "通缩", "就业",
        "美联储", "加息", "降息", "汇率", "人民币", "贸易顺差",
        "进出口", "社融", "M2", "LPR", "利率", "经济日报",
    ],
    "geopolitical": [
        "地缘", "制裁", "关税", "战争", "冲突", "军事", "国防",
        "北约", "欧盟", "中美", "中欧", "对华", "外交", "军演",
        "战斧", "导弹", "无人机", "枪击", "枪声", "枪手", "爆炸",
        "伊朗", "乌克兰", "基辅", "以色列", "哈马斯", "胡塞",
        "巴勒斯坦", "白宫", "特朗普", "伊朗核", "霍尔木兹",
        "紧急状态", "遇难", "死亡", "致命", "火灾", "坍塌",
        "埃博拉", "疫情", "地震", "洪水", "台风",
    ],
    "corporate": [
        "业绩", "财报", "营收", "利润", "合同", "中标", "重组",
        "定增", "减持", "增持", "回购", "分红", "送转",
        "上市", "退市", "停牌", "ST", "异常波动",
        "订单", "募资", "配股", "可转债", "股权激励",
    ],
}

IMPORTANCE_RULES = [
    (10, ["重大", "紧急", "突发", "刷新纪录", "首次", "里程碑", "历史性",
          "遇难", "致命", "爆炸", "崩盘", "熔断"]),
    (8,  ["涨停", "跌停", "暴涨", "暴跌", "临停", "紧急状态"]),
    (6,  ["政策", "央行", "国务院", "证监会", "发改委", "政治局",
          "特朗普", "美联储", "制裁", "关税", "战争"]),
    (4,  ["合同", "中标", "业绩", "财报", "重组", "定增", "回购",
          "订单", "减持", "增持"]),
    (2,  ["公告", "发布", "推出", "宣布", "启动", "上线"]),
]

# CLS详情页公共headers
_CLS_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.cls.cn/telegraph",
}


# ====================================================================
#  正文提取
# ====================================================================

def _clean_html(raw: str) -> str:
    """清理HTML标签和实体, 保留纯文本。"""
    if not raw:
        return ""
    text = raw.replace("&nbsp;", " ").replace("&amp;", "&")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_cls_detail(article_id: str) -> Optional[str]:
    """
    从CLS详情页提取正文。

    详情页是 Next.js 渲染, 正文数据在 <script id="__NEXT_DATA__"> 的
    JSON 中 props.pageProps.initialState.detail.articleDetail.content。
    不需要执行JS, 正则提取即可。
    """
    url = f"https://www.cls.cn/detail/{article_id}"
    try:
        resp = requests.get(url, headers=_CLS_HEADERS, timeout=CLS_DETAIL_TIMEOUT)
        resp.raise_for_status()

        m = re.search(
            r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            resp.text, re.DOTALL
        )
        if not m:
            return None

        payload = json.loads(m.group(1))
        detail = (
            payload.get("props", {})
            .get("initialState", {})
            .get("detail", {})
            .get("articleDetail", {})
        )
        content = detail.get("content") or detail.get("brief") or ""
        return _clean_html(content) if content else None

    except Exception:
        return None


# ====================================================================
#  分类 + 重要性
# ====================================================================

def load_concept_mapping() -> dict:
    """加载概念→持仓映射表。"""
    try:
        if CONCEPT_MAPPING_PATH.exists():
            return json.loads(CONCEPT_MAPPING_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def load_historical_stocks() -> dict[str, str]:
    """
    从 bs_analysis.json 加载历史分析过的标的。
    用于新闻名称匹配: {stock_name → stock_code}

    bs_analysis 结构: { winners/losers/flats → { top_best_stocks/top_worst_stocks: [[code, {name}], ...] } }
    """
    stocks: dict[str, str] = {}
    try:
        if not BS_ANALYSIS_PATH.exists():
            return stocks
        data = json.loads(BS_ANALYSIS_PATH.read_text(encoding="utf-8"))
        for section_key in ("winners", "losers", "flats"):
            section = data.get(section_key, {})
            for list_key in ("top_best_stocks", "top_worst_stocks"):
                for entry in section.get(list_key, []):
                    if isinstance(entry, list) and len(entry) == 2:
                        code, info = entry[0], entry[1]
                        name = info.get("name", "") if isinstance(info, dict) else ""
                        if code and name:
                            stocks[name] = code
        logger.debug(f"[Enricher] 历史标的: {len(stocks)} 只")
    except Exception as e:
        logger.warning(f"[Enricher] 加载历史标的失败: {e}")
    return stocks


def classify_item(
    title: str,
    content: str = "",
    concept_mapping: dict = None,
    historical_stocks: dict[str, str] = None,
) -> dict:
    """
    单条新闻分类。

    Returns:
        dict: {category_group, importance, matched_sectors}
    """
    text = f"{title} {content or ''}".lower()

    # 1. 分类: policy > macro > geopolitical > corporate > industry(默认)
    category_group = "industry"
    for cat, keywords in CATEGORY_RULES.items():
        for kw in keywords:
            if kw.lower() in text:
                category_group = cat
                break
        if category_group != "industry":
            break

    # 2. 重要性 1-10
    importance = 1
    for score, keywords in IMPORTANCE_RULES:
        for kw in keywords:
            if kw.lower() in text:
                if score > importance:
                    importance = score
                break

    # 3. 匹配持仓概念
    matched_sectors = []
    if concept_mapping:
        kw_map = concept_mapping.get("keyword_to_holdings", {})
        for keyword, stocks in kw_map.items():
            if keyword.lower() in text:
                for stock_code in stocks:
                    if stock_code not in matched_sectors:
                        matched_sectors.append(stock_code)

    # 4. 持仓相关提升重要性
    if matched_sectors and importance < 5:
        importance = 5

    return {
        "category_group": category_group,
        "importance": min(importance, 10),
        "matched_sectors": matched_sectors,
    }


# ====================================================================
#  增强管线
# ====================================================================

def _pre_classify(candidates: list, concept_mapping: dict):
    """基于标题快速初筛分类。"""
    for item, _ in candidates:
        title = item.get("title", "")
        cls_info = classify_item(title, "", concept_mapping)
        item["importance"] = cls_info["importance"]


def _final_classify(items: list[dict], concept_mapping: dict,
                    historical_stocks: dict[str, str] = None) -> list[dict]:
    """基于标题+正文做最终分类。"""
    for item in items:
        cls_info = classify_item(
            item.get("title", ""),
            item.get("content", "") or "",
            concept_mapping,
            historical_stocks=historical_stocks,
        )
        item["category_group"] = cls_info["category_group"]
        item["importance"] = cls_info["importance"]
        item["matched_sectors"] = cls_info["matched_sectors"]
    return items


def enrich_items(items: list[dict]) -> list[dict]:
    """
    对新闻列表做分类 + 正文提取。

    流程:
      1. 基于标题做初筛分类
      2. 并发提取 CLS 详情页正文
      3. 基于 标题+正文 做最终分类+重要性+持仓匹配

    Returns: 增强后的列表 (原地修改)
    """
    concept_mapping = load_concept_mapping()
    historical_stocks = load_historical_stocks()

    # 1. 初筛: 基于标题的快速分类 (content 还没拿到)
    for item in items:
        item.setdefault("content", None)

    # 2. 正文提取候选: 所有 CLS 来源且有 article_id 的
    candidates = []
    for item in items:
        if item.get("content") is not None:
            continue  # 已有正文, 跳过
        url = item.get("url", "")
        if "cls.cn/detail/" not in url:
            continue
        article_id = url.rstrip("/").split("/")[-1]
        if not article_id.isdigit():
            continue
        candidates.append((item, article_id))

    if candidates:
        # 按标题重要性初筛排序, 取前N条
        _pre_classify(candidates, concept_mapping)
        candidates.sort(key=lambda x: x[0]["importance"], reverse=True)
        candidates = candidates[:MAX_ENRICH_PER_RUN]

        # 并发提取
        logger.info(
            f"[Enricher] 并发提取 {len(candidates)} 条 (workers={ENRICH_WORKERS})"
        )
        success = 0
        with ThreadPoolExecutor(max_workers=ENRICH_WORKERS) as executor:
            future_map = {
                executor.submit(fetch_cls_detail, aid): (item, aid)
                for item, aid in candidates
            }
            for future in as_completed(future_map):
                item, aid = future_map[future]
                try:
                    c = future.result()
                    if c:
                        item["content"] = c
                        success += 1
                except Exception:
                    pass

        logger.info(f"[Enricher] 正文提取: {success}/{len(candidates)} 条成功")

    # 3. 终筛: 基于 标题+正文 做完整分类
    return _final_classify(items, concept_mapping, historical_stocks)


def enrich_latest_news(mode: str) -> bool:
    """
    增强最新新闻JSON文件 (后置钩子, 原子写入)。

    流程: 找到最新JSON → 增强 → 写入临时文件 → 原子替换。
    写入中间失败不会损坏原文件。

    Args:
        mode: morning / intraday / evening

    Returns:
        bool: True 表示执行完成 (含0条增强), False 为异常
    """
    mode_prefix = "manual" if mode == "morning" else mode
    today = datetime.now(CST).strftime("%Y%m%d")
    pattern = f"news_{mode_prefix}_{today}_*.json"

    try:
        files = sorted(Path(STOCK_DATA_DIR).glob(pattern))
        if not files:
            yesterday = (datetime.now(CST) - timedelta(days=1)).strftime("%Y%m%d")
            files = sorted(Path(STOCK_DATA_DIR).glob(
                f"news_{mode_prefix}_{yesterday}_*.json"
            ))
        if not files:
            logger.warning(f"[Enricher] 未找到文件: {pattern}")
            return False

        latest = files[-1]
        raw = latest.read_text(encoding="utf-8")
        data = json.loads(raw)
        items = data.get("data", [])
        if not items:
            return True

        t0 = time.time()
        enriched = enrich_items(items)
        elapsed = time.time() - t0

        enriched_count = sum(
            1 for i in enriched if i.get("content") and i["content"] is not None
        )

        data["data"] = enriched
        data["enriched_at"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
        data["enriched_count"] = enriched_count

        # 原子写入: .tmp → replace
        tmp_path = latest.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        tmp_path.replace(latest)

        # 结构化统计日志
        cats = {}
        imp_buckets = {"high": 0, "mid": 0, "low": 0}
        holdings_match = 0
        total_chars = 0
        for i in enriched:
            g = i.get("category_group", "?")
            cats[g] = cats.get(g, 0) + 1
            imp = i.get("importance", 1)
            if imp >= 8:
                imp_buckets["high"] += 1
            elif imp >= 4:
                imp_buckets["mid"] += 1
            else:
                imp_buckets["low"] += 1
            if i.get("matched_sectors"):
                holdings_match += 1
            total_chars += len(i.get("content") or "")

        logger.info(
            f"[Enricher] STATS | {latest.name}"
            f" | {enriched_count}/{len(enriched)} enriched"
            f" | avg {total_chars//max(len(enriched),1)} chars"
            f" | cat={cats}"
            f" | imp={imp_buckets}"
            f" | holdings={holdings_match}"
            f" | {elapsed:.1f}s"
        )
        return True

    except Exception as e:
        logger.error(f"[Enricher] 异常: {e}")
        return False
