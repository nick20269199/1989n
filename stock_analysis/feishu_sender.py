"""
Feishu (Lark) Message Sender
发送飞书消息 — 基于 IM API (tenant_access_token)，无需 webhook。

支持:
- Markdown 文本消息
- 卡片消息 (Card)
- 紧急告警消息 (红色高优先级)

Rate Limit: ~20 条/分钟
"""
import logging
import time
from collections import deque
from datetime import datetime

import os

from feishu_im_sender import send_text as _im_send_text
from feishu_im_sender import send_card as _im_send_card
from config import FEISHU_BOT_CHAT_ID

logger = logging.getLogger("feishu_sender")

_SEND_ENABLED = os.getenv("FEISHU_SEND_ENABLED", "false").lower() in ("1", "true", "yes")

_MAX_MSGS_PER_MINUTE = 15
_send_timestamps: deque[float] = deque()


def _check_rate_limit() -> None:
    now = time.time()
    window_start = now - 60.0
    while _send_timestamps and _send_timestamps[0] < window_start:
        _send_timestamps.popleft()
    if len(_send_timestamps) >= _MAX_MSGS_PER_MINUTE:
        wait_time = _send_timestamps[0] - window_start + 1.0
        if wait_time > 0:
            logger.info(f"[速率限制] 等待 {wait_time:.1f}s")
            time.sleep(wait_time)
        _send_timestamps.popleft()
    _send_timestamps.append(now)


def _validate_config() -> bool:
    if not FEISHU_BOT_CHAT_ID:
        logger.error("[飞书] FEISHU_BOT_CHAT_ID 未配置")
        return False
    return True


def send_feishu_message(title: str, content: str) -> bool:
    """发送 Markdown 格式卡片消息 (标题 + 内容)。"""
    if not _validate_config():
        return False
    if not _SEND_ENABLED:
        logger.info(f"[飞书关] 跳过发送: {title}")
        return True
    _check_rate_limit()
    md = f"{content}\n\n---\n*{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
    return _im_send_card(FEISHU_BOT_CHAT_ID, title, md)


def send_feishu_card(title: str, sections: list[dict]) -> bool:
    """发送多段卡片消息，每段为 markdown/plain_text。"""
    if not _validate_config():
        return False
    if not _SEND_ENABLED:
        logger.info(f"[飞书关] 跳过发送卡片: {title}")
        return True
    _check_rate_limit()
    lines = []
    for sec in sections:
        content = sec.get("content", "")
        if content:
            lines.append(content)
    md = "\n\n".join(lines)
    return _im_send_card(FEISHU_BOT_CHAT_ID, title, md)


def send_feishu_alert(title: str, content: str) -> bool:
    """发送高优先级告警消息 (红色标题)。"""
    if not _validate_config():
        return False
    if not _SEND_ENABLED:
        logger.info(f"[飞书关] 跳过告警: {title}")
        return True
    _check_rate_limit()
    alert_title = f"!! {title}"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = (
        f"**<font color='red'>[紧急告警]</font>**\n\n"
        f"{content}\n\n---\n告警时间: {timestamp}"
    )
    return _im_send_card(FEISHU_BOT_CHAT_ID, alert_title, md, color="red")


def send_text_message(text: str) -> bool:
    """发送纯文本消息 (最简单形式)。"""
    if not _validate_config():
        return False
    if not _SEND_ENABLED:
        logger.info(f"[飞书关] 跳过文本: {text[:50]}...")
        return True
    _check_rate_limit()
    return _im_send_text(FEISHU_BOT_CHAT_ID, text)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    logger.info("飞书发送器自测...")
    test_ok = send_feishu_message(
        title="Feishu Sender 自测",
        content=(
            "**状态**: 正常\n"
            f"**时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            "如果你看到这条消息，说明飞书 IM API 配置正确。"
        ),
    )
    if test_ok:
        logger.info("飞书发送器自测通过")
    else:
        logger.warning("飞书发送器自测失败")
