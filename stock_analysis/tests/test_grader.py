"""Grader 评分逻辑测试 — 纯函数（_try_parse_json, _ensure_passed）+ 空输入边界"""

import json
from pathlib import Path

import pytest

# 使用 relative import 会导致测试模块找不到 experts
# 直接 import experts.grader 需要正确设置 sys.path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from experts.grader import _try_parse_json, _ensure_passed, grade


# ── _try_parse_json（JSON 修复能力） ──────────────────────────────

def test_parse_normal_json():
    """标准 JSON → 直接解析成功"""
    text = '{"passed": true, "scores": {"direction": 0.8}}'
    result = _try_parse_json(text)
    assert result is not None
    assert result["passed"] is True
    assert result["scores"]["direction"] == 0.8


def test_parse_trailing_comma():
    """拖尾逗号 → 修复后解析"""
    text = '{"passed": true, "scores": {"direction": 0.8,}}'
    result = _try_parse_json(text)
    assert result is not None
    assert result["passed"] is True


def test_parse_bracket_brace_mismatch():
    """[... }（数组用大括号关闭）→ 修复（简单场景）"""
    text = '[0.8, 0.9 }'
    result = _try_parse_json(text)
    assert result is not None
    assert result == [0.8, 0.9]


def test_parse_reverse_mismatch():
    """{... ]（对象用中括号关闭）→ 修复（简单场景）"""
    text = '{"direction": 0.8]'
    result = _try_parse_json(text)
    assert result is not None
    assert result["direction"] == 0.8


def test_parse_completely_invalid():
    """完全无效 → None"""
    assert _try_parse_json("完全不是 JSON") is None
    assert _try_parse_json("") is None
    assert _try_parse_json("true") is not None  # valid JSON literal


def test_parse_fenced_json():
    """```json ... ``` 包裹 → 直接解析也可能失败（需要外部逻辑），这里测裸的"""
    text = '{"a": 1}'
    assert _try_parse_json(text) is not None


# ── _ensure_passed ────────────────────────────────────────────────

def test_passed_already_set():
    """passed 已设置 → 不覆盖"""
    result = {"passed": True, "average_score": 0.3, "scores": {"direction": 0.2}}
    _ensure_passed(result)
    assert result["passed"] is True  # 保持原值


def test_passed_computed_from_score():
    """passed 未设置 → 通过平均分+方向分计算"""
    result = {"average_score": 0.7, "scores": {"direction": 0.8}}
    _ensure_passed(result)
    assert result["passed"] is True


def test_passed_fails_low_score():
    """平均分 < min_score → passed=False"""
    import experts.grader as g
    old_min = g.GRADER_MIN_SCORE
    g.GRADER_MIN_SCORE = 0.5
    result = {"average_score": 0.3, "scores": {"direction": 0.8}}
    g._ensure_passed(result)
    assert result["passed"] is False
    g.GRADER_MIN_SCORE = old_min


def test_passed_fails_low_direction():
    """方向分 < 0.5 → passed=False"""
    result = {"average_score": 0.8, "scores": {"direction": 0.3}}
    _ensure_passed(result)
    assert result["passed"] is False


def test_passed_missing_scores():
    """scores 为空 → passed=False"""
    result = {"average_score": 0, "scores": {}}
    _ensure_passed(result)
    assert result["passed"] is False


# ── grade（空输入边界） ────────────────────────────────────────────

def test_grade_empty_experts():
    """空 expert_outputs → passed=False, 不调 API"""
    result = grade("000001", "平安银行", [])
    assert result["passed"] is False
    assert "error" in result


def test_grade_all_error_experts():
    """全部专家 error → 不调 API（理论上不会走到 call_llm）"""
    result = grade("000001", "平安银行", [
        {"expert_id": "expert1", "status": "error", "error": "API timeout"},
        {"expert_id": "expert2", "status": "error", "error": "rate limited"},
    ])
    assert result["passed"] is False


# ── save_grade_result ────────────────────────────────────────────

def test_save_grade_result(tmp_path: Path, monkeypatch):
    """保存评分结果 → 文件存在且含正确字段"""
    import experts.grader as g
    monkeypatch.setattr("experts.grader.OUTPUT_DIR", tmp_path)
    path = g.save_grade_result("000001", "平安银行", {"passed": True, "scores": {"direction": 0.9}})
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["passed"] is True
    assert path.name.startswith("000001_")
