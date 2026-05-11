"""
Simple NLP analysis bridge for Chinese financial text.

Uses a lightweight keyword-based approach — no heavy ML dependency
required.  Supports sentiment scoring, keyword extraction, news
summarisation, and alert-type classification.
"""

from __future__ import annotations

import logging
import re
from collections import Counter

from bridge_config import ALERT_TYPES, NLP_ENABLED, NLP_MODEL

logger = logging.getLogger("bridge_nlp")

# ---------------------------------------------------------------------------
# Sentiment lexicons (Chinese)
# ---------------------------------------------------------------------------

_POSITIVE_WORDS: set[str] = {
    "暴涨", "涨停", "利好", "突破", "新高", "增长", "盈利", "回购",
    "增持", "中标", "订单", "超预期", "分红", "扩产", "研发成功",
    "合作", "签约", "获批", "上线", "量产", "扭亏", "龙头",
    "放量上涨", "资金流入", "机构买入", "评级上调", "业绩预增",
    "强势", "创新高", "突破平台", "上升通道", "景气", "需求旺盛",
    "政策支持", "行业拐点", "份额提升", "毛利率提升", "净利润大增",
}

_NEGATIVE_WORDS: set[str] = {
    "暴跌", "跌停", "利空", "破位", "新低", "亏损", "减持", "套现",
    "下调", "停工", "停产", "诉讼", "违规", "处罚", "退市",
    "业绩变脸", "商誉减值", "质押", "爆仓", "资金流出", "机构卖出",
    "评级下调", "业绩预亏", "弱势", "持续下跌", "破发",
    "需求疲软", "产能过剩", "价格战", "份额下滑", "毛利率下降",
    "资金链", "违约", "重组失败", "立案调查", "信披违规",
}

# Alert-type keyword map — each type has triggering expressions
_ALERT_KEYWORDS: dict[str, list[str]] = {
    "price_break": [
        "突破", "破位", "涨停", "跌停", "新高", "新低",
        "突破平台", "突破阻力", "跌破支撑", "突破前高",
    ],
    "volume_surge": [
        "放量", "巨量", "天量", "换手率", "成交量爆炸",
        "量比", "放量上涨", "放量下跌", "成交额突增",
    ],
    "technical": [
        "金叉", "死叉", "超买", "超卖", "RSI", "MACD",
        "均线", "多头排列", "空头排列", "底背离", "顶背离",
        "布林带", "筹码集中", "筹码分散",
    ],
    "risk": [
        "止损", "风险", "仓位", "回撤", "爆仓",
        "强制平仓", "黑天鹅", "系统性风险", "流动性危机",
    ],
    "system": [
        "异常", "错误", "超时", "断连", "服务不可用",
        "API限制", "数据缺失", "同步失败",
    ],
    "news": [
        "公告", "财报", "业绩", "年报", "一季报", "中报", "三季报",
        "重大事项", "停牌", "复牌", "重组", "收购", "合并",
    ],
    "sentiment": [
        "恐慌", "贪婪", "情绪", "信心", "悲观", "乐观",
        "散户", "北向资金", "融资融券", "市场情绪",
    ],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_sentiment(text: str) -> dict:
    """
    Score the sentiment of *text* using keyword counting.

    Returns a dict with:
      - label: "positive" | "negative" | "neutral"
      - score: float in [-1, 1]
      - confidence: float in [0, 1]
      - positive_hits: list[str]
      - negative_hits: list[str]
    """
    if not NLP_ENABLED or NLP_MODEL == "mock":
        return _mock_sentiment()

    pos_hits = [w for w in _POSITIVE_WORDS if w in text]
    neg_hits = [w for w in _NEGATIVE_WORDS if w in text]
    total = len(pos_hits) + len(neg_hits)

    if total == 0:
        return {
            "label": "neutral",
            "score": 0.0,
            "confidence": 0.5,
            "positive_hits": [],
            "negative_hits": [],
        }

    raw = (len(pos_hits) - len(neg_hits)) / total  # [-1, 1]
    confidence = min(total / 8.0, 1.0)  # saturates at 8 hits

    if raw > 0.2:
        label = "positive"
    elif raw < -0.2:
        label = "negative"
    else:
        label = "neutral"

    return {
        "label": label,
        "score": round(raw, 3),
        "confidence": round(confidence, 3),
        "positive_hits": pos_hits,
        "negative_hits": neg_hits,
    }


def extract_keywords(text: str, top_n: int = 5) -> list[str]:
    """
    Extract key financial terms from *text*.

    Uses TF-style scoring on Chinese word segments (character bigrams
    filtered against known financial vocabulary).  Returns up to
    *top_n* keyword strings.
    """
    if not NLP_ENABLED or NLP_MODEL == "mock":
        return ["示例关键词1", "示例关键词2"]

    # Build a pool of candidate phrases from all known lexicons
    candidates = set()
    candidates.update(_POSITIVE_WORDS)
    candidates.update(_NEGATIVE_WORDS)
    for terms in _ALERT_KEYWORDS.values():
        candidates.update(terms)

    # Count occurrences of each candidate in text
    scores: Counter[str] = Counter()
    for term in candidates:
        count = text.count(term)
        if count > 0:
            # longer terms weighted slightly higher
            scores[term] = count * (1.0 + len(term) * 0.02)

    return [word for word, _ in scores.most_common(top_n)]


def summarize_news(news_items: list[dict]) -> str:
    """
    Generate a brief summary paragraph from a list of news items.

    Each item should be a dict with at least a "title" key.
    """
    if not news_items:
        return "暂无新闻数据。"

    if not NLP_ENABLED or NLP_MODEL == "mock":
        return f"共 {len(news_items)} 条新闻 (mock 模式，未实际分析)。"

    # Collect titles and sentiment
    titles = []
    sentiments: Counter[str] = Counter()
    keywords: Counter[str] = Counter()

    for item in news_items:
        title = item.get("title", "")
        if title:
            titles.append(title)
            sent = analyze_sentiment(title)
            sentiments[sent["label"]] += 1
            for kw in extract_keywords(title, top_n=3):
                keywords[kw] += 1

    total = len(titles)
    if total == 0:
        return "暂无有效新闻标题可分析。"

    # Build summary
    sentiment_line = (
        f"积极 {sentiments.get('positive', 0)} 条, "
        f"消极 {sentiments.get('negative', 0)} 条, "
        f"中性 {sentiments.get('neutral', 0)} 条"
    )

    top_keywords = [kw for kw, _ in keywords.most_common(5)]
    keyword_line = "、".join(top_keywords) if top_keywords else "无显著关键词"

    return (
        f"近 {total} 条相关新闻中, {sentiment_line}。"
        f"热点关键词: {keyword_line}。"
    )


def classify_alert(text: str) -> str:
    """
    Classify *text* into one of the ALERT_TYPES categories.

    Returns the best-matching alert type string or "technical" as
    the fallback default.
    """
    if not NLP_ENABLED or NLP_MODEL == "mock":
        return "system"

    scores: dict[str, int] = {}
    for alert_type, keywords in _ALERT_KEYWORDS.items():
        scores[alert_type] = sum(1 for kw in keywords if kw in text)

    best = max(scores, key=lambda k: scores[k])  # type: ignore[arg-type]
    if scores[best] == 0:
        return "technical"  # safe fallback

    logger.debug(f"分类结果: {best} (scores={scores})")
    return best


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_sentiment() -> dict:
    """Return a neutral canned response when NLP is disabled or in mock mode."""
    return {
        "label": "neutral",
        "score": 0.0,
        "confidence": 0.0,
        "positive_hits": [],
        "negative_hits": [],
    }


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    test_texts = [
        "深圳华强放量涨停突破平台，机构买入评级上调，业绩超预期增长",
        "市场恐慌情绪蔓延，大盘暴跌，多股跌停，资金大幅流出",
        "今日沪深两市窄幅震荡，成交量与昨日持平",
    ]

    for i, text in enumerate(test_texts, 1):
        print(f"\n--- 测试 {i} ---")
        print(f"原文: {text}")
        sent = analyze_sentiment(text)
        print(f"情感: {sent}")
        kws = extract_keywords(text, top_n=5)
        print(f"关键词: {kws}")
        alert = classify_alert(text)
        print(f"告警类型: {alert}")

    # Test summarise
    fake_news = [
        {"title": "深圳华强放量涨停，突破前高"},
        {"title": "市场恐慌，大盘暴跌3%"},
        {"title": "公司发布年报，业绩超预期"},
    ]
    summary = summarize_news(fake_news)
    print(f"\n新闻摘要:\n{summary}")
