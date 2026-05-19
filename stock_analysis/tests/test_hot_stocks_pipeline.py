"""涨停池数据转换测试 — mock akshare, 验证转换逻辑"""

import json
from datetime import datetime
from pathlib import Path

import pytest


# ── 模拟 akshare 返回的 DataFrame（通过 mock 的 iterrows 模拟） ──

def make_mock_zt_df(rows: list[dict]) -> object:
    """构造 mock DataFrame，模拟 .empty, .iterrows(), .columns"""
    class MockIter:
        def __init__(self, data):
            self._data = data
            self._idx = 0
        def __iter__(self):
            return self
        def __next__(self):
            if self._idx >= len(self._data):
                raise StopIteration
            i = self._idx
            self._idx += 1
            return i, self._data[i]

    class MockZT:
        empty = len(rows) == 0
        def __init__(self, rows):
            self._rows = rows
        def iterrows(self):
            return MockIter(self._rows)

    return MockZT(rows)


def test_normal_zt_pool_conversion(monkeypatch):
    """标准涨停板数据 → 正确转换"""
    import daily_task

    mock_rows = [
        {"代码": "000001", "名称": "平安银行", "最新价": 12.5, "涨跌幅": 10.01, "成交额": 5.2e8, "总市值": 2.4e10, "换手率": 3.5},
        {"代码": "000002", "名称": "万科A",    "最新价": 8.3,  "涨跌幅": 9.98,  "成交额": 3.1e8, "总市值": 1.2e10, "换手率": 2.1},
    ]
    monkeypatch.setattr("akshare.stock_zt_pool_em", lambda date: make_mock_zt_df(mock_rows))

    result = daily_task.fetch_hot_stocks_zt_pool()
    assert len(result) == 2
    assert result[0]["code"] == "000001"
    assert result[0]["name"] == "平安银行"
    assert result[0]["price"] == 12.5
    assert result[0]["change_pct"] == 10.01
    assert result[0]["sources"] == ["涨停板池"]
    assert result[1]["code"] == "000002"


def test_empty_zt_pool_returns_empty_list(monkeypatch):
    """涨停池为空 → []"""
    import daily_task
    monkeypatch.setattr("akshare.stock_zt_pool_em", lambda date: make_mock_zt_df([]))
    assert daily_task.fetch_hot_stocks_zt_pool() == []


def test_akshare_api_failure_returns_empty(monkeypatch):
    """akshare 抛异常 → [] 不崩溃"""
    import daily_task

    def _crash(*a, **kw):
        raise ConnectionError("API timeout")

    monkeypatch.setattr("akshare.stock_zt_pool_em", _crash)
    assert daily_task.fetch_hot_stocks_zt_pool() == []


def test_missing_columns_uses_defaults(monkeypatch):
    """缺少某些列 → 用默认值填补，不崩溃"""
    import daily_task

    mock_rows = [
        {"代码": "000001", "名称": "平安银行", "最新价": 12.5, "涨跌幅": 10.01},  # 缺成交额/总市值/换手率
    ]
    monkeypatch.setattr("akshare.stock_zt_pool_em", lambda date: make_mock_zt_df(mock_rows))

    result = daily_task.fetch_hot_stocks_zt_pool()
    assert len(result) == 1
    assert result[0]["amount"] == 0  # 缺字段默认为0
    assert result[0]["market_cap"] == 0
    assert result[0]["turnover_rate"] == 0


def test_column_name_variation_handled(monkeypatch):
    """akshare 列名变体 → 容错（get 而不是下标）"""
    import daily_task

    # 模拟列名变化："涨跌幅"→"涨幅"
    mock_rows = [
        {"代码": "000001", "名称": "平安银行", "最新价": 12.5, "涨幅": 9.99,
         "成交额": 5e8, "总市值": 2e10, "换手率": 2.0},
    ]
    monkeypatch.setattr("akshare.stock_zt_pool_em", lambda date: make_mock_zt_df(mock_rows))

    result = daily_task.fetch_hot_stocks_zt_pool()
    # 列名不匹配时 get 返回 0，但不应崩溃
    assert len(result) == 1
    assert result[0]["change_pct"] == 0  # "涨幅" 不是 "涨跌幅"，get不到


def test_nan_values_handled(monkeypatch):
    """0值字段 → 转换后各字段默认为0"""
    import daily_task
    mock_rows = [
        {"代码": "000001", "名称": "平安银行", "最新价": 0, "涨跌幅": 0,
         "成交额": 0, "总市值": 0, "换手率": 0},
    ]
    monkeypatch.setattr("akshare.stock_zt_pool_em", lambda date: make_mock_zt_df(mock_rows))

    result = daily_task.fetch_hot_stocks_zt_pool()
    assert len(result) == 1
    assert result[0]["price"] == 0
    assert result[0]["turnover_rate"] == 0


# ── collect_hot_stocks 多源合并 ─────────────────────────────────

def test_collect_hot_stocks_dedup(monkeypatch):
    """多源合并 → 同code去重，合并sources"""
    import daily_task

    calls = {"zt": 0, "em": 0, "jqka": 0}

    def mock_zt(*a, **kw):
        calls["zt"] += 1
        return make_mock_zt_df([{"代码": "000001", "名称": "平安银行", "最新价": 12.5, "涨跌幅": 10.0, "成交额": 1, "总市值": 1, "换手率": 1}])

    def mock_em(*a, **kw):
        calls["em"] += 1
        return [{"code": "000001", "name": "平安银行", "price": 12.5, "change_pct": 10.0, "rank": 1, "sources": ["东方财富"]}]

    def mock_jqka(*a, **kw):
        calls["jqka"] += 1
        return [{"code": "000001", "name": "平安银行", "price": 12.5, "change_pct": 10.0, "rank": 1, "sources": ["同花顺"]}]

    monkeypatch.setattr("akshare.stock_zt_pool_em", mock_zt)
    monkeypatch.setattr("daily_task.fetch_hot_stocks_eastmoney", mock_em)
    monkeypatch.setattr("daily_task.fetch_hot_stocks_10jqka", mock_jqka)

    result = daily_task.collect_hot_stocks()
    assert len(result) == 1  # 去重后只有1条
    assert len(result[0]["sources"]) == 3  # 三个来源合并
    assert "涨停板池" in result[0]["sources"]
    assert "东方财富" in result[0]["sources"]
    assert "同花顺" in result[0]["sources"]
