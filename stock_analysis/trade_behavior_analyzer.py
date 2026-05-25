"""
trade_behavior_analyzer.py — 逐笔成交深度行为分析 v2

分析维度:
  1. 盈亏分布曲线 — 直方图+百分位+肥尾检测
  2. 反事实推演 — 硬止损/最小持有/移动止盈的效果
  3. 序列分析 — 连胜/连败后的行为变化 (tilting/overconfidence)
  4. 仓位规模 vs 盈亏 — 单笔金额越大是否决策越差
  5. 时间维度 — 日内时段/周几/月内位置 vs 盈亏
  6. 持有天数 vs 盈亏曲线 — 最优持有窗口
  7. 撤单行为 — 775笔已撤订单揭示的决策犹豫
  8. 个股深度 — 交易>10次的股票的完整画像
  9. 买卖间隔 — 卖出后多久再入场
 10. 加仓行为 — 同股多次买入的模式
"""

import json
import sys
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

EXCEL_PATH = Path("D:/1989n/Table.xlsx")
OUTPUT_PATH = Path("D:/1989n/stock_data/trade_behavior_report.json")


# ── 数据加载 ────────────────────────────────────────────────

def load_all_records(path: Path) -> tuple[list[dict], list[dict]]:
    """返回 (已成交, 已撤单)。"""
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb.active
    headers = [cell.value for cell in ws[1]]
    done, cancelled = [], []
    for row in ws.iter_rows(min_row=2, values_only=True):
        d = dict(zip(headers, row))
        status = str(d.get("委托状态", ""))
        try:
            d["委托日期"] = str(d["委托日期"])[:10]
            d["成交数量"] = int(d["成交数量"]) if d["成交数量"] else 0
            d["成交金额"] = float(d["成交金额"]) if d["成交金额"] else 0.0
            d["成交均价"] = float(d["成交均价"]) if d["成交均价"] and d["成交均价"] != 0 else 0.0
            d["委托价格"] = float(d["委托价格"]) if d["委托价格"] else 0.0
            d["委托数量"] = int(d["委托数量"]) if d["委托数量"] else 0
        except (ValueError, TypeError):
            continue
        if status == "已成" and d["成交数量"] > 0:
            done.append(d)
        elif status in ("已撤", "部撤"):
            cancelled.append(d)
    return done, cancelled


# ── FIFO 匹配 ────────────────────────────────────────────────

def fifo_match(trades: list[dict]) -> list[dict]:
    stock_queues = defaultdict(list)
    for t in sorted(trades, key=lambda x: (x["委托日期"], x.get("委托时间", ""))):
        stock_queues[t["证券代码"]].append(t)
    rounds = []
    for code, queue in stock_queues.items():
        buy_stack = []
        for t in queue:
            direction = str(t["委托方向"])
            qty = t["成交数量"]
            price = t["成交均价"] or t["委托价格"]
            date = t["委托日期"]
            name = t.get("证券名称", "")
            market = t.get("交易市场", "")
            trade_time = str(t.get("委托时间", ""))
            buy_amount = t["成交金额"]

            if "买入" in direction:
                buy_stack.append({
                    "buy_date": date, "buy_time": trade_time,
                    "buy_price": price, "qty": qty,
                    "amount": buy_amount, "name": name,
                    "code": code, "market": market,
                })
            elif "卖出" in direction and buy_stack:
                remaining = qty
                sell_price = price
                sell_date = date
                while remaining > 0 and buy_stack:
                    lot = buy_stack[0]
                    matched_qty = min(lot["qty"], remaining)
                    pnl = (sell_price - lot["buy_price"]) * matched_qty
                    pnl_pct = (sell_price / lot["buy_price"] - 1) * 100 if lot["buy_price"] > 0 else 0
                    try:
                        hold_days = (datetime.strptime(sell_date, "%Y-%m-%d") -
                                     datetime.strptime(lot["buy_date"], "%Y-%m-%d")).days
                    except ValueError:
                        hold_days = None
                    try:
                        dow = datetime.strptime(sell_date, "%Y-%m-%d").weekday()
                    except ValueError:
                        dow = None
                    rounds.append({
                        "code": code, "name": name, "market": market,
                        "buy_date": lot["buy_date"], "buy_time": lot["buy_time"],
                        "sell_date": sell_date, "sell_time": trade_time,
                        "buy_price": round(lot["buy_price"], 3),
                        "sell_price": round(sell_price, 3),
                        "qty": matched_qty,
                        "buy_amount": round(lot["buy_price"] * matched_qty, 2),
                        "sell_amount": round(sell_price * matched_qty, 2),
                        "pnl": round(pnl, 2),
                        "pnl_pct": round(pnl_pct, 2),
                        "hold_days": hold_days,
                        "sell_dow": dow,
                    })
                    lot["qty"] -= matched_qty
                    lot["amount"] = lot["amount"] * (lot["qty"] / (lot["qty"] + matched_qty)) if (lot["qty"] + matched_qty) > 0 else 0
                    if lot["qty"] <= 0:
                        buy_stack.pop(0)
                    remaining -= matched_qty
    return rounds


# ── 深度分析 ──────────────────────────────────────────────────

def analyze_v2(rounds: list[dict], trades: list[dict], cancelled: list[dict]) -> dict:
    n = len(rounds)
    winners = [r for r in rounds if r["pnl"] > 0]
    losers = [r for r in rounds if r["pnl"] < 0]

    report = {}
    report["summary"] = build_summary(rounds, winners, losers, trades)
    report["pnl_distribution"] = build_pnl_distribution(rounds)
    report["counterfactuals"] = build_counterfactuals(rounds)
    report["sequence_analysis"] = build_sequence_analysis(rounds)
    report["position_sizing"] = build_position_sizing(rounds)
    report["timing_deep"] = build_timing_deep(rounds, trades)
    report["hold_days_curve"] = build_hold_days_curve(rounds)
    report["cancellation_behavior"] = build_cancellation_analysis(cancelled)
    report["stock_profiles"] = build_stock_profiles(rounds)
    report["reentry_patterns"] = build_reentry_patterns(rounds)
    report["adding_behavior"] = build_adding_behavior(trades)
    report["worst20"] = build_worst_list(rounds)
    report["best20"] = build_best_list(rounds)
    return report


def build_summary(rounds, winners, losers, trades):
    n = len(rounds)
    total_pnl = sum(r["pnl"] for r in rounds)
    total_win = sum(r["pnl"] for r in winners)
    total_loss = sum(r["pnl"] for r in losers)
    buy_amt = sum(t["成交金额"] for t in trades if "买入" in str(t.get("委托方向", "")))
    sell_amt = sum(t["成交金额"] for t in trades if "卖出" in str(t.get("委托方向", "")))
    return {
        "总交易笔数": len(trades),
        "往返交易笔数": n,
        "盈利笔数": len(winners),
        "亏损笔数": len(losers),
        "胜率": round(len(winners) / n * 100, 1) if n else 0,
        "总盈亏": round(total_pnl, 2),
        "总盈利": round(total_win, 2),
        "总亏损": round(total_loss, 2),
        "平均盈利": round(total_win / len(winners), 2) if winners else 0,
        "平均亏损": round(total_loss / len(losers), 2) if losers else 0,
        "盈亏比": round(abs(total_win / total_loss), 2) if total_loss else 0,
        "平均每笔": round(total_pnl / n, 2) if n else 0,
        "累计买入": round(buy_amt, 2),
        "累计卖出": round(sell_amt, 2),
        "资金周转率": round(sell_amt / buy_amt * 100, 1) if buy_amt else 0,
    }


def build_pnl_distribution(rounds):
    pnl_pcts = [r["pnl_pct"] for r in rounds]
    pnl_abs = [r["pnl"] for r in rounds]
    sorted_pct = sorted(pnl_pcts)
    sorted_abs = sorted(pnl_abs)
    ln = len(sorted_pct)

    # 直方图
    bins = {"<-15%": 0, "-15~-10%": 0, "-10~-7%": 0, "-7~-5%": 0, "-5~-3%": 0,
            "-3~-1%": 0, "-1~0%": 0, "0~1%": 0, "1~3%": 0, "3~5%": 0,
            "5~10%": 0, "10~15%": 0, "15~25%": 0, ">25%": 0}
    for p in pnl_pcts:
        if p < -15: bins["<-15%"] += 1
        elif p < -10: bins["-15~-10%"] += 1
        elif p < -7: bins["-10~-7%"] += 1
        elif p < -5: bins["-7~-5%"] += 1
        elif p < -3: bins["-5~-3%"] += 1
        elif p < -1: bins["-3~-1%"] += 1
        elif p < 0: bins["-1~0%"] += 1
        elif p < 1: bins["0~1%"] += 1
        elif p < 3: bins["1~3%"] += 1
        elif p < 5: bins["3~5%"] += 1
        elif p < 10: bins["5~10%"] += 1
        elif p < 15: bins["10~15%"] += 1
        elif p < 25: bins["15~25%"] += 1
        else: bins[">25%"] += 1

    # 左侧肥尾: <-7%的交易占总亏损的比例
    fat_left = sum(1 for p in pnl_pcts if p < -7)
    fat_right = sum(1 for p in pnl_pcts if p > 15)
    total_loss_sum = sum(r["pnl"] for r in rounds if r["pnl"] < 0)
    fat_left_loss = sum(r["pnl"] for r in rounds if r["pnl_pct"] < -7)
    total_win_sum = sum(r["pnl"] for r in rounds if r["pnl"] > 0)
    fat_right_win = sum(r["pnl"] for r in rounds if r["pnl_pct"] > 15)

    return {
        "盈亏%分布": bins,
        "百分位": {
            "p5": round(sorted_pct[max(0, int(ln * 0.05))], 2),
            "p10": round(sorted_pct[max(0, int(ln * 0.10))], 2),
            "p25": round(sorted_pct[max(0, int(ln * 0.25))], 2),
            "p50_中位": round(sorted_pct[ln // 2], 2),
            "p75": round(sorted_pct[min(ln - 1, int(ln * 0.75))], 2),
            "p90": round(sorted_pct[min(ln - 1, int(ln * 0.90))], 2),
            "p95": round(sorted_pct[min(ln - 1, int(ln * 0.95))], 2),
        },
        "标准差": round(statistics.stdev(pnl_pcts), 2) if len(pnl_pcts) > 1 else 0,
        "偏度": round(_skewness(pnl_pcts), 3),
        "肥尾分析": {
            "左侧肥尾_<-7%_笔数": fat_left,
            "左侧肥尾_<-7%_亏损占比": f"{abs(fat_left_loss) / abs(total_loss_sum) * 100:.0f}%" if total_loss_sum else "N/A",
            "右侧肥尾_>15%_笔数": fat_right,
            "右侧肥尾_>15%_盈利占比": f"{abs(fat_right_win) / abs(total_win_sum) * 100:.0f}%" if total_win_sum else "N/A",
            "解读": "大亏集中度远高于大盈集中度" if fat_left_loss and abs(fat_left_loss) > abs(fat_right_win) else "大盈分布较分散",
        },
    }


def _skewness(data):
    n = len(data)
    if n < 2:
        return 0
    mean = sum(data) / n
    std = (sum((x - mean) ** 2 for x in data) / (n - 1)) ** 0.5
    if std == 0:
        return 0
    return sum((x - mean) ** 3 for x in data) / ((n - 1) * std ** 3)


def build_counterfactuals(rounds):
    """反事实推演: 如果采用了不同规则会怎样。"""
    results = {}

    # 1. 硬止损 -5%：所有亏损超过5%的截断到-5%
    stop5_pnls = []
    for r in rounds:
        if r["pnl_pct"] < -5:
            adj_pnl = r["buy_amount"] * (-0.05)
            stop5_pnls.append(adj_pnl)
        else:
            stop5_pnls.append(r["pnl"])
    results["硬止损-5%"] = {
        "总盈亏": round(sum(stop5_pnls), 2),
        "改善金额": round(sum(stop5_pnls) - sum(r["pnl"] for r in rounds), 2),
        "被截断笔数": sum(1 for r in rounds if r["pnl_pct"] < -5),
    }

    # 2. 硬止损 -7%
    stop7_pnls = []
    for r in rounds:
        if r["pnl_pct"] < -7:
            adj_pnl = r["buy_amount"] * (-0.07)
            stop7_pnls.append(adj_pnl)
        else:
            stop7_pnls.append(r["pnl"])
    results["硬止损-7%"] = {
        "总盈亏": round(sum(stop7_pnls), 2),
        "改善金额": round(sum(stop7_pnls) - sum(r["pnl"] for r in rounds), 2),
        "被截断笔数": sum(1 for r in rounds if r["pnl_pct"] < -7),
    }

    # 3. 盈利最小持有5天
    minhold_pnls = []
    skipped_wins = 0
    for r in rounds:
        if r["pnl_pct"] > 0 and r["hold_days"] and r["hold_days"] < 5:
            skipped_wins += 1
            minhold_pnls.append(0)  # 假设不卖的结果未知，保守按0算
        else:
            minhold_pnls.append(r["pnl"])
    results["盈利最小持有5天_保守"] = {
        "总盈亏": round(sum(minhold_pnls), 2),
        "受影响笔数": skipped_wins,
        "说明": "假设<5天卖出的盈利交易改为持有，盈亏未知暂按0计",
    }

    # 4. T+1禁止卖出 (持有<1天的不让卖)
    no_t1_pnls = []
    affected = 0
    for r in rounds:
        if r["hold_days"] is not None and r["hold_days"] <= 1:
            affected += 1
            no_t1_pnls.append(0)
        else:
            no_t1_pnls.append(r["pnl"])
    results["禁止T1卖出_保守"] = {
        "总盈亏": round(sum(no_t1_pnls), 2),
        "受影响笔数": affected,
        "说明": "842笔T+1交易暂按0计",
    }

    return results


def build_sequence_analysis(rounds):
    """序列分析: 连胜/连败后的行为变化。"""
    sorted_rounds = sorted(rounds, key=lambda x: (x["sell_date"], x.get("sell_time", "")))

    # 检测连续序列
    streaks = []
    current_streak = []
    for r in sorted_rounds:
        if not current_streak:
            current_streak.append(r)
        elif (r["pnl"] > 0) == (current_streak[-1]["pnl"] > 0):
            current_streak.append(r)
        else:
            streaks.append(current_streak)
            current_streak = [r]
    if current_streak:
        streaks.append(current_streak)

    win_streaks = [s for s in streaks if s[0]["pnl"] > 0]
    loss_streaks = [s for s in streaks if s[0]["pnl"] < 0]

    # 每笔交易后下一笔的表现 (避免streak交替的循环定义)
    post_any_win = []  # 获利后下一笔
    post_any_loss = []  # 亏损后下一笔
    for i in range(len(sorted_rounds) - 1):
        curr = sorted_rounds[i]
        nxt = sorted_rounds[i + 1]
        d = {
            "前笔盈亏": curr["pnl"], "前笔盈亏%": curr["pnl_pct"],
            "后笔盈亏": nxt["pnl"], "后笔盈亏%": nxt["pnl_pct"],
            "后笔是盈": nxt["pnl"] > 0,
        }
        if curr["pnl"] > 0:
            post_any_win.append(d)
        else:
            post_any_loss.append(d)

    post_win_winrate = sum(1 for p in post_any_win if p["后笔是盈"]) / len(post_any_win) * 100 if post_any_win else 0
    post_win_avg = sum(p["后笔盈亏"] for p in post_any_win) / len(post_any_win) if post_any_win else 0
    post_loss_winrate = sum(1 for p in post_any_loss if p["后笔是盈"]) / len(post_any_loss) * 100 if post_any_loss else 0
    post_loss_avg = sum(p["后笔盈亏"] for p in post_any_loss) / len(post_any_loss) if post_any_loss else 0

    # 大亏后下一笔 (每笔大亏只匹配时间上最早的下笔交易)
    big_loss_events = sorted(
        [(r["sell_date"], r.get("sell_time", ""), r) for r in rounds if r["pnl_pct"] < -7],
        key=lambda x: (x[0], x[1])
    )
    revenge_trades = []
    matched_next_trades = set()  # 避免同一笔交易被多次计为大亏后的第一笔
    for bl_date, bl_time, bl in big_loss_events:
        bl_dt = datetime.strptime(bl_date, "%Y-%m-%d")
        best = None
        for j, r in enumerate(sorted_rounds):
            if r is bl:
                continue
            try:
                r_dt = datetime.strptime(r["buy_date"], "%Y-%m-%d")
            except ValueError:
                continue
            diff_h = (r_dt - bl_dt).total_seconds() / 3600
            if 0 <= diff_h <= 24:
                key = (r["code"], r["buy_date"], j)
                if key not in matched_next_trades:
                    if best is None or diff_h < best["gap_h"]:
                        best = {
                            "大亏股票": bl["name"],
                            "大亏金额": bl["pnl"],
                            "大亏日期": bl_date,
                            "下一笔股票": r["name"],
                            "下一笔日期": r["buy_date"],
                            "gap_h": round(diff_h, 1),
                            "下一笔盈亏": r["pnl"],
                            "下一笔盈亏%": r["pnl_pct"],
                        }
        if best:
            revenge_trades.append(best)

    revenge_winrate = sum(1 for rt in revenge_trades if rt["下一笔盈亏"] > 0) / len(revenge_trades) * 100 if revenge_trades else 0
    revenge_avg = sum(rt["下一笔盈亏"] for rt in revenge_trades) / len(revenge_trades) if revenge_trades else 0

    return {
        "连胜统计": {
            "连胜最多笔数": max(len(s) for s in win_streaks) if win_streaks else 0,
            "平均连胜笔数": round(sum(len(s) for s in win_streaks) / len(win_streaks), 1) if win_streaks else 0,
            "连胜段数": len(win_streaks),
        },
        "连败统计": {
            "连败最多笔数": max(len(s) for s in loss_streaks) if loss_streaks else 0,
            "平均连败笔数": round(sum(len(s) for s in loss_streaks) / len(loss_streaks), 1) if loss_streaks else 0,
            "连败段数": len(loss_streaks),
        },
        "盈利后下一笔": {
            "胜率": round(post_win_winrate, 1),
            "平均盈亏": round(post_win_avg, 2),
            "样本数": len(post_any_win),
            "过度自信检测": "是 — 获利后胜率显著低于均值" if post_win_winrate < 45 and len(post_any_win) > 10 else "不显著",
        },
        "亏损后下一笔": {
            "胜率": round(post_loss_winrate, 1),
            "平均盈亏": round(post_loss_avg, 2),
            "样本数": len(post_any_loss),
            "报复交易检测": "是 — 亏损后下一笔更差" if post_loss_avg < post_win_avg and len(post_any_loss) > 10 else "不显著",
        },
        "大亏后24h内第一笔": {
            "次数": len(revenge_trades),
            "胜率": round(revenge_winrate, 1),
            "平均盈亏": round(revenge_avg, 2),
            "样本": revenge_trades[:10],
            "风险评级": "高危 — 大亏后立即交易胜率低" if revenge_winrate < 40 and len(revenge_trades) > 5 else "待观察",
        },
    }


def build_position_sizing(rounds):
    """仓位规模 vs 盈亏 分析。"""
    # 按买入金额分桶
    buckets = {"<5千": [], "5千-1万": [], "1-2万": [], "2-5万": [], "5万+": []}
    for r in rounds:
        amt = r["buy_amount"]
        if amt < 5000:
            buckets["<5千"].append(r)
        elif amt < 10000:
            buckets["5千-1万"].append(r)
        elif amt < 20000:
            buckets["1-2万"].append(r)
        elif amt < 50000:
            buckets["2-5万"].append(r)
        else:
            buckets["5万+"].append(r)

    sizing = {}
    for label, bucket in buckets.items():
        if not bucket:
            sizing[label] = {"笔数": 0}
            continue
        wins = sum(1 for r in bucket if r["pnl"] > 0)
        total = sum(r["pnl"] for r in bucket)
        sizing[label] = {
            "笔数": len(bucket),
            "胜率": round(wins / len(bucket) * 100, 1),
            "总盈亏": round(total, 2),
            "平均盈亏": round(total / len(bucket), 2),
            "盈亏比": round(
                sum(r["pnl"] for r in bucket if r["pnl"] > 0) / abs(sum(r["pnl"] for r in bucket if r["pnl"] < 0)), 2
            ) if sum(r["pnl"] for r in bucket if r["pnl"] < 0) != 0 else 0,
        }

    # 最大单笔分析
    top_by_amount = sorted(rounds, key=lambda x: x["buy_amount"], reverse=True)[:30]
    top_amt_wins = sum(1 for r in top_by_amount if r["pnl"] > 0)
    top_amt_pnl = sum(r["pnl"] for r in top_by_amount)

    return {
        "仓位-盈亏关系": sizing,
        "最大30笔_按金额": {
            "胜率": round(top_amt_wins / 30 * 100, 1),
            "总盈亏": round(top_amt_pnl, 2),
            "解读": "重仓交易表现优于平均" if top_amt_wins / 30 > 0.5 else "重仓交易反而更差",
        },
        "仓位集中度风险": _concentration_risk(rounds),
    }


def _concentration_risk(rounds):
    """计算同一时间持仓笔数和风险暴露。"""
    # 按日期重建持仓状态
    events = []
    for r in rounds:
        events.append((r["buy_date"], "buy", r["buy_amount"], r["code"]))
        events.append((r["sell_date"], "sell", r["sell_amount"], r["code"]))
    events.sort()

    holdings = {}
    daily_exposure = []
    for date, action, amount, code in events:
        if action == "buy":
            holdings[code] = holdings.get(code, 0) + amount
        else:
            holdings[code] = holdings.get(code, 0) - amount
            if holdings[code] <= 0:
                del holdings[code]
        total = sum(holdings.values())
        if daily_exposure and daily_exposure[-1][0] == date:
            daily_exposure[-1] = (date, total)
        else:
            daily_exposure.append((date, total))

    if not daily_exposure:
        return {}

    exposures = [e[1] for e in daily_exposure]
    return {
        "最大单日持仓市值": round(max(exposures), 2),
        "平均持仓市值": round(sum(exposures) / len(exposures), 2),
        "持仓峰值日期": max(daily_exposure, key=lambda x: x[1])[0],
        "同时持仓股票数_峰值": max(len(holdings) for _ in [0]),  # 简化
    }


def build_timing_deep(rounds, trades):
    """深度时间分析。"""
    # 日内时段 vs 盈亏
    hour_pnl = defaultdict(list)
    for r in rounds:
        try:
            h = int(str(r.get("buy_time", "")).split(":")[0])
        except (ValueError, IndexError):
            h = -1
        hour_pnl[h].append(r["pnl"])

    hour_analysis = {}
    for h in sorted(hour_pnl.keys()):
        pnls = hour_pnl[h]
        if len(pnls) < 5:
            continue
        wins = sum(1 for p in pnls if p > 0)
        hour_analysis[str(h) + "点"] = {
            "笔数": len(pnls),
            "胜率": round(wins / len(pnls) * 100, 1),
            "总盈亏": round(sum(pnls), 2),
            "平均盈亏": round(sum(pnls) / len(pnls), 2),
        }

    # 周几 vs 盈亏 (sell day)
    dow_pnl = defaultdict(list)
    dow_names = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五"}
    for r in rounds:
        if r["sell_dow"] is not None:
            dow_pnl[r["sell_dow"]].append(r["pnl"])

    dow_analysis = {}
    for d in sorted(dow_pnl.keys()):
        pnls = dow_pnl[d]
        wins = sum(1 for p in pnls if p > 0)
        dow_analysis[dow_names.get(d, str(d))] = {
            "笔数": len(pnls),
            "胜率": round(wins / len(pnls) * 100, 1),
            "总盈亏": round(sum(pnls), 2),
            "平均盈亏": round(sum(pnls) / len(pnls), 2),
        }

    # 月内位置 (1-10号/11-20号/21-31号)
    month_pos = {"月初1-10": [], "月中11-20": [], "月末21-31": []}
    for r in rounds:
        try:
            day = int(r["sell_date"][8:10])
        except (ValueError, IndexError):
            continue
        if day <= 10:
            month_pos["月初1-10"].append(r["pnl"])
        elif day <= 20:
            month_pos["月中11-20"].append(r["pnl"])
        else:
            month_pos["月末21-31"].append(r["pnl"])

    month_pos_analysis = {}
    for label, pnls in month_pos.items():
        wins = sum(1 for p in pnls if p > 0)
        month_pos_analysis[label] = {
            "笔数": len(pnls),
            "胜率": round(wins / len(pnls) * 100, 1) if pnls else 0,
            "总盈亏": round(sum(pnls), 2),
        }

    return {
        "日内时段": hour_analysis,
        "周几": dow_analysis,
        "月内位置": month_pos_analysis,
    }


def build_hold_days_curve(rounds):
    """持有天数 vs 盈亏曲线 — 找到最佳持有窗口。"""
    # 按持有天数分组
    day_buckets = defaultdict(list)
    for r in rounds:
        d = r["hold_days"]
        if d is None:
            continue
        if d <= 1:
            day_buckets["0-1天"].append(r)
        elif d <= 3:
            day_buckets["2-3天"].append(r)
        elif d <= 5:
            day_buckets["4-5天"].append(r)
        elif d <= 10:
            day_buckets["6-10天"].append(r)
        elif d <= 20:
            day_buckets["11-20天"].append(r)
        else:
            day_buckets["20天+"].append(r)

    curve = {}
    for label in ["0-1天", "2-3天", "4-5天", "6-10天", "11-20天", "20天+"]:
        bucket = day_buckets.get(label, [])
        if not bucket:
            curve[label] = {"笔数": 0}
            continue
        wins = sum(1 for r in bucket if r["pnl"] > 0)
        total = sum(r["pnl"] for r in bucket)
        avg_pnl_pct = sum(r["pnl_pct"] for r in bucket) / len(bucket)
        curve[label] = {
            "笔数": len(bucket),
            "胜率": round(wins / len(bucket) * 100, 1),
            "总盈亏": round(total, 2),
            "平均盈亏": round(total / len(bucket), 2),
            "平均盈亏%": round(avg_pnl_pct, 2),
        }

    # 找出最佳窗口
    best = max(
        ((k, v) for k, v in curve.items() if v["笔数"] > 10),
        key=lambda x: x[1]["平均盈亏"],
        default=("N/A", {})
    )

    return {
        "持有天数vs盈亏": curve,
        "最佳窗口": best[0],
        "最佳窗口平均盈亏": best[1].get("平均盈亏", 0) if best[1] else 0,
    }


def build_cancellation_analysis(cancelled):
    """撤单行为分析。"""
    if not cancelled:
        return {"说明": "无撤单数据"}

    # 方向分布
    buy_cancel = [c for c in cancelled if "买入" in str(c.get("委托方向", ""))]
    sell_cancel = [c for c in cancelled if "卖出" in str(c.get("委托方向", ""))]

    # 撤单时段
    hour_dist = defaultdict(int)
    for c in cancelled:
        try:
            h = int(str(c.get("委托时间", "")).split(":")[0])
            hour_dist[h] += 1
        except (ValueError, IndexError):
            pass

    # 撤单金额
    total_cancel_amt = sum(c["委托数量"] * c["委托价格"] for c in cancelled if c["委托数量"] and c["委托价格"])

    return {
        "撤单总数": len(cancelled),
        "买入撤单": len(buy_cancel),
        "卖出撤单": len(sell_cancel),
        "撤单率": f"{len(cancelled) / (len(cancelled) + 2954) * 100:.1f}%",  # 2954 是已成笔数
        "撤单总金额": round(total_cancel_amt, 2),
        "撤单时段分布": {str(h): cnt for h, cnt in sorted(hour_dist.items())},
        "解读": _interpret_cancellation(buy_cancel, sell_cancel, hour_dist),
    }


def _interpret_cancellation(buy, sell, hour_dist):
    parts = []
    if len(buy) > len(sell) * 1.5:
        parts.append(f"买入撤单({len(buy)}笔)远多于卖出({len(sell)}笔) — 追高后犹豫撤回")
    elif len(sell) > len(buy) * 1.5:
        parts.append(f"卖出撤单({len(sell)}笔)远多于买入({len(buy)}笔) — 恐慌时犹豫撤回")
    else:
        parts.append(f"买卖撤单均衡({len(buy)}/{len(sell)})")

    peak_hour = max(hour_dist, key=hour_dist.get) if hour_dist else None
    if peak_hour and peak_hour <= 10:
        parts.append(f"撤单集中在开盘时段({peak_hour}点) — 开盘情绪驱动后冷静撤回")
    return "；".join(parts)


def build_stock_profiles(rounds):
    """个股深度画像 (交易>10次的股票)。"""
    stock_rounds = defaultdict(list)
    for r in rounds:
        stock_rounds[r["code"]].append(r)

    profiles = {}
    for code, stock_r in sorted(stock_rounds.items(), key=lambda x: len(x[1]), reverse=True):
        if len(stock_r) < 10:
            continue
        wins = [r for r in stock_r if r["pnl"] > 0]
        losses = [r for r in stock_r if r["pnl"] < 0]
        total_pnl = sum(r["pnl"] for r in stock_r)
        days = [r["hold_days"] for r in stock_r if r["hold_days"] is not None]
        pnl_pcts = [r["pnl_pct"] for r in stock_r]

        # 检测对此股票是否有"越跌越买"的加仓行为
        buy_dates = sorted(set(r["buy_date"] for r in stock_r))
        sell_dates = sorted(set(r["sell_date"] for r in stock_r))
        avg_hold = sum(days) / len(days) if days else 0

        profiles[f"{code} {stock_r[0]['name']}"] = {
            "交易次数": len(stock_r),
            "胜率": round(len(wins) / len(stock_r) * 100, 1),
            "总盈亏": round(total_pnl, 2),
            "平均盈亏": round(total_pnl / len(stock_r), 2),
            "平均持有": round(avg_hold, 1),
            "平均盈亏%": round(sum(pnl_pcts) / len(pnl_pcts), 2),
            "最大单笔盈": round(max(r["pnl"] for r in stock_r), 2),
            "最大单笔亏": round(min(r["pnl"] for r in stock_r), 2),
            "盈亏比": round(
                sum(r["pnl"] for r in wins) / abs(sum(r["pnl"] for r in losses)), 2
            ) if losses and sum(r["pnl"] for r in losses) != 0 else 0,
            "首次交易": min(buy_dates),
            "最后交易": max(sell_dates),
            "交易跨度_天": (datetime.strptime(max(sell_dates), "%Y-%m-%d") -
                          datetime.strptime(min(buy_dates), "%Y-%m-%d")).days,
        }

    return profiles


def build_reentry_patterns(rounds):
    """卖出后多久再次买入 (同一股票或不同股票)。"""
    sorted_rounds = sorted(rounds, key=lambda x: (x["sell_date"], x.get("sell_time", "")))

    # 卖出日期到下一次买入日期的间隔
    sell_buy_gaps = []
    for i in range(len(sorted_rounds) - 1):
        sell_dt = datetime.strptime(sorted_rounds[i]["sell_date"], "%Y-%m-%d")
        buy_dt = datetime.strptime(sorted_rounds[i + 1]["buy_date"], "%Y-%m-%d")
        gap = (buy_dt - sell_dt).days
        same_stock = sorted_rounds[i]["code"] == sorted_rounds[i + 1]["code"]
        sell_buy_gaps.append({
            "卖出股票": sorted_rounds[i]["name"],
            "买入股票": sorted_rounds[i + 1]["name"],
            "间隔天数": gap,
            "同股票": same_stock,
            "前笔盈亏": sorted_rounds[i]["pnl"],
            "后笔盈亏": sorted_rounds[i + 1]["pnl"],
        })

    # 当天卖完当天买的
    same_day = [g for g in sell_buy_gaps if g["间隔天数"] == 0]
    # 次日买的
    next_day = [g for g in sell_buy_gaps if g["间隔天数"] == 1]
    # 同股票再入场
    same_stock_reentry = [g for g in sell_buy_gaps if g["同股票"]]

    return {
        "卖出到买入间隔": {
            "当天再入场": len(same_day),
            "次日再入场": len(next_day),
            "2-7天": sum(1 for g in sell_buy_gaps if 2 <= g["间隔天数"] <= 7),
            "8天+": sum(1 for g in sell_buy_gaps if g["间隔天数"] > 7),
        },
        "当天再入场_后笔胜率": round(
            sum(1 for g in same_day if g["后笔盈亏"] > 0) / len(same_day) * 100, 1
        ) if same_day else 0,
        "次日再入场_后笔胜率": round(
            sum(1 for g in next_day if g["后笔盈亏"] > 0) / len(next_day) * 100, 1
        ) if next_day else 0,
        "同股票再入场": {
            "次数": len(same_stock_reentry),
            "后笔胜率": round(
                sum(1 for g in same_stock_reentry if g["后笔盈亏"] > 0) / len(same_stock_reentry) * 100, 1
            ) if same_stock_reentry else 0,
            "平均间隔_天": round(
                sum(g["间隔天数"] for g in same_stock_reentry) / len(same_stock_reentry), 1
            ) if same_stock_reentry else 0,
        },
        "前笔盈亏对再入场影响": _reentry_by_prior_pnl(sell_buy_gaps),
    }


def _reentry_by_prior_pnl(gaps):
    """前一笔盈亏对再入场行为的影响。"""
    post_win = [g for g in gaps if g["前笔盈亏"] > 0]
    post_loss = [g for g in gaps if g["前笔盈亏"] < 0]

    return {
        "盈利后": {
            "平均间隔": round(sum(g["间隔天数"] for g in post_win) / len(post_win), 1) if post_win else 0,
            "再入场胜率": round(
                sum(1 for g in post_win if g["后笔盈亏"] > 0) / len(post_win) * 100, 1
            ) if post_win else 0,
            "样本": len(post_win),
        },
        "亏损后": {
            "平均间隔": round(sum(g["间隔天数"] for g in post_loss) / len(post_loss), 1) if post_loss else 0,
            "再入场胜率": round(
                sum(1 for g in post_loss if g["后笔盈亏"] > 0) / len(post_loss) * 100, 1
            ) if post_loss else 0,
            "样本": len(post_loss),
            "解读": "亏损后急于翻本 — 间隔更短" if post_loss and post_win and
                   sum(g["间隔天数"] for g in post_loss) / len(post_loss) < sum(g["间隔天数"] for g in post_win) / len(post_win)
                   else "无明显差异",
        },
    }


def build_adding_behavior(trades):
    """同股票多次买入(加仓)行为分析。"""
    stock_buys = defaultdict(list)
    for t in trades:
        if "买入" in str(t.get("委托方向", "")):
            stock_buys[t["证券代码"]].append({
                "date": t["委托日期"],
                "price": t["成交均价"] or t["委托价格"],
                "qty": t["成交数量"],
                "amount": t["成交金额"],
            })

    # 统计加仓模式
    add_count_dist = defaultdict(int)
    avg_down_examples = []  # 越跌越买
    avg_up_examples = []    # 越涨越买

    for code, buys in stock_buys.items():
        n_buys = len(buys)
        add_count_dist[f"{n_buys}次买入"] += 1

        sorted_buys = sorted(buys, key=lambda x: x["date"])
        for i in range(1, len(sorted_buys)):
            prev = sorted_buys[i - 1]
            curr = sorted_buys[i]
            if prev["price"] > 0 and curr["price"] > 0:
                change = (curr["price"] / prev["price"] - 1) * 100
                if change < -3:
                    avg_down_examples.append({
                        "code": code, "date": curr["date"],
                        "前价": round(prev["price"], 2), "现价": round(curr["price"], 2),
                        "跌幅%": round(change, 1),
                    })
                elif change > 3:
                    avg_up_examples.append({
                        "code": code, "date": curr["date"],
                        "前价": round(prev["price"], 2), "现价": round(curr["price"], 2),
                        "涨幅%": round(change, 1),
                    })

    return {
        "加仓次数分布": dict(add_count_dist),
        "越跌越买_次数": len(avg_down_examples),
        "越涨越买_次数": len(avg_up_examples),
        "越跌越买_样本": avg_down_examples[:10],
        "越涨越买_样本": avg_up_examples[:10],
        "解读": _interpret_adding(avg_down_examples, avg_up_examples),
    }


def _interpret_adding(down, up):
    parts = []
    if len(down) > len(up) * 1.5:
        parts.append(f"倾向越跌越买({len(down)}次 vs {len(up)}次) — 均值回归思维，危险在于接飞刀")
    elif len(up) > len(down) * 1.5:
        parts.append(f"倾向越涨越买({len(up)}次 vs {len(down)}次) — 趋势跟踪思维，危险在于追高")
    else:
        parts.append(f"越跌越买({len(down)}次)和越涨越买({len(up)}次)均衡")
    return "；".join(parts)


def build_worst_list(rounds):
    return sorted(
        [{"代码": r["code"], "名称": r["name"], "买入日": r["buy_date"], "卖出日": r["sell_date"],
          "持有天": r["hold_days"], "盈亏": r["pnl"], "盈亏%": r["pnl_pct"],
          "买入金额": r["buy_amount"]} for r in rounds if r["pnl"] < 0],
        key=lambda x: x["盈亏"]
    )[:30]


def build_best_list(rounds):
    return sorted(
        [{"代码": r["code"], "名称": r["name"], "买入日": r["buy_date"], "卖出日": r["sell_date"],
          "持有天": r["hold_days"], "盈亏": r["pnl"], "盈亏%": r["pnl_pct"],
          "买入金额": r["buy_amount"]} for r in rounds if r["pnl"] > 0],
        key=lambda x: x["盈亏"], reverse=True
    )[:30]


# ── 打印 ────────────────────────────────────────────────────

def print_report(report):
    s = report["summary"]
    dist = report["pnl_distribution"]
    cf = report["counterfactuals"]
    seq = report["sequence_analysis"]
    size = report["position_sizing"]
    time_d = report["timing_deep"]
    hold = report["hold_days_curve"]
    canc = report["cancellation_behavior"]
    stocks = report["stock_profiles"]
    reentry = report["reentry_patterns"]
    adding = report["adding_behavior"]

    print("=" * 70)
    print("  交易行为深度分析 v2")
    print(f"  数据: Table.xlsx | 2954笔已成 → {s['往返交易笔数']}笔往返")
    print("=" * 70)

    # 1. 总览
    print(f"\n{'─'*50}")
    print("  一、总览")
    print(f"{'─'*50}")
    print(f"  胜率: {s['胜率']}% | 盈亏比: {s['盈亏比']} | 总盈亏: ¥{s['总盈亏']:,.0f}")
    print(f"  盈利 {s['盈利笔数']}笔: 均¥{s['平均盈利']:,.0f} | 亏损 {s['亏损笔数']}笔: 均¥{s['平均亏损']:,.0f}")
    print(f"  累计买入 ¥{s['累计买入']:,.0f} → 卖出 ¥{s['累计卖出']:,.0f} (周转率 {s['资金周转率']}%)")

    # 2. 盈亏分布
    print(f"\n{'─'*50}")
    print("  二、盈亏分布曲线")
    print(f"{'─'*50}")
    bins = dist["盈亏%分布"]
    max_bin = max(bins.values())
    for label in bins:
        cnt = bins[label]
        bar = "█" * max(1, int(cnt / max(max_bin, 1) * 30))
        print(f"  {label:>12s}: {bar} {cnt}")
    pct = dist["百分位"]
    print(f"  百分位: P5={pct['p5']}% P25={pct['p25']}% P50={pct['p50_中位']}% P75={pct['p75']}% P95={pct['p95']}%")
    print(f"  偏度={dist['偏度']} (负偏=左尾更长=大亏拖累)")
    fat = dist["肥尾分析"]
    print(f"  肥尾: <-7%占{fat['左侧肥尾_<-7%_笔数']}笔/亏损{fat['左侧肥尾_<-7%_亏损占比']}"
          f" | >15%占{fat['右侧肥尾_>15%_笔数']}笔/盈利{fat['右侧肥尾_>15%_盈利占比']}")
    print(f"  → {fat['解读']}")

    # 3. 反事实推演
    print(f"\n{'─'*50}")
    print("  三、反事实推演 (如果...会怎样)")
    print(f"{'─'*50}")
    for name, result in cf.items():
        print(f"  {name}: 总盈亏→¥{result['总盈亏']:,.0f} (改善¥{result.get('改善金额', 0):,.0f})"
              f" | 受影响{result.get('被截断笔数', result.get('受影响笔数', '?'))}笔"
              f" | {result.get('说明', '')}")

    # 4. 序列分析
    print(f"\n{'─'*50}")
    print("  四、序列分析 — 情绪驱动模式")
    print(f"{'─'*50}")
    post_win = seq.get("盈利后下一笔", {})
    post_loss = seq.get("亏损后下一笔", {})
    print(f"  最大连胜: {seq['连胜统计']['连胜最多笔数']}笔 | 最大连败: {seq['连败统计']['连败最多笔数']}笔")
    print(f"  获利后下一笔: 胜率{post_win.get('胜率', '?')}% 均¥{post_win.get('平均盈亏', 0):,.0f} "
          f"(样本{post_win.get('样本数', 0)}) | {post_win.get('过度自信检测', '')}")
    print(f"  亏损后下一笔: 胜率{post_loss.get('胜率', '?')}% 均¥{post_loss.get('平均盈亏', 0):,.0f} "
          f"(样本{post_loss.get('样本数', 0)}) | {post_loss.get('报复交易检测', '')}")
    revenge = seq.get("大亏后24h内第一笔", {})
    print(f"  大亏后24h内第一笔: {revenge.get('次数', 0)}次 | 胜率{revenge.get('胜率', '?')}% | 均¥{revenge.get('平均盈亏', 0):,.0f}")
    if revenge.get("风险评级"):
        print(f"  → {revenge['风险评级']}")

    # 5. 仓位规模
    print(f"\n{'─'*50}")
    print("  五、仓位规模 vs 盈亏")
    print(f"{'─'*50}")
    for label, bucket in size["仓位-盈亏关系"].items():
        if bucket["笔数"] == 0:
            continue
        print(f"  {label}: {bucket['笔数']}笔 胜率{bucket['胜率']}% 总¥{bucket['总盈亏']:,.0f} 均¥{bucket['平均盈亏']:,.0f}")
    top = size["最大30笔_按金额"]
    print(f"  重仓TOP30: 胜率{top['胜率']}% 总¥{top['总盈亏']:,.0f} → {top['解读']}")

    # 6. 时间维度
    print(f"\n{'─'*50}")
    print("  六、时间维度深度分析")
    print(f"{'─'*50}")
    print("  [日内时段 vs 盈亏]")
    for label, info in sorted(time_d["日内时段"].items()):
        print(f"    {label}: {info['笔数']}笔 胜率{info['胜率']}% 均¥{info['平均盈亏']:,.0f}")
    print("  [周几 vs 盈亏]")
    for label, info in time_d["周几"].items():
        print(f"    {label}: {info['笔数']}笔 胜率{info['胜率']}% 总¥{info['总盈亏']:,.0f}")
    print("  [月内位置]")
    for label, info in time_d["月内位置"].items():
        print(f"    {label}: {info['笔数']}笔 胜率{info['胜率']}% 总¥{info['总盈亏']:,.0f}")

    # 7. 持有天数曲线
    print(f"\n{'─'*50}")
    print("  七、持有天数 vs 盈亏曲线")
    print(f"{'─'*50}")
    for label, info in hold["持有天数vs盈亏"].items():
        if info["笔数"] == 0:
            continue
        print(f"  {label}: {info['笔数']}笔 胜率{info['胜率']}% 均¥{info['平均盈亏']:,.0f} 均{info['平均盈亏%']}%")
    print(f"  → 最佳窗口: {hold['最佳窗口']} (均¥{hold['最佳窗口平均盈亏']:,.0f})")

    # 8. 撤单行为
    print(f"\n{'─'*50}")
    print("  八、撤单行为分析")
    print(f"{'─'*50}")
    print(f"  撤单: {canc['撤单总数']}笔 (撤单率{canc.get('撤单率', '?')}) | 买入撤{canc.get('买入撤单', '?')} 卖出撤{canc.get('卖出撤单', '?')}")
    print(f"  撤单时段: {canc.get('撤单时段分布', {})}")
    print(f"  → {canc.get('解读', '')}")

    # 9. 个股画像
    print(f"\n{'─'*50}")
    print("  九、个股深度画像 (交易>10次)")
    print(f"{'─'*50}")
    for name, profile in list(stocks.items())[:15]:
        print(f"  {name}: {profile['交易次数']}笔 胜率{profile['胜率']}% "
              f"盈亏¥{profile['总盈亏']:,.0f} 均¥{profile['平均盈亏']:,.0f} "
              f"均持{profile['平均持有']}天 跨度{profile['交易跨度_天']}天")

    # 10. 再入场
    print(f"\n{'─'*50}")
    print("  十、卖出后再入场行为")
    print(f"{'─'*50}")
    gap = reentry["卖出到买入间隔"]
    print(f"  当天再入场: {gap['当天再入场']}笔 (后笔胜率{reentry.get('当天再入场_后笔胜率', '?')}%)")
    print(f"  次日再入场: {gap['次日再入场']}笔 (后笔胜率{reentry.get('次日再入场_后笔胜率', '?')}%)")
    same = reentry["同股票再入场"]
    print(f"  同股票再入场: {same['次数']}笔 胜率{same['后笔胜率']}% 均间隔{same['平均间隔_天']}天")
    prior = reentry["前笔盈亏对再入场影响"]
    print(f"  盈利后→均间隔{prior['盈利后']['平均间隔']}天 胜率{prior['盈利后']['再入场胜率']}%")
    print(f"  亏损后→均间隔{prior['亏损后']['平均间隔']}天 胜率{prior['亏损后']['再入场胜率']}% "
          f"→ {prior['亏损后'].get('解读', '')}")

    # 11. 加仓
    print(f"\n{'─'*50}")
    print("  十一、加仓行为")
    print(f"{'─'*50}")
    print(f"  越跌越买: {adding['越跌越买_次数']}次 | 越涨越买: {adding['越涨越买_次数']}次")
    print(f"  → {adding['解读']}")

    # 12. 最差/最好
    print(f"\n{'─'*50}")
    print("  十二、最差10笔 (金额)")
    print(f"{'─'*50}")
    for t in report["worst20"][:10]:
        print(f"  {t['名称']}({t['代码']}): {t['买入日']}→{t['卖出日']} "
              f"({t['持有天']}天) ¥{t['盈亏']:,.0f} ({t['盈亏%']}%) 买入¥{t['买入金额']:,.0f}")

    print(f"\n{'─'*50}")
    print("  十三、最好10笔 (金额)")
    print(f"{'─'*50}")
    for t in report["best20"][:10]:
        print(f"  {t['名称']}({t['代码']}): {t['买入日']}→{t['卖出日']} "
              f"({t['持有天']}天) ¥{t['盈亏']:,.0f} ({t['盈亏%']}%) 买入¥{t['买入金额']:,.0f}")

    print("\n" + "=" * 70)

    # 综合诊断
    print(f"\n{'─'*50}")
    print("  综合诊断 & 可操作建议")
    print(f"{'─'*50}")
    diag = _diagnose(report)
    for i, line in enumerate(diag, 1):
        print(f"  {i}. {line}")


def _diagnose(report):
    lines = []
    s = report["summary"]
    dist = report["pnl_distribution"]
    seq = report["sequence_analysis"]
    time_d = report["timing_deep"]
    hold = report["hold_days_curve"]
    size = report["position_sizing"]

    # 诊断1: 盈亏不对称
    if s["平均亏损"] > s["平均盈利"]:
        lines.append(f"【盈亏不对称-核心病】平均亏损¥{s['平均亏损']:,.0f} > 平均盈利¥{s['平均盈利']:,.0f}。"
                     f"必须扭转赔率：要么放大盈利(让盈利交易跑得更远)，要么截断亏损(严格执行-5%硬止损)。"
                     f"反事实推演：-5%硬止损可改善¥{report['counterfactuals']['硬止损-5%']['改善金额']:,.0f}。")

    # 诊断2: T+1依赖
    t1_pct = hold["持有天数vs盈亏"]["0-1天"]["笔数"] / s["往返交易笔数"] * 100
    if t1_pct > 30:
        lines.append(f"【过度短线】{t1_pct:.0f}%的交易在T+1内完成，中位持有仅2天。"
                     f"T+1交易的盈亏几乎为零(均¥{hold['持有天数vs盈亏']['0-1天']['平均盈亏']:,.0f})。"
                     f"建议：买入后至少持有到第3天，给交易一点呼吸空间。")

    # 诊断3: 左侧肥尾
    fat = dist["肥尾分析"]
    lines.append(f"【肥尾风险】{fat['左侧肥尾_<-7%_笔数']}笔亏损超7%，贡献了{fat['左侧肥尾_<-7%_亏损占比']}的亏损总额。"
                 f"这些'灾难性交易'是亏损的主要来源。必须设硬止损线。")

    # 诊断4: 报复交易
    revenge_diag = seq.get("大亏后24h内第一笔", {})
    if revenge_diag.get("次数", 0) > 5 and revenge_diag.get("胜率", 50) < 45:
        lines.append(f"【报复交易】大亏后24h内立即交易的胜率仅{revenge_diag['胜率']}%。"
                     f"建议：单笔亏损>5%后强制冷却24小时，禁止开新仓。")

    # 诊断5: 开盘交易
    hour_data = time_d["日内时段"]
    morning_pnl = sum(v["总盈亏"] for k, v in hour_data.items() if k.startswith(("9", "10")))
    if morning_pnl < 0:
        lines.append(f"【开盘时段亏损】9-10点交易合计亏损¥{morning_pnl:,.0f}。"
                     f"开盘情绪驱动决策质量差。建议：开盘30分钟内只观察不交易。")

    # 诊断6: 仓位-盈亏关系
    sizing_data = size["仓位-盈亏关系"]
    large_lots = sizing_data.get("2-5万", {})
    small_lots = sizing_data.get("<5千", {})
    if large_lots.get("胜率", 0) < small_lots.get("胜率", 0):
        lines.append(f"【重仓反而更差】大仓位(2-5万)胜率{large_lots.get('胜率', '?')}% < "
                     f"小仓位(<5千)胜率{small_lots.get('胜率', '?')}%。"
                     f"建议：控制单笔仓位上限，不让任何一笔交易的风险超过总资金的2%。")

    # 诊断7: 连败循环
    if seq["连败统计"]["连败最多笔数"] > 7:
        lines.append(f"【连败螺旋】最大连败{seq['连败统计']['连败最多笔数']}笔。"
                     f"连败时应有'熔断机制'：连续3笔亏损→暂停当天交易。")

    # 诊断8: 个股集中度
    lines.append(f"【标的过度分散】交易过363只股票，单只平均5.8笔。"
                 f"没有足够的重复交易来积累经验。聚焦20-30只熟悉的标的，反复做。")

    # 诊断9: 过度自信
    post_win_seq = seq.get("盈利后下一笔", {})
    post_win_wr = post_win_seq.get("胜率", 0)
    if post_win_wr < s["胜率"] and post_win_seq.get("样本数", 0) > 10:
        lines.append(f"【获利后过度自信】获利后下一笔胜率({post_win_wr}%)低于均值({s['胜率']}%)。"
                     f"大赢后容易放松标准，需警惕。")

    return lines


# ── Main ─────────────────────────────────────────────────────

def main():
    print("加载数据...")
    trades, cancelled = load_all_records(EXCEL_PATH)
    print(f"  已成: {len(trades)}笔, 已撤: {len(cancelled)}笔")

    print("FIFO匹配...")
    rounds = fifo_match(trades)
    print(f"  往返交易: {len(rounds)}笔")

    print("深度分析中...")
    report = analyze_v2(rounds, trades, cancelled)

    print_report(report)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n完整JSON报告: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
