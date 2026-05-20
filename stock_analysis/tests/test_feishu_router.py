"""Test: feishu_sender route resolution and rate limiting.

Tests _resolve_chat_id routing logic and rate limiter.
Does NOT test actual API calls (external dependency, mocked).
"""
import time
from unittest.mock import patch, MagicMock

import pytest

from feishu_sender import _resolve_chat_id, _validate_config, _check_rate_limit
from feishu_sender import _send_timestamps, _MAX_MSGS_PER_MINUTE
from feishu_sender import send_feishu_message, send_feishu_alert, send_feishu_card


# ── _resolve_chat_id ─────────────────────────────────────────


def test_resolve_empty_returns_default():
    """空字符串 → 返回默认 FEISHU_BOT_CHAT_ID"""
    chat_id = _resolve_chat_id("")
    assert chat_id == "oc_983693a765e4284d1dc7bbeaf56cf1a9"


def test_resolve_route_name_returns_mapped():
    """已知路由名 → 返回映射的 chat_id"""
    chat_id = _resolve_chat_id("alerts")
    assert chat_id == "oc_2c82fb2d0b3c326a3edd0e413dcb5089"


def test_resolve_unknown_route_returns_input():
    """未知路由名 → 原样返回（passthrough）"""
    chat_id = _resolve_chat_id("unknown_group")
    assert chat_id == "unknown_group"


def test_resolve_direct_chat_id_returns_as_is():
    """直接传 chat_id → 原样返回"""
    direct = "oc_direct_chat_id_test"
    assert _resolve_chat_id(direct) == direct


def test_resolve_all_routes():
    """所有已配置路由名都能正确解析"""
    routes = ["main", "book", "news", "midday", "closing", "alerts", "overnight"]
    for route in routes:
        chat_id = _resolve_chat_id(route)
        assert chat_id != route, f"Route '{route}' should map to a different chat_id"
        assert chat_id.startswith("oc_"), f"Route '{route}' mapped to invalid chat_id format"


# ── _validate_config ─────────────────────────────────────────


def test_validate_config_with_chat_id():
    """FEISHU_BOT_CHAT_ID 已配置 → True"""
    assert _validate_config() is True


# ── _check_rate_limit ────────────────────────────────────────


def test_rate_limit_under_threshold():
    """未达速率上限 → 不阻塞"""
    _send_timestamps.clear()
    start = time.time()
    _check_rate_limit()
    elapsed = time.time() - start
    assert elapsed < 1.0
    assert len(_send_timestamps) == 1


def test_rate_limit_clear_expired():
    """超过1分钟的旧时间戳被清理"""
    _send_timestamps.clear()
    old = time.time() - 120.0
    for _ in range(20):
        _send_timestamps.append(old)
    _check_rate_limit()
    assert len([t for t in _send_timestamps if t < time.time() - 60.0]) == 0


# ── send_feishu_message (routing only, no API) ──────────────


@patch("feishu_sender._im_send_card", return_value=True)
@patch("feishu_sender._SEND_ENABLED", True)
def test_send_message_with_route_name(mock_send):
    """路由名 'alerts' → 解析为 alerts 群 chat_id 再发送"""
    result = send_feishu_message("Test Title", "Test Content", "alerts")
    assert result is True
    mock_send.assert_called_once()
    args, _ = mock_send.call_args
    assert args[0] == "oc_2c82fb2d0b3c326a3edd0e413dcb5089"


@patch("feishu_sender._im_send_card", return_value=True)
@patch("feishu_sender._SEND_ENABLED", True)
def test_send_alert_default_route(mock_send):
    """告警不指定路由 → 发到默认群"""
    result = send_feishu_alert("Alert!", "Something wrong")
    assert result is True
    mock_send.assert_called_once()
    args, _ = mock_send.call_args
    assert args[0] == "oc_983693a765e4284d1dc7bbeaf56cf1a9"


@patch("feishu_sender._im_send_card", return_value=True)
@patch("feishu_sender._SEND_ENABLED", True)
def test_send_card_with_route_name(mock_send):
    """多段卡片 + 路由名 'closing' → 发到收盘群"""
    sections = [{"content": "段1"}, {"content": "段2"}]
    result = send_feishu_card("Card Title", sections, "closing")
    assert result is True
    mock_send.assert_called_once()
    args, _ = mock_send.call_args
    assert args[0] == "oc_afc63ec9893d4f3393bfe5cb64203e72"


@patch("feishu_sender._SEND_ENABLED", False)
def test_send_disabled_skips():
    """FEISHU_SEND_ENABLED=false → 跳过发送，返回 True"""
    result = send_feishu_message("Test", "Content", "alerts")
    assert result is True
