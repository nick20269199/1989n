"""保鲜盾逻辑测试 — 纯函数，覆盖所有边界"""

import json
import os
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from data_quality_gate import freshness_check, preflight_scan

CST = timezone(timedelta(hours=8))


# ── freshness_check ──────────────────────────────────────────────

def test_fresh_file_passes(tmp_path: Path):
    """文件最新 → pass"""
    f = tmp_path / "test.json"
    f.write_text("{}")
    time.sleep(0.05)  # ensure mtime delta
    result = freshness_check(f, max_hours=24)
    assert result["pass"] is True
    assert result["file"] == "test.json"
    assert 0 <= result["age_hours"] < 0.1


def test_stale_file_fails(tmp_path: Path):
    """文件过期 → fail"""
    f = tmp_path / "old.json"
    f.write_text("{}")
    old_mtime = datetime.now(CST).timestamp() - 7200  # 2h ago
    os.utime(f, (old_mtime, old_mtime))
    result = freshness_check(f, max_hours=1)
    assert result["pass"] is False
    assert result["age_hours"] >= 1


def test_exactly_at_threshold_passes(tmp_path: Path):
    """age < max_hours → pass（边界内）"""
    f = tmp_path / "edge.json"
    f.write_text("{}")
    old_mtime = datetime.now(CST).timestamp() - 3599  # 1s less than 1h
    os.utime(f, (old_mtime, old_mtime))
    result = freshness_check(f, max_hours=1)
    assert result["pass"] is True
    assert result["age_hours"] <= 1.0


def test_missing_file_returns_critical(tmp_path: Path):
    """文件不存在 → pass=False, severity=critical"""
    missing = tmp_path / "nonexistent.json"
    result = freshness_check(missing, max_hours=24)
    assert result["pass"] is False
    assert result["severity"] == "critical"
    assert result["age_hours"] == -1


def test_custom_max_hours_overrides_default(tmp_path: Path):
    """自定义阈值覆盖默认"""
    f = tmp_path / "custom.json"
    f.write_text("{}")
    old_mtime = datetime.now(CST).timestamp() - 120  # 2min ago
    os.utime(f, (old_mtime, old_mtime))
    result = freshness_check(f, max_hours=0.01)  # 0.01h = 36s
    assert result["pass"] is False  # 120s > 36s
    assert result["max_hours"] == 0.01


def test_zero_max_hours(tmp_path: Path):
    """max_hours=0 → 任何文件都过期（特殊场景：实时数据）"""
    f = tmp_path / "realtime.json"
    f.write_text("{}")
    result = freshness_check(f, max_hours=0)
    assert result["pass"] is False
    assert result["max_hours"] == 0


def test_none_severity_defaults_to_medium(tmp_path: Path):
    """不传 severity → 默认 medium"""
    f = tmp_path / "default_sev.json"
    f.write_text("{}")
    result = freshness_check(f, max_hours=24)
    assert result["severity"] == "medium"


# ── preflight_scan ───────────────────────────────────────────────

def test_all_fresh_returns_healthy(tmp_path: Path, monkeypatch):
    """全部新鲜 → healthy=True"""
    monkeypatch.setattr("data_quality_gate.STOCK_DATA", tmp_path)
    for name in ["a.json", "b.json"]:
        (tmp_path / name).write_text("{}")
    result = preflight_scan(["a.json", "b.json"])
    assert result["healthy"] is True
    assert len(result["checks"]) == 2
    assert all(c["pass"] for c in result["checks"])


def test_partial_stale_returns_unhealthy(tmp_path: Path, monkeypatch):
    """部分过期 → healthy=False"""
    monkeypatch.setattr("data_quality_gate.STOCK_DATA", tmp_path)
    (tmp_path / "fresh.json").write_text("{}")
    stale = tmp_path / "stale.json"
    stale.write_text("{}")
    old = datetime.now(CST).timestamp() - 90000  # 25h ago (> default 24h)
    os.utime(stale, (old, old))
    result = preflight_scan(["fresh.json", "stale.json"])
    assert result["healthy"] is False
    assert len(result["checks"]) == 2
    assert result["checks"][0]["pass"] is True
    assert result["checks"][1]["pass"] is False


def test_all_missing_returns_unhealthy(tmp_path: Path, monkeypatch):
    """全部缺失 → healthy=False，每条 severity=critical"""
    monkeypatch.setattr("data_quality_gate.STOCK_DATA", tmp_path)
    result = preflight_scan(["missing1.json", "missing2.json"])
    assert result["healthy"] is False
    assert all(c["severity"] == "critical" for c in result["checks"])


def test_unknown_file_uses_default_rules(tmp_path: Path, monkeypatch):
    """不在规则表里的文件 → 用默认阈值 24h"""
    monkeypatch.setattr("data_quality_gate.STOCK_DATA", tmp_path)
    f = tmp_path / "unknown_type.json"
    f.write_text("{}")
    result = preflight_scan(["unknown_type.json"])
    assert result["checks"][0]["max_hours"] == 24  # default
