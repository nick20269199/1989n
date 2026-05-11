"""
BS点综合分析：交易分类(赚/亏/平) × 市场背景(大盘+板块+资金)
"""
import json
import os
from collections import defaultdict
from datetime import datetime, date

DATA_DIR = "D:/1989n/stock_data"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_market_on_date(calendar, trade_date):
    """获取某交易日的大盘状态"""
    d = str(trade_date)[:10]
    if d in calendar:
        return calendar[d]
    # 尝试找最近的交易日
    for offset in range(1, 5):
        prev = (datetime.strptime(d, "%Y-%m-%d").date() - date.resolution * offset).strftime("%Y-%m-%d")
        if prev in calendar:
            return calendar[prev]
    return None


def analyze_market_context(trades, calendar, north_data):
    """分析交易时的市场背景"""
    results = {
        "buy_market": defaultdict(lambda: defaultdict(int)),
        "sell_market": defaultdict(lambda: defaultdict(int)),
        "trend_combo": defaultdict(int),  # 买入趋势→卖出趋势的转换
        "north_flow_impact": defaultdict(list),  # 北向资金影响
        "volume_impact": defaultdict(list),
        "sentiment_impact": defaultdict(list),
    }

    for t in trades:
        cat = "win" if t["gross_pct"] > 0.5 else ("loss" if t["gross_pct"] < -0.5 else "flat")

        buy_mkt = get_market_on_date(calendar, t["buy_date"])
        sell_mkt = get_market_on_date(calendar, t["sell_date"])

        if buy_mkt:
            results["buy_market"][cat][f"趋势:{buy_mkt['trend']}"] += 1
            results["buy_market"][cat][f"情绪:{buy_mkt['sentiment']}"] += 1
            results["buy_market"][cat][f"量能:{buy_mkt['volume_state']}"] += 1
            results["volume_impact"][buy_mkt["volume_state"]].append(t["gross_pct"])
            results["sentiment_impact"][buy_mkt["sentiment"]].append(t["gross_pct"])

        if sell_mkt:
            results["sell_market"][cat][f"趋势:{sell_mkt['trend']}"] += 1
            results["sell_market"][cat][f"情绪:{sell_mkt['sentiment']}"] += 1

        if buy_mkt and sell_mkt:
            combo = f"{buy_mkt['trend']}→{sell_mkt['trend']}"
            results["trend_combo"][combo] += 1

    return results


def analyze_hold_time(trades):
    """分析持仓时长与盈亏的关系"""
    buckets = {
        "日内(0天)": (0, 0),
        "1-2天": (1, 2),
        "3-5天": (3, 5),
        "6-10天": (6, 10),
        "11-20天": (11, 20),
        "20天以上": (21, 999),
    }

    result = defaultdict(lambda: {"count": 0, "win": 0, "loss": 0, "flat": 0, "total_pnl": 0, "total_pct": 0, "avg_pnl_yuan": 0, "avg_pct": 0})

    for t in trades:
        for bucket, (lo, hi) in buckets.items():
            if lo <= t["hold_days"] <= hi:
                r = result[bucket]
                r["count"] += 1
                r["total_pnl"] += t["gross_profit"]
                r["total_pct"] += t["gross_pct"]
                if t["gross_pct"] > 0.5:
                    r["win"] += 1
                elif t["gross_pct"] < -0.5:
                    r["loss"] += 1
                else:
                    r["flat"] += 1
                break

    for b in result:
        if result[b]["count"] > 0:
            result[b]["avg_pnl_yuan"] = round(result[b]["total_pnl"] / result[b]["count"], 2)
            result[b]["avg_pct"] = round(result[b]["total_pct"] / result[b]["count"], 2)
            result[b]["win_rate"] = round(result[b]["win"] / result[b]["count"] * 100, 1)

    return dict(result)


def analyze_by_month(trades, calendar):
    """按月分析：盈亏与市场环境的关系"""
    monthly = defaultdict(lambda: {
        "total_trades": 0, "win": 0, "loss": 0, "flat": 0,
        "total_pnl": 0, "market_pct": 0, "market_trend": ""
    })

    for t in trades:
        month = t["buy_date"][:7]
        m = monthly[month]
        m["total_trades"] += 1
        m["total_pnl"] += t["gross_profit"]
        if t["gross_pct"] > 0.5:
            m["win"] += 1
        elif t["gross_pct"] < -0.5:
            m["loss"] += 1
        else:
            m["flat"] += 1

    # 添加当月大盘涨跌
    for month in monthly:
        m = monthly[month]
        m["win_rate"] = round(m["win"] / m["total_trades"] * 100, 1) if m["total_trades"] > 0 else 0
        # 取当月第一个交易日的大盘状态
        for d, v in sorted(calendar.items()):
            if d.startswith(month):
                m["market_trend"] = v["trend"]
                break

    return dict(monthly)


def analyze_stock_frequency(trades):
    """高频交易股票分析"""
    stock_stats = defaultdict(lambda: {
        "name": "", "count": 0, "win": 0, "loss": 0, "flat": 0,
        "total_pnl": 0, "avg_pct": 0, "avg_hold": 0
    })

    for t in trades:
        code = t["code"]
        s = stock_stats[code]
        s["name"] = t["name"]
        s["count"] += 1
        s["total_pnl"] += t["gross_profit"]
        s["avg_hold"] += t["hold_days"]
        if t["gross_pct"] > 0.5:
            s["win"] += 1
        elif t["gross_pct"] < -0.5:
            s["loss"] += 1
        else:
            s["flat"] += 1

    for code in stock_stats:
        s = stock_stats[code]
        s["avg_pct"] = round(s["total_pnl"] / s["count"], 2) if s["count"] > 0 else 0
        s["avg_hold"] = round(s["avg_hold"] / s["count"], 1) if s["count"] > 0 else 0
        s["win_rate"] = round(s["win"] / s["count"] * 100, 1) if s["count"] > 0 else 0

    # 按交易次数分组
    high_freq = {k: v for k, v in stock_stats.items() if v["count"] >= 10}
    mid_freq = {k: v for k, v in stock_stats.items() if 4 <= v["count"] < 10}
    low_freq = {k: v for k, v in stock_stats.items() if v["count"] < 4}

    for group_name, group in [("高频(≥10次)", high_freq), ("中频(4-9次)", mid_freq), ("低频(1-3次)", low_freq)]:
        if group:
            avg_win_rate = sum(s["win_rate"] for s in group.values()) / len(group)
            avg_pnl = sum(s["total_pnl"] for s in group.values()) / len(group)
            total_count = sum(s["count"] for s in group.values())
            print(f"\n{group_name}: {len(group)}只, 均胜率{avg_win_rate:.1f}%, 均盈亏{avg_pnl:,.0f}")

    return stock_stats


def analyze_loss_patterns(losers, winners):
    """亏损交易的特殊模式分析"""
    # 连续亏损
    losers_sorted = sorted(losers, key=lambda x: (x["buy_date"], x["sell_date"]))
    streaks = []
    current_streak = []
    for t in losers_sorted:
        pct = t["gross_pct"]
        if pct < -5:
            current_streak.append(t)
        else:
            if len(current_streak) >= 2:
                streaks.append(current_streak)
            current_streak = []

    # 大亏 vs 小亏
    big_loss = [t for t in losers if t["gross_pct"] < -10]
    mid_loss = [t for t in losers if -10 <= t["gross_pct"] < -5]
    small_loss = [t for t in losers if -5 <= t["gross_pct"] < -0.5]

    # 止损纪律分析: 如果亏损超7%还持有超过3天
    stop_loss_violations = [t for t in losers if t["gross_pct"] < -7 and t["hold_days"] > 3]

    return {
        "total_losers": len(losers),
        "big_loss_gt10pct": len(big_loss),
        "mid_loss_5to10pct": len(mid_loss),
        "small_loss_lt5pct": len(small_loss),
        "loss_streaks_2plus": len(streaks),
        "stop_loss_violations": len(stop_loss_violations),
        "avg_big_loss_pct": round(sum(t["gross_pct"] for t in big_loss) / len(big_loss), 2) if big_loss else 0,
    }


def main():
    print("=== BS点综合分析 ===\n")

    # 加载数据
    bs_data = load_json(os.path.join(DATA_DIR, "bs_analysis.json"))
    calendar = load_json(os.path.join(DATA_DIR, "market_calendar.json"))
    north_data = load_json(os.path.join(DATA_DIR, "north_flow_cache.json"))

    # 合并所有往返交易
    all_trades = []
    for cat_key in ["winners", "losers", "flats"]:
        cat = bs_data[cat_key]
        # 从category分析中重建交易列表
        pass

    # 从bs_analysis中获取分类统计
    # 重新构建完整交易列表
    import openpyxl
    from collections import defaultdict

    # 重新加载原始交易做分析
    wb = openpyxl.load_workbook("D:/1989n/Table.xlsx")
    ws = wb.active
    trades_raw = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if row[6] == "已成" and row[8] and row[8] > 0:
            trades_raw.append({
                "date": str(row[0]),
                "time": str(row[1]),
                "code": str(row[2]),
                "name": str(row[3]),
                "direction": str(row[4]),
                "qty": int(row[5]),
                "price": float(row[10]),
                "amount": float(row[9]),
                "market": str(row[11]),
            })

    # FIFO匹配
    by_stock = defaultdict(list)
    for t in trades_raw:
        by_stock[t["code"]].append(t)

    for code in by_stock:
        by_stock[code].sort(key=lambda x: (x["date"], x["time"]))

    round_trips = []
    for code, trades_list in by_stock.items():
        buy_queue = []
        for t in trades_list:
            if "买入" in t["direction"]:
                buy_queue.append(t)
            elif "卖出" in t["direction"]:
                sell_qty = t["qty"]
                while sell_qty > 0 and buy_queue:
                    buy = buy_queue[0]
                    matched = min(buy["qty"], sell_qty)
                    buy["qty"] -= matched
                    sell_qty -= matched

                    buy_amt = matched * buy["price"]
                    sell_amt = matched * t["price"]
                    profit = sell_amt - buy_amt
                    pct = (t["price"] - buy["price"]) / buy["price"] * 100
                    hold = (datetime.strptime(t["date"], "%Y-%m-%d") -
                            datetime.strptime(buy["date"], "%Y-%m-%d")).days

                    round_trips.append({
                        "code": code, "name": t["name"], "market": t["market"],
                        "buy_date": buy["date"], "sell_date": t["date"],
                        "buy_price": buy["price"], "sell_price": t["price"],
                        "qty": matched, "buy_amount": round(buy_amt, 2),
                        "sell_amount": round(sell_amt, 2),
                        "gross_profit": round(profit, 2),
                        "gross_pct": round(pct, 2),
                        "hold_days": hold,
                    })

                    if buy["qty"] <= 0:
                        buy_queue.pop(0)

    winners = [t for t in round_trips if t["gross_pct"] > 0.5]
    losers = [t for t in round_trips if t["gross_pct"] < -0.5]
    flats = [t for t in round_trips if -0.5 <= t["gross_pct"] <= 0.5]

    print(f"往返交易: {len(round_trips)} (赢{len(winners)} 亏{len(losers)} 平{len(flats)})")

    # ====== 1. 市场背景分析 ======
    print("\n===== 1. 买入时大盘趋势 vs 盈亏 =====")
    for label, trades_list in [("盈利", winners), ("亏损", losers), ("持平", flats)]:
        trend_count = defaultdict(int)
        sentiment_count = defaultdict(int)
        for t in trades_list:
            mkt = get_market_on_date(calendar, t["buy_date"])
            if mkt:
                trend_count[mkt["trend"]] += 1
                sentiment_count[mkt["sentiment"]] += 1
        total = len(trades_list)
        print(f"\n{label}({total}笔) 买入时:")
        for trend in ["多头排列", "短期偏多", "震荡", "短期偏空", "空头排列"]:
            if trend in trend_count:
                print(f"  {trend}: {trend_count[trend]}次 ({trend_count[trend]/total*100:.1f}%)")
        # 合并: 偏多(多头+短期偏多) vs 偏空(空头+短期偏空)
        bullish = trend_count.get("多头排列", 0) + trend_count.get("短期偏多", 0)
        bearish = trend_count.get("空头排列", 0) + trend_count.get("短期偏空", 0)
        neutral = trend_count.get("震荡", 0) + trend_count.get("数据不足", 0)
        print(f"  偏多{bullish}({bullish/total*100:.1f}%) 偏空{bearish}({bearish/total*100:.1f}%) 中性{neutral}({neutral/total*100:.1f}%)")

    # ====== 2. 卖出时大盘情绪 vs 盈亏 ======
    print("\n===== 2. 卖出时大盘情绪 vs 盈亏 =====")
    for label, trades_list in [("盈利", winners), ("亏损", losers)]:
        sent_count = defaultdict(int)
        for t in trades_list:
            mkt = get_market_on_date(calendar, t["sell_date"])
            if mkt:
                sent_count[mkt["sentiment"]] += 1
        total = len(trades_list)
        for s in ["强势", "偏强", "偏弱", "弱势", "恐慌"]:
            if s in sent_count:
                print(f"  {label} 卖出时{s}: {sent_count[s]}次 ({sent_count[s]/total*100:.1f}%)")

    # ====== 3. 量能影响 ======
    print("\n===== 3. 买入时成交量状态 vs 平均盈亏 =====")
    vol_pnl = defaultdict(list)
    for t in round_trips:
        mkt = get_market_on_date(calendar, t["buy_date"])
        if mkt:
            vol_pnl[mkt["volume_state"]].append(t["gross_pct"])
    for state in ["放量", "正常", "缩量"]:
        if state in vol_pnl and vol_pnl[state]:
            avg = sum(vol_pnl[state]) / len(vol_pnl[state])
            print(f"  买入时{state}: {len(vol_pnl[state])}笔, 均收益{avg:.2f}%")

    # ====== 4. 持仓时长分析 ======
    print("\n===== 4. 持仓时长 vs 胜率 =====")
    hold_analysis = analyze_hold_time(round_trips)
    for bucket, data in hold_analysis.items():
        if data["count"] > 0:
            print(f"  {bucket}: {data['count']}笔, 胜率{data['win_rate']:.1f}%, 均收益{data['avg_pct']:.2f}%, 均盈亏{data['avg_pnl_yuan']:,.0f}元")

    # ====== 5. 月度分析 ======
    print("\n===== 5. 月度表现 =====")
    monthly = analyze_by_month(round_trips, calendar)
    for month in sorted(monthly.keys()):
        m = monthly[month]
        bar = "█" * int(m["win_rate"] / 5) if m["win_rate"] > 0 else ""
        print(f"  {month}: {m['total_trades']}笔 胜率{m['win_rate']:.1f}% 盈亏{m['total_pnl']:,.0f} 大盘:{m['market_trend']} {bar}")

    # ====== 6. 亏损模式 ======
    print("\n===== 6. 亏损模式分析 =====")
    loss_patterns = analyze_loss_patterns(losers, winners)
    print(f"  大亏(>10%): {loss_patterns['big_loss_gt10pct']}笔, 均亏损{loss_patterns['avg_big_loss_pct']:.1f}%")
    print(f"  中亏(5-10%): {loss_patterns['mid_loss_5to10pct']}笔")
    print(f"  小亏(<5%): {loss_patterns['small_loss_lt5pct']}笔")
    print(f"  连续亏损串(≥2次): {loss_patterns['loss_streaks_2plus']}串")
    print(f"  止损违规(亏>7%持>3天): {loss_patterns['stop_loss_violations']}笔")

    # ====== 7. 交易频率 vs 盈亏 ======
    print("\n===== 7. 交易频率 vs 盈亏 =====")
    stock_stats = analyze_stock_frequency(round_trips)

    # ====== 8. 市场趋势转换分析 ======
    print("\n===== 8. 买卖之间的市场趋势变化 =====")
    trend_combo = defaultdict(lambda: {"count": 0, "total_pnl": 0})
    for t in round_trips:
        buy_mkt = get_market_on_date(calendar, t["buy_date"])
        sell_mkt = get_market_on_date(calendar, t["sell_date"])
        if buy_mkt and sell_mkt:
            combo = f"{buy_mkt['trend']}→{sell_mkt['trend']}"
            trend_combo[combo]["count"] += 1
            trend_combo[combo]["total_pnl"] += t["gross_pct"]

    for combo in sorted(trend_combo.keys(), key=lambda x: trend_combo[x]["count"], reverse=True):
        d = trend_combo[combo]
        if d["count"] >= 5:
            avg = d["total_pnl"] / d["count"]
            print(f"  {combo}: {d['count']}笔, 均收益{avg:.2f}%")

    # ====== 保存完整分析结果 ======
    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_trades": len(round_trips),
            "winners": len(winners),
            "losers": len(losers),
            "flats": len(flats),
            "win_rate": round(len(winners) / len(round_trips) * 100, 1),
            "total_pnl": round(sum(t["gross_profit"] for t in round_trips), 2),
            "total_winner_pnl": round(sum(t["gross_profit"] for t in winners), 2),
            "total_loser_pnl": round(sum(t["gross_profit"] for t in losers), 2),
        },
        "hold_analysis": hold_analysis,
        "monthly_analysis": {k: dict(v) for k, v in monthly.items()},
        "loss_patterns": loss_patterns,
    }

    out_path = os.path.join(DATA_DIR, "bs_comprehensive_analysis.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n分析结果已保存: {out_path}")

    return output


if __name__ == "__main__":
    main()
