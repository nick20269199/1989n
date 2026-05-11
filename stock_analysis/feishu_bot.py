"""
Feishu Group Bot — WebSocket long-connection mode via lark_oapi SDK.
No public URL or tunnel needed — SDK resolves internal WebSocket endpoint.
"""
import json
import logging
import sys
import threading
from pathlib import Path

from lark_oapi.ws import Client
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.core.enum import LogLevel
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BOT_CHAT_ID, FEISHU_ENCRYPT_KEY
from feishu_im_sender import send_text, send_card
from ai_router import dual_analyze

logger = logging.getLogger("feishu_bot")

PROJECT_DIR = Path(__file__).parent
BOT_OPEN_ID = "ou_22c94d299bc015d17b3db7a4f926c357"


def _on_im_message(event: P2ImMessageReceiveV1) -> None:
    """Handle incoming IM message events from WebSocket."""
    evt_data = event.event
    if not evt_data:
        return

    msg = evt_data.message
    if not msg:
        return

    chat_id = msg.chat_id or ""
    content_str = msg.content or "{}"

    try:
        content = json.loads(content_str)
    except json.JSONDecodeError:
        content = {}

    text = content.get("text", "")

    # Only respond when bot is @mentioned
    mentions = msg.mentions or []
    bot_mentioned = any(
        m.id and m.id.open_id == BOT_OPEN_ID
        for m in mentions
    )

    if not bot_mentioned:
        if not text.strip().startswith("!ai"):
            return

    logger.info("Processing: %s", text[:100])

    # Offload to background thread so we don't block the event loop
    def process():
        send_text(chat_id, "收到，正在分析...")
        response = dual_analyze(text)
        send_card(chat_id, "AI 分析", response)

    threading.Thread(target=process, daemon=True).start()


def main():
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(PROJECT_DIR / "bot.log", encoding="utf-8"),
        ],
    )

    handler = (
        EventDispatcherHandler
        .builder(FEISHU_ENCRYPT_KEY, "")
        .register_p2_im_message_receive_v1(_on_im_message)
        .build()
    )

    client = Client(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        log_level=LogLevel.INFO,
        event_handler=handler,
    )

    logger.info("=== Feishu Bot starting (WebSocket long-connection) ===")
    send_text(FEISHU_BOT_CHAT_ID, "机器人已上线 (WebSocket 长连接模式)")

    try:
        client.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception:
        logger.exception("Bot crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
