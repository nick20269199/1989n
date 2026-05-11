"""
Bridge message sender — routes NLP analysis outputs to Feishu.

Provides a thin orchestration layer that accepts structured messages
and delegates delivery to feishu_sender, while also supporting NLP
enrichment via bridge_nlp when available.
"""

from __future__ import annotations

import logging
from datetime import datetime

from bridge_config import BRIDGE_ENABLED, ALERT_TYPES, bridge_ready
from feishu_sender import (
    send_feishu_alert,
    send_feishu_card,
    send_feishu_message,
    send_text_message,
)

logger = logging.getLogger("bridge_sender")

# Optional NLP enrichment
_NLP_AVAILABLE = False
try:
    import bridge_nlp  # type: ignore[import-untyped]

    _NLP_AVAILABLE = True
except ImportError:
    logger.info("[bridge_sender] bridge_nlp 未加载，NLP 增强不可用")


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------

def send_bridge_message(msg_type: str, data: dict) -> bool:
    """
    Route a structured message through the bridge to Feishu.

    Supported *msg_type* values:
      - "text"     -> plain text push
      - "card"     -> multi-section card
      - "report"   -> formatted markdown report
      - "alert"    -> high-priority warning
      - "nlp_card" -> card with NLP sentiment + keywords prepended

    Returns True if the message was delivered successfully.
    """
    if not BRIDGE_ENABLED or not bridge_ready():
        logger.warning("[bridge_sender] Bridge 未就绪，消息丢弃")
        return False

    try:
        if msg_type == "text":
            return send_text_message(str(data.get("content", "")))

        elif msg_type == "card":
            title = str(data.get("title", ""))
            sections = data.get("sections", [])
            return send_feishu_card(title=title, sections=sections)

        elif msg_type == "report":
            title = str(data.get("title", "报告"))
            sections = data.get("sections", [])
            md = format_markdown_report(title, sections)
            return send_feishu_message(title=title, content=md)

        elif msg_type == "alert":
            alert_type = str(data.get("alert_type", "system"))
            message = str(data.get("message", ""))
            return broadcast_alert(alert_type, message)

        elif msg_type == "nlp_card":
            return _send_nlp_card(data)

        else:
            logger.warning(f"[bridge_sender] 未知消息类型: {msg_type}")
            return False

    except Exception:
        logger.exception(f"[bridge_sender] 发送 {msg_type} 消息时异常")
        return False


def broadcast_alert(alert_type: str, message: str) -> bool:
    """
    Broadcast an alert to all configured Feishu channels.

    *alert_type* must be one of the ALERT_TYPES defined in bridge_config.
    """
    if alert_type not in ALERT_TYPES:
        logger.warning(f"[bridge_sender] 未知告警类型: {alert_type}")
        alert_type = "system"

    label_map = {
        "price_break": "价格突破",
        "volume_surge": "放量告警",
        "technical": "技术指标",
        "risk": "风险告警",
        "system": "系统告警",
        "news": "新闻告警",
        "sentiment": "情绪告警",
    }
    display_name = label_map.get(alert_type, alert_type)

    full_content = f"**类型**: {display_name}\n\n{message}"
    return send_feishu_alert(title=f"{display_name} - {alert_type}", content=full_content)


def format_markdown_report(title: str, sections: list[dict]) -> str:
    """
    Build a Markdown report string from a title and list of sections.

    Each section dict should have:
      - heading: str (section title)
      - body: str (section body text)
    """
    lines = [f"# {title}", ""]
    for sec in sections:
        heading = sec.get("heading", "")
        body = sec.get("body", "")
        if heading:
            lines.append(f"## {heading}")
            lines.append("")
        if body:
            lines.append(body)
            lines.append("")
    lines.append(f"---\n*{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# NLP-enhanced helpers
# ---------------------------------------------------------------------------

def _send_nlp_card(data: dict) -> bool:
    """Send a card enriched with NLP sentiment and keywords."""
    title = str(data.get("title", "NLP 分析"))
    raw_text = str(data.get("content", ""))
    sections: list[dict] = []

    if _NLP_AVAILABLE and raw_text:
        sent = bridge_nlp.analyze_sentiment(raw_text)
        keywords = bridge_nlp.extract_keywords(raw_text, top_n=5)
        alert_type = bridge_nlp.classify_alert(raw_text)

        nlp_block = (
            f"**情感**: {sent['label']} (置信度 {sent['confidence']:.2f})\n"
            f"**关键词**: {'、'.join(keywords) if keywords else '无'}\n"
            f"**分类**: {alert_type}"
        )
        sections.append({"tag": "markdown", "content": nlp_block})

    sections.append({"tag": "markdown", "content": raw_text or "(无内容)"})
    return send_feishu_card(title=title, sections=sections)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not bridge_ready():
        logger.warning("FEISHU_WEBHOOK_URL 未配置，无法实际发送。以下为本地格式化测试。\n")

    # Test report formatting
    report = format_markdown_report(
        title="测试报告",
        sections=[
            {"heading": "行情概览", "body": "今日沪深300上涨0.5%，成交量略有放大。"},
            {"heading": "持仓分析", "body": "6只持仓中4涨2跌，整体盈亏+1.2%。"},
        ],
    )
    print(report)

    # Test bridge message (dry-run if no webhook)
    if bridge_ready():
        send_bridge_message("text", {"content": "bridge_sender 自测通过"})
        logger.info("bridge_sender 自测完成")
    else:
        logger.info("bridge_sender 格式化自测完成 (未连接飞书)")
