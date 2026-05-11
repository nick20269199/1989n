"""
回测验证：用2021-2026年3,817笔交易数据跑一遍新机制
对比: 实际结果 vs 新机制结果
"""
import json
import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime, timedelta
from collections import defaultdict
from trade_engine import (
    TradeEngine, TradePlan, Params, Signal, PositionState
)

DATA_DIR = "D:/1989n/stock_data"


def load_all_round_trips():
    """加载已匹配的往返交易"""
    # 从bs_full_analysis没有直接保存round_trips列表
    # 需要重新从原始数据构建
    import openpyxl
    from collections import defaultdict

    EASTMONEY_DIR = "D:/东方财富"

    def load_new_format(filepath):
        wb = openpyxl.load_workbook(filepath)
        ws = wb.active
        rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[4] is None:
                continue
            trade_type = str(row[5])
            if trade_type not in ('证券买入', '证券卖出'):
                continue
            qty = int(row[6]) if row[6] else 0
            if qty <= 0:
                continue
            rows.append({
                "date": str(row[1]) if row[1] else str(row[0]),
                "time": str(row[2]) if row[2] else "",
                "code": str(row[3]),
                "name": str(row[4]),
                "direction": trade_type,
                "qty": qty,
                "price": float(row[7]) if row[7] else 0,
                "commission": float(row[10]) if row[10] else 0,
                "stamp_tax": float(row[12]) if row[12] else 0,
                "transfer_fee": float(row[13]) if row[13] else 0,
            })
        wb.close()
        return rows

    all_trades = []
    for f in ["2021-22.xlsx", "2022-2023.xlsx", "2023-2024xlsx.xlsx",
               "2024-2025.xlsx", "2025-2026.xlsx"]:
        path = os.path.join(EASTMONEY_DIR, f)
        if os.path.exists(path):
            all_trades.extend(load_new_format(path))

    # FIFO匹配
    by_stock = defaultdict(list)
    for t in all_trades:
        by_stock[t["code"]].append(t)
    for code in by_stock:
        by_stock[code].sort(key=lambda x: (x["date"], x["time"]))

    round_trips = []
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

                    fee_ratio = matched / (buy["qty"] + matched) if (buy["qty"] + matched) > 0 else 1
                    buy_fee = (buy["commission"] + buy["stamp_tax"] + buy["transfer_fee"]) * fee_ratio
                    sell_fee = (t["commission"] + t["stamp_tax"] + t["transfer_fee"]) * (matched / t["qty"])

                    gross_pnl = matched * (t["price"] - buy["price"])
                    net_pnl = gross_pnl - buy_fee - sell_fee
                    pct = (t["price"] - buy["price"]) / buy["price"] * 100
                    hold = (datetime.strptime(t["date"], "%Y-%m-%d") -
                            datetime.strptime(buy["date"], "%Y-%m-%d")).days

                    round_trips.append({
                        "code": code, "name": t["name"],
                        "buy_date": buy["date"], "sell_date": t["date"],
                        "buy_price": buy["price"], "sell_price": t["price"],
                        "qty": matched,
                        "gross_profit": round(gross_pnl, 2),
                        "net_profit": round(net_pnl, 2),
                        "gross_pct": round(pct, 2),
                        "hold_days": hold,
                    })
                    if buy["qty"] <= 0:
                        buy_queue.pop(0)

    return round_trips


def backtest(round_trips):
    """用新机制回测所有交易"""
    engine = TradeEngine()
    cal = engine.calendar

    results = {
        "total": len(round_trips),
        "filtered_out": [],       # 被过滤层拦截
        "filtered_warn": [],      # 警示但放行
        "passed": [],             # 通过过滤
        "stop_loss_hit": [],      # 触发止损
        "danger_zone_exit": [],   # 危险区退出
        "profit_take_hit": [],    # 止盈触发
        "time_exit": [],          # 时间止
        "normal_close": [],       # 正常到期
        "actual_total_pnl": 0,
        "simulated_total_pnl": 0,
    }

    for t in round_trips:
        code = t["code"]
        buy_date = t["buy_date"]
        actual_pnl = t["net_profit"]
        actual_pct = t["gross_pct"]
        hold_days = t["hold_days"]

        results["actual_total_pnl"] += actual_pnl

        # 检查买入时的市场状态
        buy_mkt = cal.get(buy_date, {})
        vol_state = buy_mkt.get("volume_state", "正常")
        trend = buy_mkt.get("trend", "")
        sentiment = buy_mkt.get("sentiment", "")

        # 过滤层检查
        filter_reason = None

        # 缩量过滤
        if vol_state == "缩量":
            filter_reason = f"缩量买入(均盈亏-0.68%)"
        # 空头排列过滤
        elif trend == "空头排列":
            filter_reason = f"空头排列(均盈亏-1.31%)"
        # 恐慌过滤
        elif sentiment == "恐慌":
            filter_reason = f"恐慌日买入"

        if filter_reason:
            results["filtered_out"].append({
                **t, "filter_reason": filter_reason,
                "prevented_loss": -actual_pnl if actual_pnl < 0 else 0,
            })
            # 被过滤的交易不参与模拟盈亏（视为没做）
            continue

        # 执行层模拟
        # 硬止损：-7%
        if actual_pct <= Params.HARD_STOP_PCT:
            # 假设在-7%时止损
            stop_loss_pct = Params.HARD_STOP_PCT
            if t["buy_price"] > 0:
                stop_price = t["buy_price"] * (1 + stop_loss_pct / 100)
                stop_loss_amount = t["qty"] * (stop_price - t["buy_price"])
                # 加回费用的一小部分
                simulated_pnl = stop_loss_amount - (t["gross_profit"] - t["net_profit"]) * 0.5
            else:
                simulated_pnl = actual_pnl

            results["stop_loss_hit"].append({
                **t,
                "actual_pnl": actual_pnl,
                "simulated_pnl": round(simulated_pnl, 2),
                "saved": round(actual_pnl - simulated_pnl, 2),
            })
            results["simulated_total_pnl"] += simulated_pnl
            continue

        # 危险区(3-5天) + 浮亏/微利
        if Params.DANGER_ZONE_START <= hold_days <= Params.DANGER_ZONE_END:
            if actual_pct < 0:
                # 第3天浮亏即砍
                exit_day = Params.DANGER_ZONE_START
                # 近似: 用实际结果的一半来估算提前砍的效果
                simulated_pnl = actual_pnl * 0.4  # 提前砍减少损失
                results["danger_zone_exit"].append({
                    **t,
                    "actual_pnl": actual_pnl,
                    "simulated_pnl": round(simulated_pnl, 2),
                    "saved": round(actual_pnl - simulated_pnl, 2),
                })
                results["simulated_total_pnl"] += simulated_pnl
                continue
            elif 0 <= actual_pct <= 2:
                results["danger_zone_exit"].append({
                    **t,
                    "actual_pnl": actual_pnl,
                    "simulated_pnl": actual_pnl,
                    "saved": 0,
                })
                results["simulated_total_pnl"] += actual_pnl
                continue

        # +8% 止盈一半
        if actual_pct >= Params.PROFIT_TAKE_50_PCT:
            half_pnl = actual_pnl * 0.5
            remaining = actual_pnl * 0.5
            if actual_pct >= Params.PROFIT_TAKE_ALL_PCT:
                remaining = actual_pnl * 0.5
            else:
                remaining = actual_pnl * 0.5 * 0.6

            simulated_pnl = half_pnl + remaining
            results["profit_take_hit"].append({
                **t,
                "actual_pnl": actual_pnl,
                "simulated_pnl": round(simulated_pnl, 2),
            })
            results["simulated_total_pnl"] += simulated_pnl
            continue

        # 超10天强制清
        if hold_days > Params.MAX_HOLD_DAYS:
            results["time_exit"].append(t)
            # 10天时强制清，根据实际盈亏比例估算
            day_ratio = min(1.0, Params.MAX_HOLD_DAYS / hold_days)
            simulated_pnl = actual_pnl * day_ratio
            results["simulated_total_pnl"] += simulated_pnl
            continue

        # 正常通过
        results["passed"].append(t)
        results["simulated_total_pnl"] += actual_pnl

    return results


def print_backtest_report(results):
    """打印回测报告"""
    total = results["total"]
    filtered = len(results["filtered_out"])
    passed = len(results["passed"])
    stop_loss = len(results["stop_loss_hit"])
    danger = len(results["danger_zone_exit"])
    profit_take = len(results["profit_take_hit"])
    time_exit = len(results["time_exit"])

    actual_total = results["actual_total_pnl"]
    simulated_total = results["simulated_total_pnl"]
    improvement = simulated_total - actual_total

    print("=" * 65)
    print("  回测验证: 新交易机制 vs 实际结果")
    print("=" * 65)

    print(f"\n  ── 实际结果 ──")
    print(f"  总交易: {total}笔")
    print(f"  实际净利: {actual_total:,.0f}元")

    print(f"\n  ── 新机制模拟 ──")
    print(f"  过滤拦截: {filtered}笔 ({filtered/total*100:.1f}%)")
    print(f"  止损优化: {stop_loss}笔 ({stop_loss/total*100:.1f}%)")
    print(f"  危险区出: {danger}笔 ({danger/total*100:.1f}%)")
    print(f"  止盈优化: {profit_take}笔 ({profit_take/total*100:.1f}%)")
    print(f"  超时清仓: {time_exit}笔 ({time_exit/total*100:.1f}%)")
    print(f"  正常通过: {passed}笔 ({passed/total*100:.1f}%)")
    print(f"  模拟净利: {simulated_total:,.0f}元")
    print(f"  改善幅度: {improvement:,.0f}元 ({improvement/abs(actual_total)*100:+.0f}%)" if actual_total != 0 else
          f"  改善幅度: {improvement:,.0f}元")

    # 过滤层效果
    if results["filtered_out"]:
        fo = results["filtered_out"]
        fo_pnl = sum(t["net_profit"] for t in fo)
        fo_saved = sum(abs(t["net_profit"]) for t in fo if t["net_profit"] < 0)
        print(f"\n  ── 过滤层详情 ──")
        print(f"  拦截{len(fo)}笔, 原亏损{fo_pnl:,.0f}元")

        # 按原因分类
        by_reason = defaultdict(lambda: {"count": 0, "pnl": 0})
        for t in fo:
            reason = t["filter_reason"]
            by_reason[reason]["count"] += 1
            by_reason[reason]["pnl"] += t["net_profit"]
        for reason, data in sorted(by_reason.items(), key=lambda x: x[1]["count"], reverse=True):
            print(f"    {reason}: {data['count']}笔, 原盈亏{data['pnl']:,.0f}")

    # 止损层效果
    if results["stop_loss_hit"]:
        sl = results["stop_loss_hit"]
        sl_saved = sum(t["saved"] for t in sl)
        sl_actual = sum(t["actual_pnl"] for t in sl)
        sl_sim = sum(t["simulated_pnl"] for t in sl)
        print(f"\n  ── 止损层详情 ──")
        print(f"  止损触发{len(sl)}笔, 实际亏损{sl_actual:,.0f} → 模拟亏损{sl_sim:,.0f}")
        print(f"  止损挽救: {sl_saved:,.0f}元")
        # 最严重的几次止损
        worst = sorted(sl, key=lambda x: x["actual_pnl"])[:5]
        for t in worst:
            print(f"    {t['name']}({t['code']}) {t['buy_date']}: "
                  f"实际{t['actual_pnl']:,.0f} → 模拟{t['simulated_pnl']:,.0f} "
                  f"({t['gross_pct']:.1f}%, 持{t['hold_days']}天)")

    # 危险区
    if results["danger_zone_exit"]:
        de = results["danger_zone_exit"]
        de_actual = sum(t["actual_pnl"] for t in de)
        de_sim = sum(t["simulated_pnl"] for t in de)
        de_saved = sum(t.get("saved", 0) for t in de)
        print(f"\n  ── 危险区退出详情 ──")
        print(f"  危险区出{len(de)}笔, 实际{de_actual:,.0f} → 模拟{de_sim:,.0f}, 挽回{de_saved:,.0f}")

    # 结论
    print(f"\n  {'='*65}")
    if simulated_total > actual_total:
        print(f"  ✅ 新机制可改善交易结果 {improvement:,.0f}元")
    else:
        print(f"  ⚠ 新机制在历史回测中未改善结果")
    print(f"  {'='*65}")


def main():
    print("加载交易数据...")
    round_trips = load_all_round_trips()
    print(f"加载 {len(round_trips)} 笔往返交易")

    print("\n运行回测...")
    results = backtest(round_trips)
    print_backtest_report(results)

    # 保存
    out_path = os.path.join(DATA_DIR, "backtest_results.json")
    save_results = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total_trades": results["total"],
            "actual_pnl": round(results["actual_total_pnl"], 2),
            "simulated_pnl": round(results["simulated_total_pnl"], 2),
            "improvement": round(results["simulated_total_pnl"] - results["actual_total_pnl"], 2),
            "filtered_out": len(results["filtered_out"]),
            "stop_loss_hit": len(results["stop_loss_hit"]),
            "danger_zone_exit": len(results["danger_zone_exit"]),
            "profit_take_hit": len(results["profit_take_hit"]),
        },
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(save_results, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
