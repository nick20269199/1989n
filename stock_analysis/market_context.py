"""
获取交易日期对应的市场背景数据：大盘指数、板块涨跌、资金流向
"""
import json
import os
import time
from datetime import datetime, date as date_type
from collections import defaultdict

import akshare as ak
import pandas as pd

DATA_DIR = "D:/1989n/stock_data"
START_DATE = "2024-10-01"
END_DATE = "2026-05-01"
START_DT = date_type(2024, 10, 1)
END_DT = date_type(2026, 5, 1)


def filter_by_date(df, date_col="date"):
    """过滤日期范围，兼容 datetime.date 和 str"""
    if df.empty:
        return df
    sample = df[date_col].iloc[0]
    if isinstance(sample, date_type):
        return df[(df[date_col] >= START_DT) & (df[date_col] <= END_DT)]
    else:
        return df[(df[date_col] >= START_DATE) & (df[date_col] <= END_DATE)]


def get_all_indices():
    """获取主要指数日线数据"""
    cache_path = os.path.join(DATA_DIR, "index_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cached = json.load(f)
        if cached.get("end_date", "") >= END_DATE:
            print("使用缓存的指数数据")
            return cached["data"]

    print("从AKShare获取指数数据...")
    indices = {}

    idx_config = [
        ("sh000001", "上证指数"),
        ("sz399001", "深证成指"),
        ("sz399006", "创业板指"),
        ("sh000688", "科创50"),
        ("sh000852", "中证1000"),
    ]

    for symbol, name in idx_config:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            df = filter_by_date(df)
            if not df.empty:
                indices[name] = df.to_dict("records")
                print(f"  {name}: {len(indices[name])} 条")
            time.sleep(0.5)
        except Exception as e:
            print(f"  {name}失败: {e}")

    with open(cache_path, "w") as f:
        json.dump({"end_date": END_DATE, "data": indices}, f, ensure_ascii=False, default=str)
    return indices


def get_north_flow():
    """北向资金历史流向"""
    cache_path = os.path.join(DATA_DIR, "north_flow_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cached = json.load(f)
        if cached.get("end_date", "") >= END_DATE:
            print("使用缓存的北向资金数据")
            return cached["data"]

    print("获取北向资金数据...")
    north = {}
    try:
        df = ak.stock_hsgt_hist_em(symbol="沪股通")
        df = filter_by_date(df, "日期")
        if not df.empty:
            north["沪股通"] = df.to_dict("records")
        time.sleep(0.5)
    except Exception as e:
        print(f"  沪股通失败: {e}")

    try:
        df = ak.stock_hsgt_hist_em(symbol="深股通")
        df = filter_by_date(df, "日期")
        if not df.empty:
            north["深股通"] = df.to_dict("records")
        time.sleep(0.5)
    except Exception as e:
        print(f"  深股通失败: {e}")

    try:
        df = ak.stock_hsgt_hist_em(symbol="北上")
        df = filter_by_date(df, "日期")
        if not df.empty:
            north["北向合计"] = df.to_dict("records")
    except Exception as e:
        print(f"  北向合计失败: {e}")

    print(f"  北向数据: {list(north.keys())}")
    with open(cache_path, "w") as f:
        json.dump({"end_date": END_DATE, "data": north}, f, ensure_ascii=False, default=str)
    return north


def get_sector_spot():
    """行业板块当前行情"""
    cache_path = os.path.join(DATA_DIR, "sector_spot_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cached = json.load(f)
        if cached.get("end_date", "") >= END_DATE:
            print("使用缓存的板块数据")
            return cached["data"]

    print("获取板块数据...")
    sectors = {}
    try:
        df = ak.stock_board_industry_name_em()
        sectors["行业板块"] = df.to_dict("records")
        print(f"  行业板块: {len(df)} 条")
    except Exception as e:
        print(f"  行业板块失败: {e}")

    try:
        df = ak.stock_board_concept_name_em()
        sectors["概念板块"] = df.to_dict("records")
        print(f"  概念板块: {len(df)} 条")
    except Exception as e:
        print(f"  概念板块失败: {e}")

    with open(cache_path, "w") as f:
        json.dump({"end_date": END_DATE, "data": sectors}, f, ensure_ascii=False, default=str)
    return sectors


def get_market_fund_flow():
    """市场整体资金流向（板块级别）"""
    cache_path = os.path.join(DATA_DIR, "market_fund_flow_cache.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cached = json.load(f)
        if cached.get("end_date", "") >= END_DATE:
            print("使用缓存的资金流向数据")
            return cached["data"]

    print("获取资金流向数据...")
    fund_data = {}

    try:
        df = ak.stock_market_fund_flow()
        fund_data["市场资金流向"] = df.to_dict("records")
        print(f"  市场资金流向: {len(df)} 条")
    except Exception as e:
        print(f"  市场资金流向失败: {e}")

    try:
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流向")
        fund_data["行业资金流向"] = df.to_dict("records")
        print(f"  行业资金流向: {len(df)} 条")
    except Exception as e:
        print(f"  行业资金流向失败: {e}")

    with open(cache_path, "w") as f:
        json.dump({"end_date": END_DATE, "data": fund_data}, f, ensure_ascii=False, default=str)
    return fund_data


def build_market_calendar(indices):
    """构建市场日历：每个交易日的大盘状态"""
    if "上证指数" not in indices:
        print("无上证指数数据，无法构建市场日历")
        return {}

    df = pd.DataFrame(indices["上证指数"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    # 计算技术指标
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["pct_chg"] = df["close"].pct_change() * 100
    df["volume_ma5"] = df["volume"].rolling(5).mean()
    df["volume_ratio"] = df["volume"] / df["volume_ma5"]

    # 市场状态判定
    calendar = {}
    for _, row in df.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        close = row["close"]

        # 趋势判定
        if pd.notna(row["ma20"]) and pd.notna(row["ma60"]):
            if close > row["ma20"] > row["ma60"]:
                trend = "多头排列"
            elif close < row["ma20"] < row["ma60"]:
                trend = "空头排列"
            elif close > row["ma20"]:
                trend = "短期偏多"
            elif close < row["ma20"]:
                trend = "短期偏空"
            else:
                trend = "震荡"
        else:
            trend = "数据不足"

        # 量能状态
        if pd.notna(row["volume_ratio"]):
            if row["volume_ratio"] > 1.5:
                volume_state = "放量"
            elif row["volume_ratio"] < 0.7:
                volume_state = "缩量"
            else:
                volume_state = "正常"
        else:
            volume_state = "未知"

        # 日内情绪: 基于涨跌幅
        if pd.notna(row["pct_chg"]):
            if row["pct_chg"] > 1.5:
                sentiment = "强势"
            elif row["pct_chg"] > 0:
                sentiment = "偏强"
            elif row["pct_chg"] > -1:
                sentiment = "偏弱"
            elif row["pct_chg"] > -3:
                sentiment = "弱势"
            else:
                sentiment = "恐慌"
        else:
            sentiment = "未知"

        calendar[date_str] = {
            "close": float(close),
            "pct_chg": round(float(row["pct_chg"]), 2) if pd.notna(row["pct_chg"]) else 0,
            "trend": trend,
            "volume_state": volume_state,
            "sentiment": sentiment,
            "ma5": round(float(row["ma5"]), 2) if pd.notna(row["ma5"]) else None,
            "ma20": round(float(row["ma20"]), 2) if pd.notna(row["ma20"]) else None,
            "ma60": round(float(row["ma60"]), 2) if pd.notna(row["ma60"]) else None,
        }

    return calendar


def main():
    print("=== 获取市场背景数据 ===\n")

    indices = get_all_indices()
    north = get_north_flow()
    sectors = get_sector_spot()
    fund_flow = get_market_fund_flow()

    # 构建市场日历
    calendar = build_market_calendar(indices)
    print(f"\n市场日历: {len(calendar)} 个交易日")

    # 保存市场日历
    cal_path = os.path.join(DATA_DIR, "market_calendar.json")
    with open(cal_path, "w") as f:
        json.dump(calendar, f, ensure_ascii=False, default=str)
    print(f"市场日历已保存: {cal_path}")

    # 统计趋势分布
    trends = defaultdict(int)
    for d, v in calendar.items():
        trends[v["trend"]] += 1
    print(f"\n趋势分布: {dict(trends)}")

    return calendar


if __name__ == "__main__":
    main()
