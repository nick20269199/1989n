"""
Feishu ↔ Claude Code 双向桥接层

Inbox:  Bot v2 收到消息 → 写入 feishu_inbox.jsonl
Outbox: Claude Code 回复 → 写入 feishu_outbox.jsonl → Bot 自动发送

用法:
  from feishu_inbox import inbox_append, outbox_append, inbox_unread, outbox_flush
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("feishu_inbox")

STOCK_DATA = Path("D:/1989n/stock_data")
INBOX_FILE = STOCK_DATA / "feishu_inbox.jsonl"
OUTBOX_FILE = STOCK_DATA / "feishu_outbox.jsonl"
SENT_MARKER = STOCK_DATA / "feishu_sent.jsonl"  # 已发送归档

# ── Inbox: Bot → Claude ──────────────────────────────────────

def inbox_append(chat_id: str, user_text: str, dept: str = "unknown",
                 chat_type: str = "group", user_name: str = "") -> dict:
    """Bot 收到消息时调用，写入 inbox 供 Claude 读取。"""
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "chat_id": chat_id,
        "chat_type": chat_type,
        "user_name": user_name,
        "dept": dept,
        "text": user_text,
        "status": "unread",
    }
    try:
        with open(INBOX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("Inbox: [%s] %s", dept, user_text[:60])
    except Exception:
        logger.exception("Inbox write failed")
    return entry


def inbox_unread() -> list[dict]:
    """Claude Code 读取所有未读消息。"""
    if not INBOX_FILE.exists():
        return []
    entries = []
    try:
        with open(INBOX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if e.get("status") == "unread":
                        entries.append(e)
                except json.JSONDecodeError:
                    continue
    except Exception:
        logger.exception("Inbox read failed")
    return entries


def inbox_mark_read(entries: list[dict]) -> None:
    """将 inbox 中指定条目标记为已读。"""
    if not INBOX_FILE.exists() or not entries:
        return
    ts_set = {e.get("ts", "") for e in entries}
    try:
        lines = INBOX_FILE.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if e.get("ts", "") in ts_set:
                    e["status"] = "read"
                new_lines.append(json.dumps(e, ensure_ascii=False))
            except json.JSONDecodeError:
                new_lines.append(line)
        INBOX_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception:
        logger.exception("Inbox mark_read failed")


def inbox_stats() -> dict:
    """返回 inbox 统计。"""
    if not INBOX_FILE.exists():
        return {"total": 0, "unread": 0}
    total = 0
    unread = 0
    try:
        with open(INBOX_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                total += 1
                try:
                    if json.loads(line).get("status") == "unread":
                        unread += 1
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass
    return {"total": total, "unread": unread}


# ── Outbox: Claude → Bot → Feishu ────────────────────────────

def outbox_append(chat_id: str, content: str, reply_to_text: str = "") -> dict:
    """Claude Code 回复消息，写入 outbox 等待 Bot 发送。"""
    entry = {
        "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "chat_id": chat_id,
        "content": content,
        "reply_to": reply_to_text[:100],
        "sent": False,
    }
    try:
        with open(OUTBOX_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info("Outbox: [%s] %s", chat_id, content[:60])
    except Exception:
        logger.exception("Outbox write failed")
    return entry


def outbox_flush(send_func) -> int:
    """发送所有未发送的 outbox 消息。send_func(chat_id, content) → bool。"""
    if not OUTBOX_FILE.exists():
        return 0
    sent_count = 0
    try:
        lines = OUTBOX_FILE.read_text(encoding="utf-8").splitlines()
        new_lines = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                e = json.loads(line)
                if not e.get("sent", False):
                    ok = send_func(e["chat_id"], e["content"])
                    if ok:
                        e["sent"] = True
                        e["sent_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        sent_count += 1
                        # 归档
                        with open(SENT_MARKER, "a", encoding="utf-8") as sf:
                            sf.write(json.dumps(e, ensure_ascii=False) + "\n")
                new_lines.append(json.dumps(e, ensure_ascii=False))
            except json.JSONDecodeError:
                new_lines.append(line)
        OUTBOX_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception:
        logger.exception("Outbox flush failed")
    if sent_count:
        logger.info("Outbox flushed: %d sent", sent_count)
    return sent_count


# ── Outbox Watcher (后台线程，在 Bot v2 进程里跑) ─────────────

_watcher_running = False


def start_outbox_watcher(send_func, interval: float = 3.0) -> threading.Thread:
    """启动 outbox 监控线程，定期发送待发消息。"""
    global _watcher_running
    _watcher_running = True

    def _watch():
        logger.info("Outbox watcher started (interval=%.1fs)", interval)
        while _watcher_running:
            try:
                outbox_flush(send_func)
            except Exception:
                logger.exception("Outbox watcher error")
            time.sleep(interval)

    t = threading.Thread(target=_watch, name="outbox-watcher", daemon=True)
    t.start()
    return t


def stop_outbox_watcher():
    global _watcher_running
    _watcher_running = False
