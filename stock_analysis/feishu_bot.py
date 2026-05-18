"""
Feishu Group Bot — WebSocket long-connection mode via lark_oapi SDK.
支持多 Bot 模式（primary/passive）+ 回复自动分类。
"""
import datetime
import json
import logging
import os
import sys
import threading
from pathlib import Path

from lark_oapi.ws import Client
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.core.enum import LogLevel
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BOT_CHAT_ID, FEISHU_ENCRYPT_KEY
from feishu_im_sender import send_text, send_card
from feishu_claude_agent import process_message

logger = logging.getLogger("feishu_bot")

PROJECT_DIR = Path(__file__).parent
RESPONSES_DIR = PROJECT_DIR / "responses"
RESPONSES_DIR.mkdir(exist_ok=True)
BOT_OPEN_ID = "ou_22c94d299bc015d17b3db7a4f926c357"
BOT_MODE = os.environ.get("BOT_MODE", "primary")  # primary | passive
BOT_NAME = os.environ.get("BOT_NAME", "")

# 分类 → 卡片颜色映射
CATEGORY_COLORS = {
    "📊 行情分析": "blue",
    "📈 持仓报告": "green",
    "⚠️ 风险提醒": "red",
    "💬 问答": "indigo",
}
DEFAULT_CATEGORY = "💬 问答"
DEFAULT_COLOR = "blue"


def _parse_category(response: str) -> tuple[str, str, str]:
    """解析回复中的分类标签，返回 (分类, 标题, 正文)"""
    lines = response.strip().split("\n", 2)
    first_line = lines[0].strip()

    if first_line in CATEGORY_COLORS:
        category = first_line
        title = category  # 直接用 emoji + 分类名做标题
        body = lines[2].strip() if len(lines) > 2 else lines[1].strip() if len(lines) > 1 else ""
    else:
        category = DEFAULT_CATEGORY
        title = "AI 分析"
        body = response.strip()

    return category, title, body


def _should_respond(event) -> bool:
    """判断当前 Bot 是否应该回复此消息"""
    if BOT_MODE == "primary":
        return True

    # passive 模式：只回复 1-on-1 私聊
    msg = event.event.message
    if msg and getattr(msg, "chat_type", "") == "p2p":
        return True

    return False


def _save_response(query: str, response: str, chat_id: str) -> None:
    """保存每次问答记录到本地文件（响应者/每日归档）"""
    now = datetime.datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    file_path = RESPONSES_DIR / f"{date_str}_{BOT_NAME or 'bot'}.md"
    entry = (
        f"--- {time_str} ---\n"
        f"用户: {query}\n"
        f"Bot [{BOT_NAME}] (chat_id: {chat_id}):\n{response}\n\n"
    )
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        logger.exception("保存问答记录失败")


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

    # Skip empty messages
    if not text.strip():
        return

    # 多 Bot 去重：passive 模式不回复群消息
    if not _should_respond(event):
        logger.debug("Passive mode, skipping: %s", text[:50])
        return

    logger.info("[%s] Processing: %s", BOT_NAME or "bot", text[:100])

    # Offload to background thread so we don't block the event loop
    def process():
        # 直接处理，不发送"收到"中间消息
        response = process_message(text, chat_id=chat_id)
        # 本地持久化保存
        _save_response(text, response, chat_id)
        category, title, body = _parse_category(response)
        color = CATEGORY_COLORS.get(category, DEFAULT_COLOR)
        try:
            send_card(chat_id, title, body, color=color)
        except Exception:
            logger.exception("Failed to send card, falling back to text")
            send_text(chat_id, response)

    threading.Thread(target=process, daemon=True).start()


def main():
    log_file = os.environ.get("BOT_LOG_FILE") or str(PROJECT_DIR / "bot.log")
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
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

    mode_label = f"【{BOT_MODE}】" if BOT_MODE != "primary" else ""
    logger.info("=== Feishu Bot [%s] %s starting ===", BOT_NAME or "?", mode_label)

    # 启动通知（失败不阻止 Bot 运行）
    try:
        startup_msg = f"机器人 [{BOT_NAME}] {mode_label}已上线" if BOT_NAME else "机器人已上线"
        send_text(FEISHU_BOT_CHAT_ID, startup_msg)
    except Exception:
        logger.warning("发送启动消息失败（可能 Bot 未加入群聊）")

    try:
        client.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception:
        logger.exception("Bot crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()
