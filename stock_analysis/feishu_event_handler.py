"""
Feishu Event Subscription handler — AES-256-CBC decryption, URL verification,
and message event parsing.
"""
import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional

from config import FEISHU_ENCRYPT_KEY

logger = logging.getLogger("feishu_event")


def _aes_key() -> bytes:
    return hashlib.sha256(FEISHU_ENCRYPT_KEY.encode("utf-8")).digest()


def decrypt_event(encrypt_str: str) -> dict:
    """Decrypt a Feishu event payload (AES-256-CBC, PKCS7 padding).

    Ciphertext = base64( IV(16 bytes) + encrypted_data )
    Key = SHA-256(encrypt_key)
    """
    try:
        raw = base64.b64decode(encrypt_str)
    except Exception:
        logger.exception("Base64 decode failed")
        return {}
    if len(raw) < 17:
        logger.error("Ciphertext too short: %d bytes", len(raw))
        return {}
    iv = raw[:16]
    ciphertext = raw[16:]

    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
        cipher = Cipher(algorithms.AES(_aes_key()), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(ciphertext) + decryptor.finalize()
    except ImportError:
        # Pure-Python fallback — only works if pycryptodome is available,
        # otherwise the user must pip install cryptography
        from Crypto.Cipher import AES
        cipher = AES.new(_aes_key(), AES.MODE_CBC, iv=iv)
        padded = cipher.decrypt(ciphertext)
    except Exception:
        logger.exception("AES decrypt failed")
        return {}

    # Remove PKCS7 padding
    pad_len = padded[-1]
    if pad_len > 32 or pad_len == 0:
        logger.error("Bad padding byte: %d", pad_len)
        return {}
    plaintext = padded[:-pad_len]
    try:
        return json.loads(plaintext.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.exception("JSON parse after decrypt failed")
        return {}


def handle_url_verification(body: dict) -> Optional[dict]:
    """Handle Feishu URL verification challenge (one-time setup).

    Body: {"encrypt": "<base64_ciphertext>"}
    Returns: {"challenge": "<decrypted_challenge>"} or None
    """
    encrypt_str = body.get("encrypt", "")
    if not encrypt_str:
        logger.error("URL verification body missing 'encrypt'")
        return None
    decrypted = decrypt_event(encrypt_str)
    challenge = decrypted.get("challenge", "")
    if not challenge:
        logger.error("Decrypted challenge is empty")
        return None
    logger.info("URL verification successful")
    return {"challenge": challenge}


@dataclass
class MessageEvent:
    chat_id: str
    message_id: str
    content: str
    msg_type: str
    sender_open_id: str
    is_group: bool
    bot_mentioned: bool


def extract_message(event: dict, bot_open_id: str = "") -> Optional[MessageEvent]:
    """Parse a decrypted event dict into a MessageEvent, or None if not actionable.

    We only act on im.message.receive_v1 events in group chats where the bot
    is @mentioned *or* the message starts with a command prefix.
    """
    header = event.get("header", {})
    evt_type = header.get("event_type", "")
    if evt_type != "im.message.receive_v1":
        return None

    evt_data = event.get("event", {})
    msg = evt_data.get("message", {})
    if not msg:
        return None

    chat_type = msg.get("chat_type", "p2p")
    is_group = chat_type == "group"
    chat_id = msg.get("chat_id", "")

    msg_type = msg.get("msg_type", "text")
    raw_content = msg.get("content", "{}")
    try:
        content_json = json.loads(raw_content)
    except json.JSONDecodeError:
        content_json = {}

    text = content_json.get("text", "")
    title = content_json.get("title", "")

    # Check if bot is @mentioned
    mentions = msg.get("mentions", [])
    bot_mentioned = any(
        m.get("id", {}).get("open_id", "") == bot_open_id
        for m in mentions
    ) if mentions else False

    if not bot_mentioned:
        # Optionally accept "!ai " prefix commands
        if not text.strip().startswith("!ai"):
            return None

    combined = title + "\n" + text if title else text

    return MessageEvent(
        chat_id=chat_id,
        message_id=msg.get("message_id", ""),
        content=combined.strip(),
        msg_type=msg_type,
        sender_open_id=evt_data.get("sender", {}).get("sender_id", {}).get("open_id", ""),
        is_group=is_group,
        bot_mentioned=bot_mentioned,
    )
