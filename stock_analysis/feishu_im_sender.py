"""
Feishu IM API sender — post messages to chats via tenant_access_token.
"""
import json
import logging
import threading
import time
from typing import Optional

import requests

from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_BOT_CHAT_ID,
)

logger = logging.getLogger("feishu_im")

IM_MESSAGE_URL = "https://open.feishu.cn/open-apis/im/v1/messages"
TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
TOKEN_TTL = 7000  # safety margin below real 7200
REQUEST_TIMEOUT = 15

_lock = threading.Lock()
_cached_token: str = ""
_token_expiry: float = 0.0


def _get_token() -> str:
    global _cached_token, _token_expiry
    now = time.time()
    if _cached_token and now < _token_expiry:
        return _cached_token
    with _lock:
        if _cached_token and now < _token_expiry:
            return _cached_token
        try:
            r = requests.post(
                TOKEN_URL,
                json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
        except Exception:
            logger.exception("Failed to fetch tenant_access_token")
            return ""
        if data.get("code") != 0:
            logger.error("Token API error: %s", data.get("msg", ""))
            return ""
        _cached_token = data["tenant_access_token"]
        _token_expiry = now + TOKEN_TTL
        return _cached_token


def send_text(chat_id: str, text: str) -> bool:
    """Send a plain-text message to a Feishu chat."""
    token = _get_token()
    if not token:
        logger.error("No token, cannot send message")
        return False
    try:
        r = requests.post(
            IM_MESSAGE_URL + "?receive_id_type=chat_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            logger.error("Send text failed: %s", data.get("msg", ""))
            return False
        logger.info("Message sent to %s", chat_id)
        return True
    except Exception:
        logger.exception("send_text error")
        return False


def send_card(chat_id: str, title: str, content_md: str, color: str = "blue") -> bool:
    """Send a card message (Markdown inside) to a Feishu chat."""
    token = _get_token()
    if not token:
        return False
    card = {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": title},
            "template": color,
        },
        "elements": [
            {"tag": "markdown", "content": content_md},
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {"tag": "plain_text", "content": "以上分析由 AI 生成，仅供参考，不构成投资建议"}
                ],
            },
        ],
    }
    try:
        r = requests.post(
            IM_MESSAGE_URL + "?receive_id_type=chat_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card, ensure_ascii=False),
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        if data.get("code") != 0:
            logger.error("Send card failed: %s", data.get("msg", ""))
            return False
        logger.info("Card sent to %s", chat_id)
        return True
    except Exception:
        logger.exception("send_card error")
        return False


def reply_text(chat_id: str, reply_to_msg_id: str, text: str) -> bool:
    """Reply to a specific message in chat."""
    token = _get_token()
    if not token:
        return False
    try:
        r = requests.post(
            IM_MESSAGE_URL + "?receive_id_type=chat_id",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("code") == 0
    except Exception:
        logger.exception("reply_text error")
        return False
