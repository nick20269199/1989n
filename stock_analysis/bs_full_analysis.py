"""
全量BS点分析：合并所有年份交易数据 + 大盘/板块/资金背景
覆盖 2021-2026 共5年+
"""
import json
import os
import time
from collections import defaultdict
from datetime import datetime, date as date_type

import openpyxl
import akshare as ak
import pandas as pd
import numpy as np

DATA_DIR = "D:/1989n/stock_data"
EASTMONEY_DIR = "D:/东方财富"

# ============================================================
# 第一步: 加载和标准化所有数据源
# ============================================================

def load_new_format(filepath):
    """加载22列格式的东方财富数据"""
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[4] is None:
            continue
        trade_type = str(row[5])
        if trade_type not in ('证券买入', '证券卖出'):
            continue
        # 交收日期, 发生日期, 发生时间, 证券代码, 证券名称, 交易类别,
        # 成交数量, 成交均价, 成交金额, 发生金额, 佣金, 其他费用, 印花税, 过户费,
        # 股份余额, 资金余额, 成交编号, 股东账号, 流水号, 交易市场, 币种, 其他
        qty = int(row[6]) if row[6] else 0
        price = float(row[7]) if row[7] else 0
        amount = float(row[8]) if row[8] else 0
        net_amount = float(row[9]) if row[9] else 0  # 发生金额(含费用)
        commission = float(row[10]) if row[10] else 0
        stamp_tax = float(row[12]) if row[12] else 0
        transfer_fee = float(row[13]) if row[13] else 0

        if qty <= 0:
            continue

        rows.append({
            "date": str(row[1]) if row[1] else str(row[0]),  # 发生日期
            "time": str(row[2]) if row[2] else "",
            "code": str(row[3]),
            "name": str(row[4]),
            "direction": trade_type,
            "qty": qty,
            "price": price,
            "amount": amount,
            "net_amount": net_amount,
            "commission": commission,
            "stamp_tax": stamp_tax,
            "transfer_fee": transfer_fee,
            "market": str(row[19]) if row[19] else "",
            "account": str(row[17]) if row[17] else "",
        })
    wb.close()
    return rows


def load_old_format(filepath):
    """加载15列格式的Table.xlsx"""
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    rows = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[6] != "已成" or not row[8] or row[8] <= 0:
            continue
        direction = str(row[4])
        if "买入" not in direction and "卖出" not in direction:
            continue

        rows.append({
            "date": str(row[0]),
            "time": str(row[1]),
            "code": str(row[2]),
            "name": str(row[3]),
            "direction": direction,
            "qty": int(row[5]),
            "price": float(row[10]) if row[10] else float(row[7]),
            "amount": float(row[9]),
            "net_amount": float(row[9]),  # 老格式无费用明细
            "commission": 0,
            "stamp_tax": 0,
            "transfer_fee": 0,
            "market": str(row[11]),
            "account": str(row[13]) if row[13] else "",
        })
    wb.close()
    return rows


def load_all_trades():
    """加载所有数据源"""
    all_trades = []

    # 新格式文件
    new_files = [
        "2021-22.xlsx", "2022-2023.xlsx", "2023-2024xlsx.xlsx",
        "2024-2025.xlsx", "2025-2026.xlsx"
    ]
    for f in new_files:
        path = os.path.join(EASTMONEY_DIR, f)
        if os.path.exists(path):
            trades = load_new_format(path)
            all_trades.extend(trades)
            print(f"  {f}: {len(trades)} 笔")

    # 旧格式
    old_path = os.path.join(EASTMONEY_DIR, "Table.xlsx")
    if os.path.exists(old_path):
        trades = load_old_format(old_path)
        all_trades.extend(trades)
        print(f"  Table.xlsx: {len(trades)} 笔")

    print(f"  总计: {len(all_trades)} 笔交易")
    return all_trades


# ============================================================
# 第二步: FIFO匹配 + 费用计算
# ============================================================

def match_trades_fifo(all_trades):
    """FIFO匹配买卖对，含真实费用"""
    by_stock = defaultdict(list)
    for t in all_trades:
        by_stock[t["code"]].append(t)

    for code in by_stock:
        by_stock[code].sort(key=lambda x: (x["date"], x["time"]))

    round_trips = []
    unmatched_buys = []

    for code, trades in by_stock.items():
        buy_queue = []
        for t in trades:
            if "买入" in t["direction"]:
                buy_queue.append(t)
            elif "卖出" in t["direction"]:
                sell_qty = t["qty"]
                while sell_qty > 0 and buy_queue:
                    buy = buy_queue[0]
                    matched = min(buy["qty"], sell_qty)
                    buy["qty"] -= matched
                    sell_qty -= matched

                    # 按比例分摊买入费用
                    buy_ratio = matched / (buy["qty"] + matched)
                    buy_cost = (buy["commission"] + buy["stamp_tax"] + buy["transfer_fee"]) * buy_ratio
                    sell_cost = (t["commission"] + t["stamp_tax"] + t["transfer_fee"]) * (matched / t["qty"])

                    gross_buy = matched * buy["price"]
                    gross_sell = matched * t["price"]
                    gross_profit = gross_sell - gross_buy
                    net_profit = gross_profit - buy_cost - sell_cost
                    gross_pct = (t["price"] - buy["price"]) / buy["price"] * 100

                    hold = (datetime.strptime(t["date"], "%Y-%m-%d") -
                            datetime.strptime(buy["date"], "%Y-%m-%d")).days

                    round_trips.append({
                        "code": code, "name": t["name"], "market": t["market"],
                        "buy_date": buy["date"], "sell_date": t["date"],
                        "buy_price": buy["price"], "sell_price": t["price"],
                        "qty": matched,
                        "gross_profit": round(gross_profit, 2),
                        "net_profit": round(net_profit, 2),
                        "gross_pct": round(gross_pct, 2),
                        "hold_days": hold,
                        "buy_cost": round(buy_cost, 2),
                        "sell_cost": round(sell_cost, 2),
                    })

                    if buy["qty"] <= 0:
                        buy_queue.pop(0)

        # 收集未匹配买入
        for b in buy_queue:
            if b["qty"] > 0:
                unmatched_buys.append({
                    "date": b["date"], "code": code, "name": b["name"],
                    "qty": b["qty"], "price": b["price"],
                })

    return round_trips, unmatched_buys


# ============================================================
# 第三步: 构建扩展市场日历 (2020-2026)
# ============================================================

def build_extended_calendar():
    """构建覆盖全交易周期的市场日历"""
    cache_path = os.path.join(DATA_DIR, "market_calendar_full.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r") as f:
            cal = json.load(f)
        print(f"使用缓存市场日历: {len(cal)} 天")
        return cal

    print("构建全周期市场日历...")
    indices_cache = os.path.join(DATA_DIR, "index_cache_full.json")

    if os.path.exists(indices_cache):
        with open(indices_cache, "r") as f:
            idx_data = json.load(f)["data"]
    else:
        idx_data = {}
        idx_config = [
            ("sh000001", "上证指数"),
            ("sz399001", "深证成指"),
            ("sz399006", "创业板指"),
        ]
        for symbol, name in idx_config:
            try:
                df = ak.stock_zh_index_daily(symbol=symbol)
                idx_data[name] = df.to_dict("records")
                print(f"  {name}: {len(df)} 条")
                time.sleep(0.5)
            except Exception as e:
                print(f"  {name}失败: {e}")

        with open(indices_cache, "w") as f:
            json.dump({"end_date": "2026-12-31", "data": idx_data}, f, ensure_ascii=False, default=str)

    if "上证指数" not in idx_data:
        return {}

    df = pd.DataFrame(idx_data["上证指数"])
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")

    df["ma5"] = df["close"].rolling(5).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["pct_chg"] = df["close"].pct_change() * 100
    df["vol_ma5"] = df["volume"].rolling(5).mean()
    df["volume_ratio"] = df["volume"] / df["vol_ma5"]

    # 市场宽度: 用波动率近似
    df["volatility"] = df["pct_chg"].rolling(20).std()

    calendar = {}
    for _, row in df.iterrows():
        date_str = row["date"].strftime("%Y-%m-%d")
        close = row["close"]

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

        if pd.notna(row["volume_ratio"]):
            if row["volume_ratio"] > 1.15:
                vol_state = "放量"
            elif row["volume_ratio"] < 0.88:
                vol_state = "缩量"
            else:
                vol_state = "正常"
        else:
            vol_state = "未知"

        if pd.notna(row["pct_chg"]):
            pct = row["pct_chg"]
            if pct > 1.5:
                sentiment = "强势"
            elif pct > 0:
                sentiment = "偏强"
            elif pct > -1:
                sentiment = "偏弱"
            elif pct > -3:
                sentiment = "弱势"
            else:
                sentiment = "恐慌"
        else:
            sentiment = "未知"

        calendar[date_str] = {
            "close": float(close),
            "pct_chg": round(float(row["pct_chg"]), 2) if pd.notna(row["pct_chg"]) else 0,
            "trend": trend,
            "volume_state": vol_state,
            "sentiment": sentiment,
            "volatility": round(float(row["volatility"]), 2) if pd.notna(row["volatility"]) else None,
        }

    with open(cache_path, "w") as f:
        json.dump(calendar, f, ensure_ascii=False)
    print(f"市场日历: {len(calendar)} 天")
    return calendar


# ============================================================
# 第四步: 综合分析
# ============================================================

def get_market(calendar, date_str):
    d = str(date_str)[:10]
    if d in calendar:
        return calendar[d]
    return None


def classify(t):
    if t["gross_pct"] > 0.5:
        return "win"
    elif t["gross_pct"] < -0.5:
        return "loss"
    return "flat"


def analyze_yearly(trades, calendar):
    """按年分析"""
    yearly = defaultdict(lambda: {"count": 0, "win": 0, "loss": 0, "flat": 0,
                                   "gross_pnl": 0, "net_pnl": 0, "fees": 0})
    for t in trades:
        y = t["buy_date"][:4]
        r = yearly[y]
        r["count"] += 1
        r["gross_pnl"] += t["gross_profit"]
        r["net_pnl"] += t["net_profit"]
        r["fees"] += t["buy_cost"] + t["sell_cost"]
        cat = classify(t)
        if cat == "win":
            r["win"] += 1
        elif cat == "loss":
            r["loss"] += 1
        else:
            r["flat"] += 1

    for y in yearly:
        r = yearly[y]
        r["win_rate"] = round(r["win"] / r["count"] * 100, 1)
        r["avg_net"] = round(r["net_pnl"] / r["count"], 0)

    return dict(yearly)


def analyze_market_factors(trades, calendar):
    """多因子分析"""
    factors = {
        "trend_buy": defaultdict(lambda: defaultdict(int)),
        "volume_buy": defaultdict(list),
        "sentiment_sell": defaultdict(lambda: defaultdict(int)),
        "volatility": defaultdict(list),
        "month_quarter": defaultdict(lambda: {"count": 0, "pnl": 0, "win": 0}),
    }

    for t in trades:
        cat = classify(t)
        buy_mkt = get_market(calendar, t["buy_date"])
        sell_mkt = get_market(calendar, t["sell_date"])

        if buy_mkt:
            factors["trend_buy"][cat][buy_mkt["trend"]] += 1
            factors["volume_buy"][buy_mkt["volume_state"]].append(t["gross_pct"])
            if buy_mkt["volatility"]:
                factors["volatility"]["buy_vol"].append((buy_mkt["volatility"], t["gross_pct"]))

        if sell_mkt:
            factors["sentiment_sell"][cat][sell_mkt["sentiment"]] += 1

        # 季度分析
        month = int(t["buy_date"][5:7])
        quarter = f"Q{(month-1)//3+1}"
        mq = f"{t['buy_date'][:4]}-{quarter}"
        factors["month_quarter"][mq]["count"] += 1
        factors["month_quarter"][mq]["pnl"] += t["net_profit"]
        if cat == "win":
            factors["month_quarter"][mq]["win"] += 1

    return factors


def analyze_loss_deep(losers, calendar):
    """深度亏损分析"""
    # 按原因分类
    by_cause = {
        "追高杀跌": [],  # 买在强势日卖在弱势日
        "止损犹豫": [],  # >7%且持>3天
        "大盘逆风": [],  # 买在空头排列
        "缩量陷阱": [],  # 买在缩量日
        "其他": [],
    }

    for t in losers:
        buy_mkt = get_market(calendar, t["buy_date"])
        sell_mkt = get_market(calendar, t["sell_date"])

        if t["gross_pct"] < -7 and t["hold_days"] > 3:
            by_cause["止损犹豫"].append(t)
        elif buy_mkt and buy_mkt["volume_state"] == "缩量":
            by_cause["缩量陷阱"].append(t)
        elif buy_mkt and buy_mkt["trend"] == "空头排列":
            by_cause["大盘逆风"].append(t)
        elif buy_mkt and sell_mkt and buy_mkt["sentiment"] in ("强势", "偏强") and sell_mkt["sentiment"] in ("弱势", "恐慌", "偏弱"):
            by_cause["追高杀跌"].append(t)
        else:
            by_cause["其他"].append(t)

    result = {}
    for cause, trades_list in by_cause.items():
        if trades_list:
            total = sum(t["net_profit"] for t in trades_list)
            result[cause] = {
                "count": len(trades_list),
                "total_loss": round(total, 2),
                "avg_loss_pct": round(sum(t["gross_pct"] for t in trades_list) / len(trades_list), 2),
                "avg_hold": round(sum(t["hold_days"] for t in trades_list) / len(trades_list), 1),
            }

    return result


def main():
    print("=" * 60)
    print("全量BS点分析: 2021-2026")
    print("=" * 60)

    # 1. 加载
    print("\n[1/4] 加载交易数据...")
    all_trades = load_all_trades()

    # 2. 匹配
    print("\n[2/4] FIFO匹配买卖对...")
    round_trips, unmatched = match_trades_fifo(all_trades)
    winners = [t for t in round_trips if t["gross_pct"] > 0.5]
    losers = [t for t in round_trips if t["gross_pct"] < -0.5]
    flats = [t for t in round_trips if -0.5 <= t["gross_pct"] <= 0.5]

    print(f"往返交易: {len(round_trips)} (赢{len(winners)} 亏{len(losers)} 平{len(flats)})")

    # 3. 市场日历
    print("\n[3/4] 构建市场日历...")
    calendar = build_extended_calendar()

    # 4. 分析
    print("\n[4/4] 综合分析...")

    # 基础统计
    total_gross = sum(t["gross_profit"] for t in round_trips)
    total_net = sum(t["net_profit"] for t in round_trips)
    total_fees = sum(t["buy_cost"] + t["sell_cost"] for t in round_trips)
    total_winner_net = sum(t["net_profit"] for t in winners)
    total_loser_net = sum(t["net_profit"] for t in losers)

    print(f"\n{'='*60}")
    print(f"总览")
    print(f"{'='*60}")
    print(f"总往返交易: {len(round_trips)}")
    print(f"盈利: {len(winners)} ({len(winners)/len(round_trips)*100:.1f}%)  |  亏损: {len(losers)} ({len(losers)/len(round_trips)*100:.1f}%)  |  持平: {len(flats)}")
    print(f"毛利: {total_gross:,.0f}  |  净利(扣费): {total_net:,.0f}  |  总费用: {total_fees:,.0f}")
    print(f"盈利贡献: +{total_winner_net:,.0f}  |  亏损拖累: {total_loser_net:,.0f}")
    print(f"盈亏比: {abs(total_winner_net/total_loser_net):.2f}" if total_loser_net != 0 else "盈亏比: N/A")
    print(f"未平仓买入: {len(unmatched)} 笔")

    # 年度分析
    print(f"\n{'='*60}")
    print(f"年度表现")
    print(f"{'='*60}")
    yearly = analyze_yearly(round_trips, calendar)
    print(f"{'年份':<8} {'笔数':<6} {'胜率':<8} {'净利':<12} {'毛利':<12} {'费用':<10}")
    print("-" * 56)
    for y in sorted(yearly.keys()):
        r = yearly[y]
        print(f"{y:<8} {r['count']:<6} {r['win_rate']:<8.1f}% {r['net_pnl']:<12,.0f} {r['gross_pnl']:<12,.0f} {r['fees']:<10,.0f}")

    # 市场因子
    print(f"\n{'='*60}")
    print(f"买入大盘趋势 vs 盈亏")
    print(f"{'='*60}")
    factors = analyze_market_factors(round_trips, calendar)
    for label, cat_key in [("盈利", "win"), ("亏损", "loss")]:
        trends = factors["trend_buy"][cat_key]
        total = sum(trends.values())
        print(f"\n{label}买入时大盘:")
        bullish = trends.get("多头排列", 0) + trends.get("短期偏多", 0)
        bearish = trends.get("空头排列", 0) + trends.get("短期偏空", 0)
        print(f"  偏多: {bullish} ({bullish/total*100:.1f}%)  偏空: {bearish} ({bearish/total*100:.1f}%)")

    # 量能因子
    print(f"\n{'='*60}")
    print(f"买入量能 vs 平均收益")
    print(f"{'='*60}")
    for state in ["放量", "正常", "缩量"]:
        if state in factors["volume_buy"] and factors["volume_buy"][state]:
            pcts = factors["volume_buy"][state]
            print(f"  {state}: {len(pcts)}笔, 均收益{sum(pcts)/len(pcts):.2f}%")

    # 季度分析
    print(f"\n{'='*60}")
    print(f"季度表现")
    print(f"{'='*60}")
    mq = factors["month_quarter"]
    for q in sorted(mq.keys()):
        d = mq[q]
        wr = d["win"] / d["count"] * 100 if d["count"] > 0 else 0
        bar = "█" * int(wr / 4) if wr > 0 else ""
        print(f"  {q}: {d['count']}笔 胜率{wr:.1f}% 净利{d['pnl']:,.0f} {bar}")

    # 亏损归因
    print(f"\n{'='*60}")
    print(f"亏损归因分析")
    print(f"{'='*60}")
    loss_causes = analyze_loss_deep(losers, calendar)
    total_loss_count = sum(v["count"] for v in loss_causes.values())
    for cause in ["止损犹豫", "追高杀跌", "缩量陷阱", "大盘逆风", "其他"]:
        if cause in loss_causes:
            d = loss_causes[cause]
            pct = d["count"] / total_loss_count * 100
            print(f"  {cause}: {d['count']}笔 ({pct:.1f}%) 亏损{d['total_loss']:,.0f} 均亏{d['avg_loss_pct']:.1f}% 均持{d['avg_hold']}天")

    # 持仓时长(全周期)
    print(f"\n{'='*60}")
    print(f"持仓时长 vs 胜率 (全周期)")
    print(f"{'='*60}")
    hold_buckets = {"0-2天": (0, 2), "3-5天": (3, 5), "6-10天": (6, 10),
                    "11-20天": (11, 20), "21-50天": (21, 50), "50天+": (51, 9999)}
    for label, (lo, hi) in hold_buckets.items():
        bucket_trades = [t for t in round_trips if lo <= t["hold_days"] <= hi]
        if bucket_trades:
            wr = len([t for t in bucket_trades if t["gross_pct"] > 0.5]) / len(bucket_trades) * 100
            avg = sum(t["gross_pct"] for t in bucket_trades) / len(bucket_trades)
            avg_net = sum(t["net_profit"] for t in bucket_trades) / len(bucket_trades)
            print(f"  {label}: {len(bucket_trades)}笔 ({len(bucket_trades)/len(round_trips)*100:.1f}%) 胜率{wr:.1f}% 均收益{avg:.2f}% 均净利{avg_net:,.0f}")

    # 保存完整结果
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_round_trips": len(round_trips),
            "winners": len(winners),
            "losers": len(losers),
            "flats": len(flats),
            "win_rate": round(len(winners) / len(round_trips) * 100, 1),
            "total_gross_pnl": round(total_gross, 2),
            "total_net_pnl": round(total_net, 2),
            "total_fees": round(total_fees, 2),
        },
        "yearly": {k: dict(v) for k, v in yearly.items()},
        "loss_causes": loss_causes,
    }

    out_path = os.path.join(DATA_DIR, "bs_full_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
