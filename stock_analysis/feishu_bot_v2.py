"""
feishu_bot_v2.py — 飞书 Bot v2 双向通信

v2 改进:
  - 部门路由: 6个部门 + 通用AI fallback
  - @mention 过滤: 只回复明确 @bot 或私聊的消息
  - 数据准确性: 全部走 data_source_router / dept_handlers
  - 自动重连: WebSocket 断线指数退避重连
  - 健康监控: 心跳日志 + 重启守护兼容

用法: python feishu_bot_v2.py
"""
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from lark_oapi.ws import Client
from lark_oapi.event.dispatcher_handler import EventDispatcherHandler
from lark_oapi.core.enum import LogLevel
from lark_oapi.api.im.v1.model.p2_im_message_receive_v1 import P2ImMessageReceiveV1

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BOT_CHAT_ID, FEISHU_ENCRYPT_KEY
from feishu_im_sender import send_text, send_card
from dept_handlers import route_message

logger = logging.getLogger("feishu_bot_v2")

PROJECT_DIR = Path(__file__).parent
RESPONSES_DIR = PROJECT_DIR / "responses"
RESPONSES_DIR.mkdir(exist_ok=True)
STATE_FILE = PROJECT_DIR / "bot_v2_state.json"

# Bot 自身 open_id (从飞书应用详情获取)
BOT_OPEN_ID = os.environ.get("BOT_OPEN_ID", "ou_22c94d299bc015d17b3db7a4f926c357")

# 重连配置
MAX_RECONNECT_DELAY = 300       # 最大重连间隔 (秒)
INITIAL_RECONNECT_DELAY = 5    # 初始重连间隔 (秒)
RECONNECT_BACKOFF = 2          # 指数退避倍数

# ── 状态持久化 ──
_reconnect_count = 0
_start_time: str = ""


def _save_state() -> None:
    try:
        STATE_FILE.write_text(json.dumps({
            "start_time": _start_time,
            "reconnect_count": _reconnect_count,
            "last_heartbeat": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False), "utf-8")
    except Exception:
        pass


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text("utf-8"))
    except Exception:
        pass
    return {}


# ── @mention 解析 ──

def _parse_message_content(content_str: str) -> tuple[str, list[str], bool]:
    """解析飞书消息 content JSON。

    返回: (清理后的文本, 被@的用户open_id列表, 是否@所有人)
    """
    try:
        content = json.loads(content_str)
    except (json.JSONDecodeError, TypeError):
        return content_str, [], False

    text = content.get("text", "")
    mentions = content.get("mentions", [])
    mentioned_ids = []
    at_all = False

    for m in mentions:
        if isinstance(m, dict):
            key = m.get("key", "")
            uid = m.get("id", {}).get("open_id", m.get("id", ""))
            if uid:
                mentioned_ids.append(uid)
            if key == "@_all" or "所有人" in str(m.get("name", "")):
                at_all = True
            # 从文本中移除 @mention 标记
            text = text.replace(key, "").strip()

    return text.strip(), mentioned_ids, at_all


def _is_bot_mentioned(mentioned_ids: list[str], at_all: bool) -> bool:
    """检查 bot 是否被 @mention。"""
    if at_all:
        return True
    return BOT_OPEN_ID in mentioned_ids


def _strip_at_prefixes(text: str) -> str:
    """移除文本中残留的 @xxx 格式标记。"""
    import re
    # 移除 @_user_xxx 格式
    text = re.sub(r'@_user_\w+', '', text)
    # 移除 @所有人
    text = text.replace('@所有人', '')
    return text.strip()


# ── 响应保存 ──

def _save_response(query: str, response: str, dept: str, chat_id: str) -> None:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M:%S")
    file_path = RESPONSES_DIR / f"{date_str}_v2.md"
    entry = (
        f"--- {time_str} [{dept}] ---\n"
        f"用户: {query}\n"
        f"Bot v2 [{dept}] (chat_id: {chat_id}):\n{response}\n\n"
    )
    try:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception:
        logger.exception("保存问答记录失败")


# ── 消息处理 ──

def _on_im_message(event: P2ImMessageReceiveV1) -> None:
    """WebSocket IM 消息事件处理。"""
    evt_data = event.event
    if not evt_data:
        return

    msg = evt_data.message
    if not msg:
        return

    chat_id = msg.chat_id or ""
    chat_type = getattr(msg, "chat_type", "group")
    content_str = msg.content or "{}"

    # 解析消息内容
    text, mentioned_ids, at_all = _parse_message_content(content_str)
    text = _strip_at_prefixes(text)

    if not text.strip():
        logger.debug("Empty message after stripping mentions, skip")
        return

    # bot 是否应该回复: p2p 私聊自动回复, 群聊需要 @bot
    if chat_type == "p2p":
        logger.info("[p2p] Processing: %s", text[:80])
    elif _is_bot_mentioned(mentioned_ids, at_all):
        logger.info("[group@bot] Processing: %s", text[:80])
    else:
        logger.debug("Bot not mentioned in group, skip: %s", text[:50])
        return

    # 后台线程处理，不阻塞 WebSocket 事件循环
    def process():
        try:
            result = route_message(text, chat_id)
        except Exception as e:
            logger.exception("route_message failed")
            result = {
                "title": "系统错误",
                "content": f"消息处理异常: {e}\n请稍后重试。",
                "source": "dept:error",
            }

        dept = result.get("source", "dept:unknown")
        content = result.get("content", "无内容")
        title = result.get("title", "回复")

        _save_response(text, content, dept, chat_id)

        # 发送回复: 优先 text (可靠简洁)
        try:
            send_text(chat_id, content)
        except Exception:
            logger.exception("send_text failed, retry with card")
            try:
                send_card(chat_id, title, content, color="blue")
            except Exception:
                logger.exception("send_card also failed")

    threading.Thread(target=process, daemon=True).start()


# ── 主循环 (含自动重连) ──

def _build_client() -> Client:
    handler = (
        EventDispatcherHandler
        .builder(FEISHU_ENCRYPT_KEY, "")
        .register_p2_im_message_receive_v1(_on_im_message)
        .build()
    )
    return Client(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        log_level=LogLevel.INFO,
        event_handler=handler,
    )


def main():
    global _start_time, _reconnect_count

    log_file = os.environ.get("BOT_V2_LOG_FILE") or str(PROJECT_DIR / "bot_v2.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )

    _start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("=== Feishu Bot v2 starting at %s ===", _start_time)

    # 启动通知
    try:
        send_text(FEISHU_BOT_CHAT_ID, f"[Bot v2] 上线 {_start_time}\n6部门路由已激活: 前厅/情报/工程/财务/研发/读书郎")
    except Exception:
        logger.warning("启动通知发送失败")

    delay = INITIAL_RECONNECT_DELAY

    while True:
        try:
            client = _build_client()
            logger.info("WebSocket connecting (reconnect_count=%d)...", _reconnect_count)
            _save_state()
            client.start()
        except KeyboardInterrupt:
            logger.info("Bot v2 stopped by user")
            _save_state()
            sys.exit(0)
        except Exception:
            _reconnect_count += 1
            logger.exception("WebSocket disconnected (count=%d), reconnecting in %ds...",
                             _reconnect_count, delay)
            _save_state()

            # 指数退避
            time.sleep(delay)
            delay = min(delay * RECONNECT_BACKOFF, MAX_RECONNECT_DELAY)

    # 正常退出
    logger.info("Bot v2 exiting")
    sys.exit(0)


if __name__ == "__main__":
    main()
