#!/usr/bin/env python3
"""
三倍量策略 — 抖音"开心"教学策略

流程:
  1. 每天收盘后找三倍量股票加自选
  2. 等缩量回踩均线
  3. 突破虚线(均线)时上车

策略来源: https://v.douyin.com/DtffR3tYz9A/
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

STOCK_DATA = Path("D:/1989n/stock_data")
LEARNING_DIR = STOCK_DATA / "learning"
OUTPUT_DIR = STOCK_DATA / "trade_plans"


def load_stock_list() -> list[dict]:
    """加载A股股票列表（通过新浪/腾讯，绕过东方财富WAF）"""
    cache_file = STOCK_DATA / "a_stock_list.json"
    if cache_file.exists():
        with open(cache_file, encoding="utf-8") as f:
            return json.load(f)

    # 通过新浪获取全市场列表
    try:
        import requests
        headers = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}
        # 获取所有A股列表 (新浪)
        url = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=5000&sort=symbol&asc=1&node=hs_a&symbol=&_s_r_a=page"
        resp = requests.get(url, headers=headers, timeout=15)
        data = resp.json()
        result = [{"代码": item["symbol"], "名称": item["name"], "最新价": float(item.get("trade", 0))} for item in data]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False)
        return result
    except Exception as e:
        print(f"新浪接口失败: {e}")
        # 备选: 腾讯
        try:
            url = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/HksecRank/js?type=1&market=1&offset=1&count=5000"
            resp = requests.get(url, headers=headers, timeout=15)
            # 腾讯接口比较简单，只返回基本的股票列表
            print("腾讯接口可用")
            return []
        except Exception:
            print("所有数据源不可用")
            return []


def find_triple_volume_candidates(
    volume_threshold: float = 3.0,
    lookback_days: int = 5,
    min_price: float = 5.0,
    max_price: float = 100.0,
) -> list[dict]:
    """
    三倍量初筛: 当日成交量是5日均量的3倍以上

    Args:
        volume_threshold: 量比阈值, 默认3倍
        lookback_days: 均量计算天数
        min_price: 最低股价过滤
        max_price: 最高股价过滤

    Returns:
        符合条件的候选股列表
    """
    try:
        import akshare as ak
    except ImportError:
        print("需要 akshare: pip install akshare")
        return []

    candidates = []
    all_stocks = load_stock_list()
    total = len(all_stocks)

    print(f"扫描{total}只股票, 寻找量比>{volume_threshold}倍...")

    for i, stock in enumerate(all_stocks):
        code = stock["代码"]
        name = stock["名称"]
        price = stock.get("最新价", 0)

        if price < min_price or price > max_price:
            continue

        if (i + 1) % 500 == 0:
            print(f"  进度: {i+1}/{total}")

        try:
            # 获取历史日K
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=(datetime.now() - timedelta(days=30)).strftime("%Y%m%d"),
                adjust="qfq",
            )
            if df.empty or len(df) < lookback_days + 1:
                continue

            # 计算量比: 当日量 / N日均量
            latest_vol = df["成交量"].iloc[-1]
            avg_vol = df["成交量"].tail(lookback_days + 1).head(lookback_days).mean()

            vol_ratio = latest_vol / avg_vol if avg_vol > 0 else 0

            if vol_ratio >= volume_threshold:
                candidates.append({
                    "code": code,
                    "name": name,
                    "price": float(price),
                    "vol_ratio": round(vol_ratio, 2),
                    "latest_vol": int(latest_vol),
                    "avg_vol": int(avg_vol),
                    "date": str(df["日期"].iloc[-1])[:10],
                })
        except Exception:
            continue

    candidates.sort(key=lambda x: x["vol_ratio"], reverse=True)
    return candidates


def check_shrink_to_ma(candidates: list[dict]) -> list[dict]:
    """
    缩量回均线确认: 检查候选股是否出现缩量回踩均线

    Args:
        candidates: 三倍量初筛结果

    Returns:
        符合缩量回踩条件的股票
    """
    try:
        import akshare as ak
    except ImportError:
        return []

    confirmed = []
    print(f"\n检查{candidates}只候选股是否缩量回均线...")

    for c in candidates[:20]:  # 只看前20只
        try:
            df = ak.stock_zh_a_hist(
                symbol=c["code"],
                period="daily",
                start_date=(datetime.now() - timedelta(days=30)).strftime("%Y%m%d"),
                adjust="qfq",
            )
            if df.empty or len(df) < 10:
                continue

            # 计算均线
            df["MA5"] = df["收盘"].rolling(5).mean()
            df["MA10"] = df["收盘"].rolling(10).mean()
            df["MA20"] = df["收盘"].rolling(20).mean()

            # 最近的N根K线
            recent = df.tail(5)

            # 条件1: 缩量 (最近一日量 < 前5日均量的1.5倍)
            recent_avg_vol = recent["成交量"].head(4).mean()
            latest_vol_ratio = recent["成交量"].iloc[-1] / recent_avg_vol if recent_avg_vol > 0 else 999

            # 条件2: 价格在均线附近 (±3%)
            latest_close = recent["收盘"].iloc[-1]
            near_ma5 = abs(latest_close - recent["MA5"].iloc[-1]) / recent["MA5"].iloc[-1] < 0.03
            near_ma10 = abs(latest_close - recent["MA10"].iloc[-1]) / recent["MA10"].iloc[-1] < 0.03

            if latest_vol_ratio < 1.5 and (near_ma5 or near_ma10):
                c["vol_shrink_ratio"] = round(latest_vol_ratio, 2)
                c["near_ma5"] = round(recent["MA5"].iloc[-1], 2)
                c["near_ma10"] = round(recent["MA10"].iloc[-1], 2)
                c["close"] = round(latest_close, 2)
                c["last_date"] = str(df["日期"].iloc[-1])[:10]
                confirmed.append(c)

        except Exception:
            continue

    return confirmed


def generate_report(
    candidates: list[dict],
    confirmed: list[dict],
) -> str:
    """生成策略报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"# 三倍量策略日报 — {now}",
        "",
        f"扫描范围: 全A股",
        f"初筛(量比>3倍): {len(candidates)}只",
        f"确认(缩量回均线): {len(confirmed)}只",
        "",
        "---",
        "## 使用说明",
        "",
        "1. **每天收盘后**运行此脚本, 找三倍量股票",
        "2. 加入自选后观察**缩量回踩均线**(MA5/MA10)",
        "3. 缩量回踩+ **突破均线** = 上车信号",
        "4. 止损: 跌破均线-3% 或 入场价-5%",
        "5. 止盈: 前高 或 +8~15%",
        "",
        "---",
        "## 三倍量初筛名单",
        "",
    ]

    if candidates:
        lines.append("| 代码 | 名称 | 量比 | 现价 | 日期 |")
        lines.append("|------|------|------|------|------|")
        for c in candidates[:30]:
            lines.append(
                f"| {c['code']} | {c['name']} | {c['vol_ratio']:.1f}x | "
                f"{c['price']:.2f} | {c.get('date', '')} |"
            )
    else:
        lines.append("今日无三倍量候选。")

    lines += ["", "---", "## 缩量回均线确认 (优先关注)", ""]

    if confirmed:
        lines.append("| 代码 | 名称 | 量比 | 现价 | MA5 | MA10 | 缩量比 |")
        lines.append("|------|------|------|------|------|------|--------|")
        for c in confirmed:
            lines.append(
                f"| {c['code']} | {c['name']} | {c['vol_ratio']:.1f}x | "
                f"{c['close']:.2f} | {c.get('near_ma5', '-')} | "
                f"{c.get('near_ma10', '-')} | {c.get('vol_shrink_ratio', '-')}x |"
            )
    else:
        lines.append("暂无符合缩量回踩条件的股票。")

    lines += [
        "",
        "---",
        "## 策略来源",
        "",
        "抖音 @开心",
        "链接: https://v.douyin.com/DtffR3tYz9A/",
        "免责: 历史图形仅供欣赏, 不作为投资依据",
    ]

    return "\n".join(lines)


def main():
    print("=" * 50)
    print("  三倍量策略扫描仪")
    print("  抖音 @开心 教学策略")
    print("=" * 50)

    # Step 1: 三倍量初筛
    candidates = find_triple_volume_candidates()
    print(f"\n初筛结果: {len(candidates)}只三倍量股票")

    if not candidates:
        print("今日无三倍量候选。")
        report = generate_report([], [])
    else:
        print("\n--- TOP 10 三倍量 ---")
        for c in candidates[:10]:
            print(f"  {c['code']} {c['name']}  量比={c['vol_ratio']:.1f}x  现价={c['price']:.2f}")

        # Step 2: 缩量回均线检查
        confirmed = check_shrink_to_ma(candidates)
        print(f"\n缩量回踩确认: {len(confirmed)}只")

        if confirmed:
            print("\n--- 优先关注 ---")
            for c in confirmed:
                print(f"  {c['code']} {c['name']}  回踩MA{c['near_ma5'] if c.get('near_ma5') else c.get('near_ma10')}")

        report = generate_report(candidates, confirmed)

    # 保存报告
    date_str = datetime.now().strftime("%Y%m%d_%H%M")
    report_file = OUTPUT_DIR / f"sanbei_strategy_{date_str}.md"
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"\n报告已保存: {report_file}")
    print(report)


if __name__ == "__main__":
    main()
