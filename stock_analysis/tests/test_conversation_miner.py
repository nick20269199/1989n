"""Test: conversation_miner JSONL parsing and signal extraction.

Tests the pure parsing functions (extract_user_intent, extract_assistant_action)
and the session extraction from JSONL lines.
Does NOT test the full scan → extract → analyze → synthesize pipeline (integration).
"""
import json
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from conversation_miner import (
    extract_user_intent,
    extract_assistant_action,
    extract_session_from_jsonl,
)


# ── extract_user_intent ──────────────────────────────────────


def test_user_intent_plain_string():
    """普通字符串消息 → 提取内容"""
    msg = {"type": "user", "message": "分析一下002156"}
    assert extract_user_intent(msg) == "分析一下002156"


def test_user_intent_dict_content():
    """dict 类型 message → 提取 content 字段"""
    msg = {"type": "user", "message": {"content": "持仓情况如何"}}
    assert extract_user_intent(msg) == "持仓情况如何"


def test_user_intent_list_blocks():
    """list 类型 message（多文本块）→ 拼接"""
    msg = {"type": "user", "message": [
        {"text": "看下"},
        {"text": "大盘走势"},
    ]}
    result = extract_user_intent(msg)
    assert "看下" in result
    assert "大盘走势" in result


def test_user_intent_list_dict_with_content():
    """list 中用 content 字段的块 → 也能提取"""
    msg = {"type": "user", "message": [
        {"content": "第一段"},
        {"content": "第二段"},
    ]}
    result = extract_user_intent(msg)
    assert "第一段" in result
    assert "第二段" in result


def test_user_intent_nested_content_list():
    """content 本身是列表（嵌套内容块）→ 提取 text 类型"""
    msg = {"type": "user", "message": {"content": [
        {"type": "text", "text": "深度分析"},
        {"type": "text", "text": "通富微电"},
    ]}}
    result = extract_user_intent(msg)
    assert "深度分析" in result
    assert "通富微电" in result


def test_user_intent_string_content_nested_list():
    """message 是 string，但 content 是嵌套列表"""
    msg = {"type": "user", "message": "检查持仓"}
    assert extract_user_intent(msg) == "检查持仓"


def test_user_intent_caveat_filtered():
    """local-command-caveat → 返回空字符串"""
    msg = {"type": "user", "message": "<local-command-caveat>skip</local-command-caveat>"}
    assert extract_user_intent(msg) == ""


def test_user_intent_none_message():
    """message 为 None → 返回空字符串"""
    assert extract_user_intent({"type": "user", "message": None}) == ""


def test_user_intent_short_content():
    """内容 < 3 字符 → 返回空"""
    assert extract_user_intent({"type": "user", "message": "a"}) == ""
    assert extract_user_intent({"type": "user", "message": "ab"}) == ""


def test_user_intent_whitespace_only():
    """纯空白 → 返回空"""
    assert extract_user_intent({"type": "user", "message": "   "}) == ""


def test_user_intent_fallback_str():
    """非标准类型 → str() 兜底"""
    msg = {"type": "user", "message": 12345}
    assert extract_user_intent(msg) == "12345"


# ── extract_assistant_action ─────────────────────────────────


def test_assistant_tool_use():
    """tool_use 块 → 提取工具名和输入"""
    msg = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "tool_use", "name": "Read", "input": {"file_path": "test.py"}},
            ]
        },
    }
    result = extract_assistant_action(msg)
    assert "[tool:Read]" in result
    assert "test.py" in result


def test_assistant_text():
    """text 块 → 提取文本内容"""
    msg = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "根据分析，该股处于上升趋势"},
            ]
        },
    }
    result = extract_assistant_action(msg)
    assert "上升趋势" in result


def test_assistant_mixed():
    """混合 text + tool_use → 都提取"""
    msg = {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "开始分析"},
                {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            ]
        },
    }
    result = extract_assistant_action(msg)
    assert "开始分析" in result
    assert "[tool:Bash]" in result


def test_assistant_empty_content():
    """空 content → 返回空字符串"""
    msg = {"type": "assistant", "message": {"content": []}}
    assert extract_assistant_action(msg) == ""


def test_assistant_string_message():
    """message 是字符串 → 直接作为文本"""
    msg = {"type": "assistant", "message": "简单回复"}
    assert extract_assistant_action(msg) == "简单回复"


def test_assistant_truncates_long_text():
    """超过200字符的 text → 截断"""
    long_text = "x" * 300
    msg = {"type": "assistant", "message": {"content": [{"type": "text", "text": long_text}]}}
    result = extract_assistant_action(msg)
    assert len(result) <= 210  # 200 + " | "


# ── extract_session_from_jsonl ───────────────────────────────


SAMPLE_LINES = [
    json.dumps({"type": "user", "message": "hello", "timestamp": "2026-01-01T00:00:00", "sessionId": "s1"}),
    json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi there"}]}, "timestamp": "2026-01-01T00:00:01", "sessionId": "s1"}),
    json.dumps({"type": "queue-operation", "content": "scheduled task ran", "timestamp": "2026-01-01T00:00:02", "sessionId": "s1"}),
    # second session
    json.dumps({"type": "user", "message": "analyze stock", "timestamp": "2026-01-02T00:00:00", "sessionId": "s2"}),
    # invalid JSON line
    "not json at all",
    # empty line (should be skipped)
    "",
    # user with no message (should be skipped)
    json.dumps({"type": "user", "message": None, "timestamp": "2026-01-02T00:00:01", "sessionId": "s2"}),
]


def test_extract_sessions_basic():
    """正常 JSONL → 提取多会话，过滤无效行"""
    content = "\n".join(SAMPLE_LINES)
    with patch("pathlib.Path.open", mock_open(read_data=content)):
        fp = Path("/fake/test.jsonl")
        sessions = extract_session_from_jsonl(fp)

    assert len(sessions) == 2
    s1 = [s for s in sessions if s["session_id"] == "s1"][0]
    s2 = [s for s in sessions if s["session_id"] == "s2"][0]

    assert len(s1["entries"]) == 3
    assert s1["entries"][0]["role"] == "user"
    assert s1["entries"][1]["role"] == "assistant"
    assert s1["entries"][2]["role"] == "system"
    assert "[scheduled] scheduled task ran" in s1["entries"][2]["content"]

    assert len(s2["entries"]) == 1  # "analyze stock" included, None message skipped
    assert s2["entries"][0]["content"] == "analyze stock"


def test_extract_sessions_start_line():
    """指定 start_line → 跳过前面的行"""
    content = "\n".join(SAMPLE_LINES)
    with patch("pathlib.Path.open", mock_open(read_data=content)):
        fp = Path("/fake/test.jsonl")
        # 跳过前3行（s1会话），只处理 s2
        sessions = extract_session_from_jsonl(fp, start_line=3)

    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "s2"


def test_extract_session_truncation():
    """超过60条交互 → 截断为 30 + ... + 30"""
    many_lines = []
    for i in range(70):
        many_lines.append(json.dumps({
            "type": "user" if i % 2 == 0 else "assistant",
            "message": f"msg {i}",
            "timestamp": f"2026-01-01T00:{i//60:02d}:{i%60:02d}",
            "sessionId": "long_session",
        }))
    content = "\n".join(many_lines)

    with patch("pathlib.Path.open", mock_open(read_data=content)):
        fp = Path("/fake/test.jsonl")
        sessions = extract_session_from_jsonl(fp)

    assert len(sessions) == 1
    entries = sessions[0]["entries"]
    assert len(entries) == 61  # 30 + 1(...) + 30
    assert entries[30]["role"] == "..."


def test_extract_session_invalid_json():
    """JSONDecodeError 行 → 跳过，不中断"""
    lines_with_error = [
        json.dumps({"type": "user", "message": "valid", "timestamp": "00:00", "sessionId": "s1"}),
        "{broken json",
        json.dumps({"type": "user", "message": "after error", "timestamp": "00:01", "sessionId": "s1"}),
    ]
    content = "\n".join(lines_with_error)
    with patch("pathlib.Path.open", mock_open(read_data=content)):
        fp = Path("/fake/test.jsonl")
        sessions = extract_session_from_jsonl(fp)

    assert len(sessions) == 1
    assert len(sessions[0]["entries"]) == 2
