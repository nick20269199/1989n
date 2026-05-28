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
from pathlib import Path

from feishu_im_sender import send_text as _im_send_text
from feishu_im_sender import send_card as _im_send_card
from config import FEISHU_BOT_CHAT_ID, FEISHU_ROUTES

logger = logging.getLogger("feishu_sender")

_SEND_ENABLED = os.getenv("FEISHU_SEND_ENABLED", "false").lower() in ("1", "true", "yes")

_MAX_MSGS_PER_MINUTE = 15
_send_timestamps: deque[float] = deque()


def _resolve_chat_id(route_or_id: str = "") -> str:
    """返回真实 chat_id：支持路由名（如 'news'）或原始 chat_id"""
    if not route_or_id:
        return FEISHU_BOT_CHAT_ID
    return FEISHU_ROUTES.get(route_or_id, route_or_id)


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


def send_feishu_message(title: str, content: str, chat_id: str = "") -> bool:
    """发送 Markdown 格式卡片消息 (标题 + 内容)。可指定群聊或路由名。"""
    target = _resolve_chat_id(chat_id)
    if not target:
        return False
    if not _SEND_ENABLED:
        logger.info(f"[飞书关] 跳过发送: {title}")
        return True
    _check_rate_limit()
    md = f"{content}\n\n---\n*{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
    return _im_send_card(target, title, md)


def send_feishu_card(title: str, sections: list[dict], chat_id: str = "") -> bool:
    """发送多段卡片消息，每段为 markdown/plain_text。可指定群聊或路由名。"""
    target = _resolve_chat_id(chat_id)
    if not target:
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
    return _im_send_card(target, title, md)


def send_feishu_alert(title: str, content: str, chat_id: str = "") -> bool:
    """发送高优先级告警消息 (红色标题)。可指定群聊或路由名。"""
    target = _resolve_chat_id(chat_id)
    if not target:
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
    return _im_send_card(target, alert_title, md, color="red")


def send_text_message(text: str, chat_id: str = "") -> bool:
    """发送纯文本消息。可指定群聊或路由名。"""
    target = _resolve_chat_id(chat_id)
    if not target:
        return False
    if not _SEND_ENABLED:
        logger.info(f"[飞书关] 跳过文本: {text[:50]}...")
        return True
    _check_rate_limit()
    return _im_send_text(target, text)


def send_midday_snapshot() -> bool:
    """推送午间行情快照到 midday 群。"""
    logger.info("推送午间行情快照")
    return send_feishu_message("午盘数据", "午间行情快照已生成。\n详细数据请查看桌面文件。", "midday")


def send_closing_brief() -> bool:
    """推送收盘数据简报到 closing 群。"""
    logger.info("推送收盘数据简报")
    return send_feishu_message("收盘数据", "收盘简报已生成。\n详细数据请查看桌面文件。", "closing")


def send_daily_brief() -> bool:
    """推送系统日报（任务数/命中率）到 daily_brief 群。"""
    logger.info("推送系统日报")
    digest_path = Path("D:/1989n/stock_data/status/daily_digest.md")
    if digest_path.exists():
        content = digest_path.read_text(encoding="utf-8")
    else:
        content = "每日摘要文件未生成。"
    return send_feishu_message("系统日报", content[:2000], "daily_brief")


def send_alert(msg: str) -> bool:
    """推送异常告警到 alerts 群（红色高优先级）。"""
    logger.info("推送系统告警")
    return send_feishu_alert("系统告警", msg, "alerts")


def send_kae_discovery() -> bool:
    """推送 KAE 管线摘要 + 缺口健康面板到 book 群。"""
    logger.info("推送 KAE 发现")
    kae_path = Path("D:/1989n/stock_data/status/kae_discoveries.md")
    digest_path = Path("D:/1989n/stock_data/status/daily_digest.md")
    sections = []

    # 管线摘要（优先用 daily_digest.md）
    if digest_path.exists():
        content = digest_path.read_text(encoding="utf-8")
        sections.append({"content": content[:2000]})
    elif kae_path.exists():
        content = kae_path.read_text(encoding="utf-8")
        sections.append({"content": content[:2000]})

    # 缺口健康面板
    try:
        gap_path = Path("D:/1989n/stock_data/knowledge/gap_registry.json")
        if gap_path.exists():
            import json
            gaps = json.loads(gap_path.read_text(encoding="utf-8"))
            total = len(gaps)
            by_status = {}
            by_priority = {}
            for g in gaps:
                s = g.get("status", "unknown")
                by_status[s] = by_status.get(s, 0) + 1
                p = g.get("priority", "P3")
                by_priority[p] = by_priority.get(p, 0) + 1

            panel = [
                "**缺口健康面板**",
                f"  总缺口: {total}",
            ]
            for s in ("open", "investigating", "absorbing", "absorbed", "closed"):
                if s in by_status:
                    panel.append(f"  {s}: {by_status[s]}")
            panel.append("")
            for p in ("P0", "P1", "P2", "P3"):
                if p in by_priority:
                    panel.append(f"  {p}: {by_priority[p]}")
            sections.append({"content": "\n".join(panel)})
    except Exception as e:
        logger.warning("缺口面板生成失败: %s", e)

    if not sections:
        sections.append({"content": "暂无 KAE 发现。"})
    return send_feishu_card("KAE 发现", sections, "book")


def send_deep_research() -> bool:
    """推送 KAE 深度发现/提案到 deep_research 群。"""
    logger.info("推送深度研究")
    return send_feishu_message("深度研究", "周度深度发现报告已生成。", "deep_research")


def send_investment_signal() -> bool:
    """推送情报信号/渠道报告到 investment 群。"""
    logger.info("推送投资分析")
    return send_feishu_message("投资分析", "情报信号已更新。", "investment")


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
