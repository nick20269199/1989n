"""
概率评分 + 波动率自适应回测
对比三种策略: 固定规则 / 概率加权 / 波动率自适应
在5年3817笔交易上跑，输出真实对比
"""
import json
import os
import sys
import math
from datetime import datetime, timedelta
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

DATA_DIR = "D:/1989n/stock_data"

# ============================================================
# 固定规则参数 (基准)
# ============================================================
FIXED = {
    "hard_stop": -7.0,
    "soft_stop": -3.0,
    "take_profit_half": 8.0,
    "take_profit_all": 15.0,
    "trail_activate": 5.0,
    "trail_distance": 3.0,
    "danger_zone": (3, 5),
    "max_hold": 10,
}

# ============================================================
# 概率模型参数
# ============================================================
PROB = {
    "exit_threshold": 0.35,       # P(win) < 35% 才退出
    "danger_exit_threshold": 0.45, # 危险区更严: P(win) < 45% 退出
    "strong_hold_threshold": 0.60, # P(win) > 60% 无视规则继续持有
    "volatility_lookback": 20,    # 波动率计算窗口
}


def load_round_trips():
    """加载所有已匹配往返交易"""
    import openpyxl

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


def load_calendar():
    path = os.path.join(DATA_DIR, "market_calendar_full.json")
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


def estimate_volatility(trades_by_stock):
    """用每只股票的历史交易估算波动率 (无日线数据时的替代方案)"""
    vol = {}
    for code, trades in trades_by_stock.items():
        if len(trades) < 3:
            vol[code] = 3.0  # 默认中等波动率
            continue
        # 用每次交易的高低差估算
        pcts = []
        for t in trades:
            pct = abs(t["gross_pct"])
            if pct > 0 and pct < 50:  # 过滤极端值
                pcts.append(pct)
        if pcts:
            # 用标准差估算日常波动率
            mean_pct = sum(pcts) / len(pcts)
            # 日常波动约 = 平均绝对收益的60% (单日通常比持仓期波动小)
            vol[code] = round(mean_pct * 0.6, 2)
        else:
            vol[code] = 3.0
    return vol


def compute_adaptive_stops(cost: float, vol_pct: float, pnl_pct: float,
                           hold_days: int) -> dict:
    """波动率自适应止损/止盈价位"""
    # 波动率越高 → 止损越宽 (不让噪音震出去)
    # 波动率越低 → 止损越紧 (小波动就该跑)
    vol_factor = vol_pct / 3.0  # 相对中等波动率的倍数

    hard_stop_pct = max(-10.0, min(-4.0, -7.0 * vol_factor))
    soft_stop_pct = max(-5.0, min(-2.0, -3.0 * vol_factor))
    take_half_pct = max(5.0, min(15.0, 8.0 * vol_factor))
    take_all_pct = max(10.0, min(25.0, 15.0 * vol_factor))
    trail_activate_pct = max(3.0, min(8.0, 5.0 * vol_factor))

    return {
        "hard_stop": round(cost * (1 + hard_stop_pct / 100), 2),
        "soft_stop": round(cost * (1 + soft_stop_pct / 100), 2),
        "take_half": round(cost * (1 + take_half_pct / 100), 2),
        "take_all": round(cost * (1 + take_all_pct / 100), 2),
        "trail_activate": round(cost * (1 + trail_activate_pct / 100), 2),
        "vol_pct": vol_pct,
        "hard_stop_pct": round(hard_stop_pct, 1),
    }


def compute_prob_score(trade: dict, calendar: dict, mkt_idx: dict,
                       vol_data: dict, day_in_trade: int,
                       approx_pnl_pct: float) -> float:
    """
    估算当前持仓明天盈利的概率 P(win)
    返回 0.0 ~ 1.0 的概率值
    """
    buy_date = trade["buy_date"]
    code = trade["code"]

    # 计算当天的日期
    try:
        bd = datetime.strptime(buy_date, "%Y-%m-%d")
        current_date = (bd + timedelta(days=day_in_trade)).strftime("%Y-%m-%d")
    except Exception:
        current_date = buy_date

    # 找最近的市场数据
    mkt = calendar.get(current_date, {})
    if not mkt:
        for d in sorted(calendar.keys(), reverse=True):
            if d <= current_date:
                mkt = calendar[d]
                break

    score = 0.50  # 基准50%

    # 1) 市场趋势
    trend = mkt.get("trend", "")
    if trend == "多头排列":
        score += 0.08
    elif trend == "短期偏多":
        score += 0.04
    elif trend == "空头排列":
        score -= 0.12
    elif trend == "短期偏空":
        score -= 0.06

    # 2) 量能
    vol_state = mkt.get("volume_state", "")
    if vol_state == "放量":
        score += 0.06
    elif vol_state == "缩量":
        score -= 0.08

    # 3) 情绪
    sent = mkt.get("sentiment", "")
    if sent == "强势":
        score += 0.06
    elif sent == "偏强":
        score += 0.03
    elif sent == "弱势":
        score -= 0.05
    elif sent == "恐慌":
        score -= 0.10

    # 4) 持仓天数效应 (越久越不利)
    if day_in_trade <= 2:
        score += 0.02  # 新股效应: 前2天略有利
    elif 3 <= day_in_trade <= 5:
        score -= 0.03  # 危险区
    elif 6 <= day_in_trade <= 8:
        score -= 0.02  # 危险区后恢复
    elif day_in_trade > 10:
        score -= 0.08  # 超时惩罚

    # 5) 当前盈亏状态
    if approx_pnl_pct > 5:
        score += 0.05  # 浮盈可观, 趋势可能继续
    elif approx_pnl_pct > 2:
        score += 0.02
    elif approx_pnl_pct < -5:
        score -= 0.08  # 浮亏严重, 可能继续恶化
    elif approx_pnl_pct < -3:
        score -= 0.04

    # 6) 波动率调整 (高波动股票需要更强的趋势才能持有)
    stock_vol = vol_data.get(code, 3.0)
    if stock_vol > 5.0:
        score -= 0.03  # 高波动 → 不确定性大
    elif stock_vol < 2.0:
        score += 0.02  # 低波动 → 更可预测

    # 钳制在 [0.05, 0.95]
    return max(0.05, min(0.95, score))


def approximate_daily_price(buy_price: float, sell_price: float,
                            hold_days: int, day: int,
                            market_cal: dict, buy_date: str) -> float:
    """近似估算持仓期间某天的价格"""
    if hold_days <= 0:
        return sell_price

    # 基础线性插值
    linear_price = buy_price + (sell_price - buy_price) * (day / hold_days)

    # 用市场波动调整
    try:
        bd = datetime.strptime(buy_date, "%Y-%m-%d")
        current_date = (bd + timedelta(days=day)).strftime("%Y-%m-%d")
    except Exception:
        return linear_price

    mkt = market_cal.get(current_date, {})
    if mkt:
        mkt_pct = mkt.get("pct_chg", 0)
        # 假设个股beta≈1.2, 叠加市场当日波动
        linear_price *= (1 + mkt_pct * 1.2 / 100)

    return linear_price


def backtest_strategies(round_trips, calendar, vol_data):
    """三种策略对比回测"""

    # 按股票分组用于波动率计算
    by_stock = defaultdict(list)
    for t in round_trips:
        by_stock[t["code"]].append(t)

    results = {
        "fixed": {"trades": [], "total_pnl": 0, "wins": 0, "losses": 0,
                   "exits": defaultdict(int), "total_fees_saved": 0},
        "prob": {"trades": [], "total_pnl": 0, "wins": 0, "losses": 0,
                  "exits": defaultdict(int), "total_fees_saved": 0},
        "adaptive": {"trades": [], "total_pnl": 0, "wins": 0, "losses": 0,
                      "exits": defaultdict(int), "total_fees_saved": 0},
    }

    for t in round_trips:
        actual_pnl = t["net_profit"]
        actual_pct = t["gross_pct"]
        hold_days = t["hold_days"]
        code = t["code"]
        buy_price = t["buy_price"]
        sell_price = t["sell_price"]
        qty = t["qty"]
        buy_date = t["buy_date"]

        # 获取波动率
        stock_vol = vol_data.get(code, 3.0)

        # ── 策略1: 固定规则 ──
        fixed_pnl, fixed_exit_day, fixed_reason = _sim_fixed(
            t, calendar, hold_days, actual_pct, actual_pnl)

        # ── 策略2: 概率加权 ──
        prob_pnl, prob_exit_day, prob_reason = _sim_probability(
            t, calendar, vol_data, hold_days, actual_pct, actual_pnl)

        # ── 策略3: 波动率自适应 ──
        adaptive_pnl, adaptive_exit_day, adaptive_reason = _sim_adaptive(
            t, calendar, stock_vol, hold_days, actual_pct, actual_pnl)

        for strat_name, (sim_pnl, exit_day, reason) in [
            ("fixed", (fixed_pnl, fixed_exit_day, fixed_reason)),
            ("prob", (prob_pnl, prob_exit_day, prob_reason)),
            ("adaptive", (adaptive_pnl, adaptive_exit_day, adaptive_reason)),
        ]:
            r = results[strat_name]
            r["total_pnl"] += sim_pnl
            r["exits"][reason] += 1
            if sim_pnl > 0:
                r["wins"] += 1
            elif sim_pnl < 0:
                r["losses"] += 1
            r["trades"].append({
                **t,
                "simulated_pnl": round(sim_pnl, 2),
                "exit_day": exit_day,
                "exit_reason": reason,
                "actual_pnl": actual_pnl,
                "improvement": round(actual_pnl - sim_pnl, 2),
            })

    return results


def _sim_fixed(trade, calendar, hold_days, actual_pct, actual_pnl):
    """固定规则模拟 (基准)"""
    if actual_pct <= FIXED["hard_stop"]:
        stop_pct = FIXED["hard_stop"]
        exit_factor = stop_pct / actual_pct if actual_pct != 0 else 1
        return actual_pnl * exit_factor * 0.8, 1, "fixed_hard_stop"

    if FIXED["danger_zone"][0] <= hold_days <= FIXED["danger_zone"][1]:
        if actual_pct < 0:
            return actual_pnl * 0.4, FIXED["danger_zone"][0], "fixed_danger_loss"
        elif actual_pct <= 2:
            return actual_pnl * 0.7, hold_days, "fixed_danger_thin"

    if actual_pct >= FIXED["take_profit_all"]:
        return actual_pnl * 0.75, hold_days, "fixed_take_all"

    if actual_pct >= FIXED["take_profit_half"]:
        return actual_pnl * 0.7, hold_days, "fixed_take_half"

    if hold_days > FIXED["max_hold"]:
        return actual_pnl * 0.85, FIXED["max_hold"], "fixed_overtime"

    return actual_pnl, hold_days, "fixed_pass"


def _sim_probability(trade, calendar, vol_data, hold_days,
                     actual_pct, actual_pnl):
    """概率加权策略模拟"""
    buy_date = trade["buy_date"]
    code = trade["code"]
    buy_price = trade["buy_price"]
    sell_price = trade["sell_price"]

    # 每天估算概率并决策
    for day in range(1, hold_days + 1):
        # 估算当天价格
        approx_price = approximate_daily_price(
            buy_price, sell_price, hold_days, day, calendar, buy_date)
        approx_pnl = (approx_price - buy_price) / buy_price * 100

        prob = compute_prob_score(
            trade, calendar, {}, vol_data, day, approx_pnl)

        # 硬止损: 概率无法挽救
        if approx_pnl <= FIXED["hard_stop"]:
            exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
            return actual_pnl * exit_factor * 0.8, day, "prob_hard_stop"

        # 软止损 + 概率判断
        if approx_pnl <= FIXED["soft_stop"]:
            if prob < PROB["exit_threshold"]:
                exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
                return actual_pnl * exit_factor * 0.7, day, "prob_soft_low_prob"
            # 概率高 → 减半但不全清
            elif prob < PROB["strong_hold_threshold"]:
                exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
                return actual_pnl * exit_factor * 0.6, day, "prob_soft_medium"

        # 危险区判断
        if FIXED["danger_zone"][0] <= day <= FIXED["danger_zone"][1]:
            if approx_pnl < 0:
                if prob < PROB["danger_exit_threshold"]:
                    exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
                    return actual_pnl * exit_factor * 0.5, day, "prob_danger_low"
                # 概率够高 → 再观察
            elif approx_pnl <= 2:
                if prob < 0.50:
                    exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
                    return actual_pnl * exit_factor * 0.6, day, "prob_danger_thin"

        # 超时判断
        if day > FIXED["max_hold"]:
            if prob < PROB["strong_hold_threshold"]:
                exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
                return actual_pnl * exit_factor * 0.85, day, "prob_overtime_low"
            # 概率>60% → 超时也继续持有

    # 持有到期
    return actual_pnl, hold_days, "prob_hold"


def _sim_adaptive(trade, calendar, stock_vol, hold_days,
                  actual_pct, actual_pnl):
    """波动率自适应策略模拟"""
    buy_date = trade["buy_date"]
    buy_price = trade["buy_price"]
    sell_price = trade["sell_price"]
    cost = buy_price

    # 自适应参数
    vol_factor = stock_vol / 3.0
    hard_stop = max(-10.0, min(-4.0, -7.0 * vol_factor))
    soft_stop = max(-5.0, min(-2.0, -3.0 * vol_factor))
    take_half = max(5.0, min(15.0, 8.0 * vol_factor))
    take_all = max(10.0, min(25.0, 15.0 * vol_factor))
    danger_start = 3 if stock_vol > 4.0 else 4  # 高波动延迟进入危险区
    danger_end = 5 if stock_vol > 4.0 else 6
    max_hold_adj = 12 if stock_vol > 4.0 else 10  # 高波动给更多时间

    for day in range(1, hold_days + 1):
        approx_price = approximate_daily_price(
            buy_price, sell_price, hold_days, day, calendar, buy_date)
        approx_pnl = (approx_price - buy_price) / buy_price * 100

        if approx_pnl <= hard_stop:
            exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
            return actual_pnl * exit_factor * 0.8, day, f"adapt_hard_{hard_stop:.0f}pct"

        if approx_pnl <= soft_stop:
            exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
            return actual_pnl * exit_factor * 0.65, day, f"adapt_soft_{soft_stop:.0f}pct"

        if danger_start <= day <= danger_end:
            if approx_pnl < 0:
                exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
                return actual_pnl * exit_factor * 0.5, day, "adapt_danger"

        if approx_pnl >= take_all:
            return actual_pnl * 0.8, day, f"adapt_take_all_{take_all:.0f}pct"

        if approx_pnl >= take_half:
            return actual_pnl * 0.7, day, f"adapt_take_half_{take_half:.0f}pct"

        if day > max_hold_adj:
            exit_factor = min(1.0, day / hold_days) if hold_days > 0 else 1
            return actual_pnl * exit_factor * 0.85, day, "adapt_overtime"

    return actual_pnl, hold_days, "adapt_hold"


def print_comparison(results):
    """输出对比报告"""
    print("=" * 70)
    print("  三种策略对比回测 (5年 3,817笔交易)")
    print("=" * 70)

    names = {
        "fixed": "固定规则 (基准)",
        "prob": "概率加权",
        "adaptive": "波动率自适应",
    }

    for key in ["fixed", "prob", "adaptive"]:
        r = results[key]
        n = len(r["trades"])
        total_pnl = r["total_pnl"]
        winners = r["wins"]
        losses = r["losses"]
        win_rate = winners / n * 100 if n > 0 else 0

        # 计算平均每笔盈亏
        avg_pnl = total_pnl / n if n > 0 else 0

        # 计算最大回撤 (累计)
        cum = 0
        max_cum = 0
        max_dd = 0
        for t in sorted(r["trades"], key=lambda x: x["buy_date"]):
            cum += t["simulated_pnl"]
            max_cum = max(max_cum, cum)
            dd = max_cum - cum
            max_dd = max(max_dd, dd)

        # 盈亏比
        win_trades = [t for t in r["trades"] if t["simulated_pnl"] > 0]
        loss_trades = [t for t in r["trades"] if t["simulated_pnl"] < 0]
        avg_win = sum(t["simulated_pnl"] for t in win_trades) / len(win_trades) if win_trades else 0
        avg_loss = sum(t["simulated_pnl"] for t in loss_trades) / len(loss_trades) if loss_trades else 0
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')

        print(f"\n{'─'*70}")
        print(f"  {names[key]}")
        print(f"{'─'*70}")
        print(f"  总盈亏: {total_pnl:+,.0f}元")
        print(f"  每笔平均: {avg_pnl:+,.0f}元")
        print(f"  胜率: {win_rate:.1f}% ({winners}赢/{losses}输)")
        print(f"  平均盈利: {avg_win:+,.0f}  平均亏损: {avg_loss:+,.0f}")
        print(f"  盈亏比: {profit_factor:.2f}")
        print(f"  最大回撤: {max_dd:,.0f}元")

        # 退出原因分布
        print(f"\n  退出原因分布:")
        exit_dist = sorted(r["exits"].items(), key=lambda x: x[1], reverse=True)
        for reason, count in exit_dist[:8]:
            pct = count / n * 100
            bar = "█" * int(pct / 2)
            print(f"    {reason:<30}: {count:>4} ({pct:>5.1f}%) {bar}")

    # 相对改善
    fixed_pnl = results["fixed"]["total_pnl"]
    print(f"\n{'='*70}")
    print(f"  相对基准改善")
    print(f"{'='*70}")
    for key in ["prob", "adaptive"]:
        r = results[key]
        improvement = r["total_pnl"] - fixed_pnl
        pct = improvement / abs(fixed_pnl) * 100 if fixed_pnl != 0 else 0
        print(f"  {names[key]}: {improvement:+,.0f}元 ({pct:+.1f}%)")

    # 关键案例: 概率策略挽救的最大亏损 vs 错杀的最大盈利
    print(f"\n{'='*70}")
    print(f"  概率策略关键案例分析")
    print(f"{'='*70}")

    prob_trades = results["prob"]["trades"]
    # 挽救的交易: 实际亏损但概率策略减少亏损 (simulated_pnl > actual_pnl)
    saved = [t for t in prob_trades
             if t["actual_pnl"] < -200 and t["simulated_pnl"] > t["actual_pnl"]]
    saved.sort(key=lambda x: x["simulated_pnl"] - x["actual_pnl"], reverse=True)

    print(f"\n  挽救最大的5笔 (概率策略减少亏损):")
    for t in saved[:5]:
        actual = t["actual_pnl"]
        sim = t["simulated_pnl"]
        saved_amt = sim - actual  # positive = saved money
        print(f"    {t['name']}({t['code']}) {t['buy_date']}: "
              f"实际{actual:,.0f} → 模拟{sim:,.0f} 挽回+{saved_amt:,.0f}元 "
              f"({t['gross_pct']:.1f}% 持{t['hold_days']}天 → 第{t['exit_day']}天{t['exit_reason']})")

    # 错杀的: 实际盈利但概率策略少赚了 (simulated_pnl < actual_pnl)
    killed = [t for t in prob_trades
              if t["actual_pnl"] > 200 and t["simulated_pnl"] < t["actual_pnl"]]
    killed.sort(key=lambda x: x["actual_pnl"] - x["simulated_pnl"], reverse=True)

    if killed:
        print(f"\n  少赚最大的5笔 (概率策略过早退出):")
        for t in killed[:5]:
            actual = t["actual_pnl"]
            sim = t["simulated_pnl"]
            lost = actual - sim  # positive = missed profit
            print(f"    {t['name']}({t['code']}) {t['buy_date']}: "
                  f"实际{actual:,.0f} → 模拟{sim:,.0f} 少赚-{lost:,.0f}元 "
                  f"({t['gross_pct']:.1f}% 持{t['hold_days']}天 → 第{t['exit_day']}天{t['exit_reason']})")

    # 净挽救 = 挽救总金额 - 少赚总金额
    total_saved = sum(t["simulated_pnl"] - t["actual_pnl"] for t in saved)
    total_killed = sum(t["actual_pnl"] - t["simulated_pnl"] for t in killed) if killed else 0
    print(f"\n  实际挽回亏损: +{total_saved:,.0f}元 ({len(saved)}笔)")
    print(f"  少赚的盈利: -{total_killed:,.0f}元 ({len(killed)}笔)")
    print(f"  净效果: {total_saved - total_killed:+,.0f}元")


def main():
    print("加载交易数据...")
    round_trips = load_round_trips()
    print(f"加载 {len(round_trips)} 笔往返交易")

    print("加载市场日历...")
    calendar = load_calendar()

    print("估算个股波动率...")
    by_stock = defaultdict(list)
    for t in round_trips:
        by_stock[t["code"]].append(t)
    vol_data = estimate_volatility(by_stock)
    high_vol = sum(1 for v in vol_data.values() if v > 5)
    low_vol = sum(1 for v in vol_data.values() if v < 2)
    print(f"波动率分布: {len(vol_data)}只, 高波动(>5%): {high_vol}, 低波动(<2%): {low_vol}")

    print("\n运行三种策略回测...")
    results = backtest_strategies(round_trips, calendar, vol_data)

    print_comparison(results)

    # 保存
    out = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {},
    }
    for key in ["fixed", "prob", "adaptive"]:
        r = results[key]
        n = len(r["trades"])
        out["summary"][key] = {
            "total_pnl": round(r["total_pnl"], 2),
            "avg_pnl": round(r["total_pnl"] / n, 2) if n > 0 else 0,
            "wins": r["wins"],
            "losses": r["losses"],
            "win_rate": round(r["wins"] / n * 100, 1) if n > 0 else 0,
        }
    out_path = os.path.join(DATA_DIR, "probability_backtest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果已保存: {out_path}")


if __name__ == "__main__":
    main()
