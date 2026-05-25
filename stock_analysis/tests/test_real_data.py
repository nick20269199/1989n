"""
test_real_data.py — 真实数据冒烟测试

用 production 数据验证核心函数能正常工作。
不是 mock，是真数据。跑通了才算系统健康。

运行:
    /d/Python314/python -m pytest stock_analysis/tests/test_real_data.py -v
"""
import json
import pytest
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
ANALYSIS_DATA = Path("D:/1989n/stock_analysis/data")


def _read(path: Path):
    """Read JSON file, return (data, error)."""
    if not path.exists():
        return None, f"文件不存在: {path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as e:
        return None, f"JSON 解析失败: {e}"
    except OSError as e:
        return None, f"读取失败: {e}"


# ── 持仓数据 ──

def test_portfolio_json_parses():
    """portfolio.json 必须能解析为合法 JSON。"""
    data, err = _read(ANALYSIS_DATA / "portfolio.json")
    assert err is None, err


def test_portfolio_has_holdings():
    """portfolio.json 必须包含 holdings 列表。"""
    data, err = _read(ANALYSIS_DATA / "portfolio.json")
    if err:
        pytest.skip(err)
    assert isinstance(data, dict), "顶层应为 dict"
    assert "holdings" in data, "缺少 holdings"
    assert isinstance(data["holdings"], list), "holdings 应为 list"
    assert len(data["holdings"]) > 0, "holdings 不应为空"


def test_portfolio_each_holding_has_required_fields():
    """每只持仓必须包含 code/name/shares。"""
    data, err = _read(ANALYSIS_DATA / "portfolio.json")
    if err:
        pytest.skip(err)
    for i, h in enumerate(data.get("holdings", [])):
        assert isinstance(h, dict), f"holdings[{i}] 应为 dict"
        assert "code" in h, f"holdings[{i}] 缺少 code"
        assert "name" in h, f"holdings[{i}] 缺少 name"
        assert "shares" in h, f"holdings[{i}] 缺少 shares"
        assert isinstance(h["shares"], (int, float)), f"holdings[{i}].shares 应为数字"


def test_portfolio_holdings_have_unique_codes():
    """持仓代码不能重复。"""
    data, err = _read(ANALYSIS_DATA / "portfolio.json")
    if err:
        pytest.skip(err)
    codes = [h["code"] for h in data.get("holdings", []) if isinstance(h, dict)]
    assert len(codes) == len(set(codes)), f"重复的持仓代码: {codes}"


# ── A 股全列表 ──

def test_a_stock_list_parses():
    """a_stock_list.json 必须能解析。"""
    data, err = _read(STOCK_DATA / "a_stock_list.json")
    assert err is None, err


def test_a_stock_list_has_stocks():
    """a_stock_list.json 必须包含 stocks 列表。"""
    data, err = _read(STOCK_DATA / "a_stock_list.json")
    if err:
        pytest.skip(err)
    assert isinstance(data, dict), "顶层应为 dict"
    assert "stocks" in data, "缺少 stocks"
    assert isinstance(data["stocks"], list), "stocks 应为 list"
    assert len(data["stocks"]) > 0, "stocks 不应为空"


def test_portfolio_codes_exist_in_stock_list():
    """所有持仓代码必须在 a_stock_list 中存在。"""
    port, err_p = _read(ANALYSIS_DATA / "portfolio.json")
    stocks, err_s = _read(STOCK_DATA / "a_stock_list.json")
    if err_p or err_s:
        pytest.skip(f"数据文件缺失: {err_p or err_s}")

    stock_codes = {s["code"] for s in stocks.get("stocks", []) if isinstance(s, dict)}
    for h in port.get("holdings", []):
        assert h["code"] in stock_codes, f"持仓 {h['code']} {h['name']} 未在 A 股列表中找到"


# ── 通道健康 ──

def test_channel_health_parses():
    """channel_health_latest.json 必须能解析。"""
    data, err = _read(STOCK_DATA / "channel_health_latest.json")
    assert err is None, err


def test_channel_health_has_expected_fields():
    """通道健康文件必须包含 sina_stock/tencent/eastmoney。"""
    data, err = _read(STOCK_DATA / "channel_health_latest.json")
    if err:
        pytest.skip(err)
    for ch in ["sina_stock", "tencent", "eastmoney"]:
        assert ch in data, f"缺少通道 {ch}"
        assert isinstance(data[ch], bool), f"{ch} 应为 bool"


# ── 集合竞价 ──

def test_recent_call_auction_parses():
    """最近的 call_auction 文件能解析。"""
    files = sorted(STOCK_DATA.glob("call_auction_*.json"), reverse=True)
    if not files:
        pytest.skip("无 call_auction 文件")
    data, err = _read(files[0])
    assert err is None, f"{files[0].name}: {err}"


def test_recent_call_auction_has_portfolio_data():
    """最近的 call_auction 包含 portfolio_auction 列表。"""
    files = sorted(STOCK_DATA.glob("call_auction_*.json"), reverse=True)
    if not files:
        pytest.skip("无 call_auction 文件")
    data, err = _read(files[0])
    if err:
        pytest.skip(err)
    assert "portfolio_auction" in data, f"{files[0].name} 缺少 portfolio_auction"
    assert isinstance(data["portfolio_auction"], list), "portfolio_auction 应为 list"


# ── 盘中分析 ──

def test_recent_intraday_analysis_parses():
    """最近的 analysis_30min 文件能解析。"""
    files = sorted(STOCK_DATA.glob("analysis_30min_*.json"), reverse=True)
    if not files:
        pytest.skip("无 analysis_30min 文件")
    data, err = _read(files[0])
    assert err is None, f"{files[0].name}: {err}"


def test_recent_hot_stocks_parses():
    """hot_stocks.json 能解析。"""
    data, err = _read(STOCK_DATA / "hot_stocks.json")
    assert err is None, err


def test_recent_hot_stocks_has_top():
    """hot_stocks.json 包含 top 列表。"""
    data, err = _read(STOCK_DATA / "hot_stocks.json")
    if err:
        pytest.skip(err)
    assert "top" in data, "缺少 top"
    assert isinstance(data["top"], list), "top 应为 list"
