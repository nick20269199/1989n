"""
feishu_doc — Feishu Document Creator

把分析报告写成飞书文档（docx），不走卡片消息的长度限制。
通过 IM API 把文档链接推送到群里，点开就是完整内容。

用法:
    doc = FeishuDoc()
    url = doc.create_from_markdown("今日复盘", long_markdown_content)
    doc.send_to_chat(url, "今日复盘")
"""
import json
import logging
import re
import time
from datetime import datetime

import requests

from config import FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BOT_CHAT_ID
from feishu_im_sender import send_card

logger = logging.getLogger("feishu_doc")

# ── Feishu Open API ──
BASE_URL = "https://open.feishu.cn/open-apis"
DOCX_URL = f"{BASE_URL}/docx/v1/documents"
IM_MESSAGE_URL = f"{BASE_URL}/im/v1/messages"

# ── Block types (飞书服务端API数值枚举) ──
# 参考: https://open.feishu.cn/document/server-docs/docs/docx-v1/docx-structure
_BLOCK_TYPE = {
    "text": 2,       # 普通段落 (key="text")
    "heading1": 3, "heading2": 4, "heading3": 5,
    "heading4": 6, "heading5": 7, "heading6": 8,
    "heading7": 9, "heading8": 10, "heading9": 11,
    "bullet": 12, "ordered": 13,
    "code": 14, "quote": 15,
    "divider": 22,
}

BATCH_SIZE = 40  # blocks per API call (max 50)


# ═══════════════════════════════════════════════════════
# Token (reuse same cached token from feishu_im_sender)
# ═══════════════════════════════════════════════════════

def _get_token() -> str:
    """Get tenant_access_token (reuses cache from feishu_im_sender)."""
    from feishu_im_sender import _get_token as _im_token
    return _im_token()


# ═══════════════════════════════════════════════════════
# Document CRUD
# ═══════════════════════════════════════════════════════

def create_document(title: str) -> str:
    """Create an empty Feishu document. Returns document_id."""
    token = _get_token()
    if not token:
        raise RuntimeError("No Feishu token available")

    resp = requests.post(
        DOCX_URL,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"title": title},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Create doc failed: {data.get('msg', '')}")
    doc_id = data["data"]["document"]["document_id"]
    logger.info("Document created: %s (title=%s)", doc_id, title)
    return doc_id


def add_blocks(doc_id: str, blocks: list[dict], parent_id: str | None = None) -> None:
    """Add blocks to a document, auto-batching in groups of BATCH_SIZE."""
    if not blocks:
        return

    target_id = parent_id or doc_id
    url = f"{DOCX_URL}/{doc_id}/blocks/{target_id}/children"

    token = _get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    for i in range(0, len(blocks), BATCH_SIZE):
        batch = blocks[i:i + BATCH_SIZE]
        resp = requests.post(
            url,
            headers=headers,
            json={"children": batch, "index": -1},
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            logger.error("Add blocks batch %d failed: %s", i // BATCH_SIZE, data.get("msg", ""))
            continue
        logger.debug("Added blocks %d-%d", i, i + len(batch) - 1)


# ═══════════════════════════════════════════════════════
# Markdown → Feishu blocks
# ═══════════════════════════════════════════════════════

def _text_element(content: str, bold: bool = False, code: bool = False) -> dict:
    """Build a single text_element for inline content."""
    style = {}
    if bold:
        style["bold"] = True
    if code:
        style["inline_code"] = True
    return {
        "text_run": {
            "content": content,
            "text_element_style": style,
        }
    }


def _inline_parse(line: str) -> list[dict]:
    """Parse inline markdown (**bold**, `code`) into text_element list."""
    # Tokenize with regex
    pattern = r"(\*\*[^*]+\*\*|`[^`]+`|\[.*?\]\(.*?\)|[^*`]+)"
    elements = []
    for segment in re.findall(pattern, line):
        if segment.startswith("**") and segment.endswith("**"):
            elements.append(_text_element(segment[2:-2], bold=True))
        elif segment.startswith("`") and segment.endswith("`"):
            elements.append(_text_element(segment[1:-1], code=True))
        elif segment.startswith("[") and "](" in segment:
            # Link: [text](url)
            text = segment[1:segment.index("](")]
            url = segment[segment.index("](") + 2:-1]
            elements.append({
                "text_run": {
                    "content": text,
                    "text_element_style": {"link": {"url": url}},
                }
            })
        else:
            elements.append(_text_element(segment))
    return elements


_TEXT_KEYS = {"text", "heading1", "heading2", "heading3", "heading4",
               "heading5", "heading6", "heading7", "heading8", "heading9",
               "bullet", "ordered", "quote"}
_SIMPLE_BLOCKS = {"divider"}  # no elements needed


def _build_block(block_type: str, elements: list[dict] | None = None,
                 extra: dict | None = None) -> dict:
    """Build a block dict for the given type.

    Args:
        block_type: key in _BLOCK_TYPE (e.g. "text", "heading1", "bullet", "divider")
        elements: list of text_element dicts (used by text-like blocks)
        extra: extra fields merged into the block's content dict
    """
    block = {"block_type": _BLOCK_TYPE[block_type]}

    if block_type in _SIMPLE_BLOCKS:
        block[block_type] = extra or {}
        return block

    content = {}
    if elements:
        content["elements"] = elements
    # Text-like blocks need a style field
    if block_type in _TEXT_KEYS:
        content["style"] = extra.get("style", {}) if extra else {}
    # Code blocks: extra fields go into style sub-object
    if block_type == "code" and extra:
        content["style"] = extra

    block[block_type] = content
    return block


def markdown_to_blocks(md: str) -> list[dict]:
    """Convert markdown text to a list of Feishu block dicts.

    Handles: headings, paragraphs, bold, inline code, bullet lists,
    ordered lists, code fences, horizontal rules, quotes.
    """
    blocks: list[dict] = []
    lines = md.split("\n")
    i = 0
    in_code_block = False
    code_buffer: list[str] = []

    while i < len(lines):
        line = lines[i]

        # ── Code fence ──
        if line.strip().startswith("```"):
            if in_code_block:
                # Close code block
                blocks.append(_build_block("code", [
                    {"text_run": {"content": "\n".join(code_buffer),
                                  "text_element_style": {}}}
                ], extra={"language": 1, "wrap": True}))
                code_buffer = []
                in_code_block = False
            else:
                in_code_block = True
                # optional language specifier
                lang = line.strip().lstrip("`").strip()
                if lang not in ("", "text", "plain"):
                    pass  # language info available but Feishu uses language=-1 for auto
            i += 1
            continue

        if in_code_block:
            code_buffer.append(line)
            i += 1
            continue

        stripped = line.strip()

        # ── Empty line → skip ──
        if not stripped:
            i += 1
            continue

        # ── HR ──
        if re.match(r"^-{3,}$", stripped):
            blocks.append(_build_block("divider", []))
            i += 1
            continue

        # ── Quote ──
        if stripped.startswith(">"):
            content = stripped.lstrip(">").strip()
            blocks.append(_build_block("quote", _inline_parse(content)))
            i += 1
            continue

        # ── Headings ──
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            level = min(level, 9)  # Feishu supports up to heading9
            text = heading_match.group(2)
            blocks.append(_build_block(f"heading{level}", _inline_parse(text)))
            i += 1
            continue

        # ── Bullet list ──
        bullet_match = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet_match:
            blocks.append(_build_block("bullet", _inline_parse(bullet_match.group(1))))
            i += 1
            continue

        # ── Ordered list ──
        ordered_match = re.match(r"^\d+[\.\)]\s+(.+)$", stripped)
        if ordered_match:
            blocks.append(_build_block("ordered", _inline_parse(ordered_match.group(1))))
            i += 1
            continue

        # ── Table row (simplified: render as paragraphs) ──
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Render separator row silently
            if all(re.match(r"^[-:]+$", c) for c in cells if c):
                i += 1
                continue
            if cells:
                table_text = " | ".join(cells)
                blocks.append(_build_block("text", _inline_parse(table_text)))
                i += 1
                continue

        # ── Default: paragraph ──
        blocks.append(_build_block("text", _inline_parse(stripped)))
        i += 1

    # In case code block was never closed
    if in_code_block and code_buffer:
        blocks.append(_build_block("code", [
            {"text_run": {"content": "\n".join(code_buffer),
                          "text_element_style": {}}}
        ], extra={"language": 1, "wrap": True}))

    return blocks


# ═══════════════════════════════════════════════════════
# High-level: create doc from markdown + push to chat
# ═══════════════════════════════════════════════════════

_FEISHU_DOMAIN = "www.feishu.cn"


def set_domain(domain: str):
    """Override Feishu domain (e.g. 'bytedance.feishu.cn')."""
    global _FEISHU_DOMAIN
    _FEISHU_DOMAIN = domain


def create_from_markdown(title: str, content_md: str) -> str:
    """Create a Feishu doc from markdown content.

    Returns the doc URL.
    """
    # 1. Create empty doc
    doc_id = create_document(title)

    # 2. Convert markdown → blocks
    blocks = markdown_to_blocks(content_md)
    logger.info("Converting %d chars → %d blocks", len(content_md), len(blocks))

    if not blocks:
        # Add a placeholder so doc isn't empty
        blocks = [_build_block("text", _inline_parse("(空内容)"))]

    # 3. Add blocks
    add_blocks(doc_id, blocks)

    # 4. Build URL
    url = f"https://{_FEISHU_DOMAIN}/docx/{doc_id}"
    logger.info("Doc ready: %s", url)
    return url


def send_to_chat(doc_url: str, title: str, summary: str = "", chat_id: str = "") -> bool:
    """发送文档卡片到指定群聊"""
    target = chat_id or FEISHU_BOT_CHAT_ID
    if not target:
        logger.error("chat_id 未配置")
        return False

    link_md = f"[点此查看完整报告]({doc_url})"

    content_parts = [f"**{title}**"]
    if summary:
        content_parts.append(summary)
    content_parts.append("")
    content_parts.append(link_md)
    content_md = "\n".join(content_parts)

    return send_card(target, f"📄 {title}", content_md)


def publish_report(title: str, content_md: str, summary: str = "", chat_id: str = "") -> str | None:
    """创建飞书文档并推送到指定群聊。返回文档 URL 或 None。"""
    try:
        url = create_from_markdown(title, content_md)
        send_to_chat(url, title, summary, chat_id=chat_id)
        return url
    except Exception as e:
        logger.exception("publish_report 失败: %s", e)
        return None


# ═══════════════════════════════════════════════════════
# Self-test
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    test_md = """## 测试文档

这是一段**加粗文字**和一段`行内代码`。

- 列表项 1
- 列表项 2

1. 第一
2. 第二

```
code block
here
```

> 引用文字

---

| 列1 | 列2 |
| --- | --- |
| A   | B   |

生成时间: 2026-05-15
"""
    url = publish_report("FeishuDoc 自测", test_md, summary="如果你看到这篇文档，说明飞书文档模块工作正常。")
    if url:
        print(f"文档已创建: {url}")
    else:
        print("失败")
