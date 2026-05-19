"""持仓加载测试 — portfolio.json 解析 + 后备方案"""

import json
from pathlib import Path

import pytest


# ── load_portfolio 测试（通过 monkeypatch PORTFOLIO_FILE） ─────

SAMPLE_HOLDING = {
    "code": "000981", "name": "山子高科", "shares": 8000, "cost": 4.411,
    "sector": "汽车零部件/房地产", "first_buy": "2026-05-15", "latest_buy": "2026-05-18",
}
SAMPLE_CLEARED = {"code": "000062", "name": "深圳华强", "closed_price": 37.20, "pnl": -160, "closed_date": "2026-05-12"}


def _write_portfolio(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_load_list_format(tmp_path: Path, monkeypatch):
    """portfolio.json 是 list [{...}] → 正确解析"""
    monkeypatch.setattr("daily_task.PORTFOLIO_FILE", tmp_path / "portfolio.json")
    _write_portfolio(tmp_path / "portfolio.json", [SAMPLE_HOLDING])
    from daily_task import load_portfolio
    result = load_portfolio()
    assert len(result) == 1
    assert result[0]["code"] == "000981"
    assert result[0]["shares"] == 8000


def test_load_dict_with_holdings_key(tmp_path: Path, monkeypatch):
    """portfolio.json 是 {"holdings": [...]} → 正确解析"""
    monkeypatch.setattr("daily_task.PORTFOLIO_FILE", tmp_path / "portfolio.json")
    _write_portfolio(tmp_path / "portfolio.json", {"holdings": [SAMPLE_HOLDING]})
    from daily_task import load_portfolio
    result = load_portfolio()
    assert len(result) == 1


def test_load_dict_with_data_key(tmp_path: Path, monkeypatch):
    """portfolio.json 是 {"data": [...]} → 正确解析"""
    monkeypatch.setattr("daily_task.PORTFOLIO_FILE", tmp_path / "portfolio.json")
    _write_portfolio(tmp_path / "portfolio.json", {"data": [SAMPLE_HOLDING]})
    from daily_task import load_portfolio
    result = load_portfolio()
    assert len(result) == 1


def test_normalize_holding_fields():
    """_normalize_holdings 标准化字段名 + 格式"""
    from daily_task import _normalize_holdings
    raw = [
        {"code": 981, "name": "山子高科", "shares": "8000", "cost": "4.411", "sector": "汽车零部件"},
        {"stock_code": "601789", "stock_name": "宁波建工", "shares": 5200, "cost": 6.206},
    ]
    result = _normalize_holdings(raw)
    assert len(result) == 2
    assert result[0]["code"] == "000981"  # zfill(6)
    assert result[0]["shares"] == 8000  # str → int
    assert result[0]["cost"] == 4.411  # str → float
    assert result[1]["code"] == "601789"


def test_normalize_filters_zero_shares():
    """_normalize_holdings 过滤 shars=0 的持仓"""
    from daily_task import _normalize_holdings
    raw = [
        {"code": "000001", "shares": 100, "cost": 10},
        {"code": "000002", "shares": 0, "cost": 20},  # 无效
        {"code": "000003", "shares": 0, "cost": 30},  # 无效
    ]
    result = _normalize_holdings(raw)
    assert len(result) == 1
    assert result[0]["code"] == "000001"


def test_normalize_filters_empty_code():
    """_normalize_holdings: 空 code → zfill 后变为 \"000000\"，不过滤"""
    from daily_task import _normalize_holdings
    raw = [
        {"code": "", "shares": 100, "cost": 10},
        {"code": "000001", "shares": 100, "cost": 10},
    ]
    result = _normalize_holdings(raw)
    assert len(result) == 2  # zfill("") → "000000" 是有效code
    assert result[1]["code"] == "000001"


def test_missing_portfolio_uses_fallback(tmp_path: Path, monkeypatch):
    """portfolio.json 不存在 → 走 fallback"""
    monkeypatch.setattr("daily_task.PORTFOLIO_FILE", tmp_path / "nonexistent.json")
    # 禁用 DB
    monkeypatch.setattr("daily_task._DB_AVAILABLE", False)
    from daily_task import load_portfolio
    result = load_portfolio()
    assert len(result) >= 6  # fallback 有至少6只


def test_corrupted_json_uses_fallback(tmp_path: Path, monkeypatch):
    """portfolio.json 损坏 → 走 fallback，不崩溃"""
    monkeypatch.setattr("daily_task.PORTFOLIO_FILE", tmp_path / "portfolio.json")
    (tmp_path / "portfolio.json").write_text("{bad json", encoding="utf-8")
    monkeypatch.setattr("daily_task._DB_AVAILABLE", False)
    from daily_task import load_portfolio
    result = load_portfolio()
    assert len(result) >= 6


def test_empty_holdings_list_uses_fallback(tmp_path: Path, monkeypatch):
    """portfolio.json 的 holdings 为空列表 → 走 fallback"""
    monkeypatch.setattr("daily_task.PORTFOLIO_FILE", tmp_path / "portfolio.json")
    _write_portfolio(tmp_path / "portfolio.json", {"holdings": []})
    monkeypatch.setattr("daily_task._DB_AVAILABLE", False)
    from daily_task import load_portfolio
    result = load_portfolio()
    assert len(result) >= 6


def test_real_portfolio_file_parses():
    """实际的 portfolio.json → 能正常解析，不抛异常"""
    from daily_task import load_portfolio
    from config import PORTFOLIO_FILE
    assert PORTFOLIO_FILE.exists(), f"{PORTFOLIO_FILE} not found"
    result = load_portfolio()
    assert len(result) >= 6
    for h in result:
        assert len(h["code"]) == 6  # all zfilled
        assert h["shares"] > 0
        assert h["cost"] > 0
