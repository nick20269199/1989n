"""
每日开仓前检查清单 + 盘中持仓管理
用法:
  python daily_checklist.py status          # 今日市场状态
  python daily_checklist.py check 002156     # 检查某只股票能否开仓
  python daily_checklist.py plan 002156 通富微电 50.00  # 生成交易计划
  python daily_checklist.py hold 002156 50.00 51.20 3   # 持仓第3天检查
"""
import sys
import os
import json
from datetime import datetime

DATA_DIR = "D:/1989n/stock_data"

# 精简版参数 — 和trade_engine一致
RULES = {
    "hard_stop": -7.0,
    "soft_stop": -3.0,
    "take_profit_half": 8.0,
    "take_profit_all": 15.0,
    "trail_activate": 5.0,
    "trail_distance": 3.0,
    "danger_zone": (3, 5),
    "max_hold": 10,
    "volume_blacklist": ["缩量"],
    "trend_blacklist": ["空头排列"],
    "sentiment_blacklist": ["恐慌"],
}


def load_calendar():
    cal_path = os.path.join(DATA_DIR, "market_calendar_full.json")
    if os.path.exists(cal_path):
        with open(cal_path, "r") as f:
            return json.load(f)
    return {}


def cmd_status():
    """今日市场状态"""
    cal = load_calendar()
    today = datetime.now().strftime("%Y-%m-%d")
    mkt = cal.get(today, {})

    print(f"\n{'='*50}")
    print(f"  今日市场 — {today}")
    print(f"{'='*50}")

    if not mkt:
        # 找最近交易日
        for d in sorted(cal.keys(), reverse=True):
            if d <= today:
                mkt = cal[d]
                print(f"  (使用最近交易日: {d})")
                break

    trend = mkt.get("trend", "?")
    vol = mkt.get("volume_state", "?")
    sent = mkt.get("sentiment", "?")
    pct = mkt.get("pct_chg", 0)

    print(f"  上证收盘: {mkt.get('close', '?')} ({pct:+.2f}%)")
    print(f"  趋势: {trend}")
    print(f"  量能: {vol}")
    print(f"  情绪: {sent}")
    print(f"  波动率: {mkt.get('volatility', '?')}")

    # 判断
    print(f"\n  ── 今日交易规则 ──")
    issues = []
    if vol in RULES["volume_blacklist"]:
        issues.append("⛔ 缩量日 — 不主动开新仓")
    else:
        print(f"  ✅ 量能允许开仓")

    if trend in RULES["trend_blacklist"]:
        issues.append("⛔ 空头排列 — 只做超短(0-2天)")
    else:
        print(f"  ✅ 趋势允许开仓")

    if sent in RULES["sentiment_blacklist"]:
        issues.append("⛔ 恐慌日 — 只卖不买")
    else:
        print(f"  ✅ 情绪允许开仓")

    if sent == "弱势":
        issues.append("⚠ 弱势 — 仓位减半, 止损收紧至-5%")

    if vol == "放量":
        print(f"  💡 放量日 — 最佳开仓时机(5年均+1.35%)")

    for i in issues:
        print(f"  {i}")

    if not issues:
        print(f"\n  >>> 今日可以正常交易，严格执行三层机制 <<<")

    print()


def cmd_check(code):
    """检查单只股票"""
    cal = load_calendar()
    today = datetime.now().strftime("%Y-%m-%d")
    mkt = cal.get(today, {})
    if not mkt:
        for d in sorted(cal.keys(), reverse=True):
            if d <= today:
                mkt = cal[d]
                break

    print(f"\n  标的 {code} 开仓前检查:")
    print(f"  {'─'*40}")

    checks = []
    vol = mkt.get("volume_state", "")
    trend = mkt.get("trend", "")
    sent = mkt.get("sentiment", "")

    if vol in RULES["volume_blacklist"]:
        checks.append(("NOGO", f"缩量环境"))
    else:
        checks.append(("OK", f"量能: {vol}"))

    if trend in RULES["trend_blacklist"]:
        checks.append(("NOGO", f"空头排列"))
    else:
        checks.append(("OK", f"趋势: {trend}"))

    if sent in RULES["sentiment_blacklist"]:
        checks.append(("NOGO", f"恐慌情绪"))
    else:
        checks.append(("OK", f"情绪: {sent}"))

    for status, msg in checks:
        icon = "✅" if status == "OK" else "⛔"
        print(f"  {icon} {msg}")

    nogo = any(s == "NOGO" for s, _ in checks)
    if nogo:
        print(f"\n  >>> 不开仓 <<<")
    else:
        print(f"\n  >>> 环境通过，可以开仓 <<<")
    print()


def cmd_plan(code, name, price_str):
    """生成交易计划，保存到 trade_plans/，标记需对抗审查"""
    price = float(price_str)
    today = datetime.now().strftime("%Y-%m-%d")
    timestamp_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 计算风控价位
    hard_stop = round(price * 0.93, 2)
    soft_stop = round(price * 0.97, 2)
    target_half = round(price * 1.08, 2)
    target_all = round(price * 1.15, 2)
    trail_start = round(price * 1.05, 2)

    print(f"\n{'='*55}")
    print(f"  {name}({code}) @ {price:.2f}  — 交易计划")
    print(f"{'='*55}")
    print(f"  ┌─────────────────────────────────┐")
    print(f"  │ 硬止损 (-7%)        {hard_stop:>8.2f}  │")
    print(f"  │ 软止损 (-3%)        {soft_stop:>8.2f}  │")
    print(f"  │ 止盈 50% (+8%)      {target_half:>8.2f}  │")
    print(f"  │ 止盈 全部 (+15%)    {target_all:>8.2f}  │")
    print(f"  │ 移动止损启动 (+5%)  {trail_start:>8.2f}  │")
    print(f"  └─────────────────────────────────┘")
    print(f"  ⚠ 最大持仓: 10天 | 危险区: 第3-5天")
    print(f"  ⚠ 移动止损: 浮盈>5%后回撤3%即止盈")

    print(f"\n  ── 持仓时间线 ──")
    print(f"  第0天(今日): 开仓 @{price:.2f}")
    print(f"  每天: 检查是否触发止损/止盈")
    print(f"  第2天: 若微利(<2%)→考虑止盈")
    print(f"  第3-5天: ⚠危险区 浮亏即砍, 微利也清")
    print(f"  第10天: 强制清仓")

    # 保存交易计划到 trade_plans/
    plan_dir = os.path.join(DATA_DIR, "trade_plans")
    os.makedirs(plan_dir, exist_ok=True)

    import json as _json
    plan = {
        "code": code,
        "name": name,
        "entry_price": price,
        "hard_stop": hard_stop,
        "soft_stop": soft_stop,
        "target_half": target_half,
        "target_all": target_all,
        "trail_activate": trail_start,
        "max_hold_days": RULES["max_hold"],
        "danger_zone": list(RULES["danger_zone"]),
        "created_at": timestamp_now,
        "for_date": today,
        "status": "pending_review",
        "adversarial_review": {
            "required": True,
            "completed": False,
            "passed": False,
            "reviewed_at": None,
            "findings": [],
        },
    }
    plan_path = os.path.join(plan_dir, f"plan_{code}_{today}.json")
    with open(plan_path, "w", encoding="utf-8") as f:
        _json.dump(plan, f, ensure_ascii=False, indent=2)

    print(f"\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  ⛔ 此计划需通过 adversarial-review 后才能执行")
    print(f"  ⛔ 审查不通过 = 不执行，无例外")
    print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"  计划已保存: {plan_path}")
    print(f"  审查方式: 在 Claude Code 中运行")
    print(f"    /adversarial-review {plan_path}")
    print()


def cmd_review_check(code=None):
    """检查交易计划的审查状态"""
    import json as _json

    plan_dir = os.path.join(DATA_DIR, "trade_plans")
    if not os.path.exists(plan_dir):
        print("暂无交易计划")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    pattern = f"plan_{code}_{today}.json" if code else f"plan_*_{today}.json"
    files = sorted(
        [f for f in os.listdir(plan_dir) if f.startswith("plan_") and f.endswith(".json")],
        reverse=True,
    )

    if not files:
        print("今日暂无交易计划")
        return

    print(f"\n  {'='*55}")
    print(f"  交易计划审查状态 — {today}")
    print(f"  {'='*55}")

    for fname in files:
        if code and not fname.startswith(f"plan_{code}_"):
            continue
        filepath = os.path.join(plan_dir, fname)
        with open(filepath, "r", encoding="utf-8") as f:
            plan = _json.load(f)

        # 跳过不符合新格式的旧文件
        if "entry_price" not in plan and "name" not in plan:
            continue

        review = plan.get("adversarial_review", {})
        status = plan.get("status", "unknown")
        status_icon = {
            "pending_review": "⏳",
            "review_passed": "✅",
            "review_failed": "⛔",
        }.get(status, "❓")

        print(f"\n  {status_icon} {plan.get('name', '?')}({plan.get('code', '?')}) @ {plan.get('entry_price', '?')}")
        print(f"     状态: {status}")
        print(f"     创建: {plan.get('created_at', '?')}")

        if review.get("completed"):
            print(f"     审查时间: {review.get('reviewed_at', '?')}")
            print(f"     审查通过: {'是' if review.get('passed') else '否'}")
            if review.get("findings"):
                for finding in review["findings"]:
                    print(f"       - {finding}")
        else:
            print(f"     ⚠ 尚未完成对抗审查")

    print()


def cmd_plan_mark_reviewed(code, passed, *findings):
    """标记交易计划已审查: python daily_checklist.py reviewed <code> <yes/no> [findings...]"""
    import json as _json

    today = datetime.now().strftime("%Y-%m-%d")
    plan_path = os.path.join(DATA_DIR, "trade_plans", f"plan_{code}_{today}.json")

    if not os.path.exists(plan_path):
        print(f"未找到今日计划: plan_{code}_{today}.json")
        return

    with open(plan_path, "r", encoding="utf-8") as f:
        plan = _json.load(f)

    plan["adversarial_review"] = {
        "required": True,
        "completed": True,
        "passed": passed.lower() in ("yes", "true", "pass"),
        "reviewed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "findings": list(findings),
    }
    plan["status"] = "review_passed" if plan["adversarial_review"]["passed"] else "review_failed"

    with open(plan_path, "w", encoding="utf-8") as f:
        _json.dump(plan, f, ensure_ascii=False, indent=2)

    status_icon = "✅" if plan["adversarial_review"]["passed"] else "⛔"
    print(f"{status_icon} 审查结果已记录: {plan['name']}({code}) — {plan['status']}")
    if not plan["adversarial_review"]["passed"]:
        print("⚠ 审查未通过 — 此计划不得执行")


def cmd_hold(code, entry_str, current_str, days_str):
    """持仓中检查"""
    entry = float(entry_str)
    current = float(current_str)
    days = int(days_str)
    pnl_pct = (current - entry) / entry * 100

    print(f"\n  {code} 持仓检查 — 第{days}天")
    print(f"  入场: {entry:.2f}  现价: {current:.2f}  {pnl_pct:+.2f}%")
    print(f"  {'─'*40}")

    # 硬止损
    if pnl_pct <= RULES["hard_stop"]:
        print(f"  ⛔ 硬止损触发! {pnl_pct:.1f}% ≤ -7%")
        print(f"  >>> 立刻清仓, 不要等 <<<")
        return

    # 软止损
    if pnl_pct <= RULES["soft_stop"]:
        print(f"  ⚠ 软止损: {pnl_pct:.1f}% ≤ -3%")
        print(f"  >>> 减半仓 或 清仓 <<<")
        return

    # 危险区
    if RULES["danger_zone"][0] <= days <= RULES["danger_zone"][1]:
        if pnl_pct < 0:
            print(f"  ⛔ 危险区+浮亏: 第{days}天 {pnl_pct:.1f}%")
            print(f"  >>> 清仓！危险区浮亏是最大亏损源 <<<")
            return
        elif pnl_pct <= 2:
            print(f"  ⚠ 危险区+微利: 第{days}天 {pnl_pct:+.1f}%")
            print(f"  >>> 建议止盈, 不贪 <<<")
            return
        else:
            print(f"  ✅ 危险区但浮盈可观: {pnl_pct:+.1f}%")
            print(f"  >>> 收紧止损到成本价 <<<")
            return

    # 止盈
    if pnl_pct >= RULES["take_profit_all"]:
        print(f"  💰 +15%触发: {pnl_pct:.1f}%")
        print(f"  >>> 全部止盈 <<<")
        return
    if pnl_pct >= RULES["take_profit_half"]:
        print(f"  💰 +8%触发: {pnl_pct:.1f}%")
        print(f"  >>> 止盈一半, 剩余设移动止损 <<<")
        return

    # 移动止损
    if pnl_pct >= RULES["trail_activate"]:
        trail = pnl_pct - RULES["trail_distance"]
        print(f"  📈 移动止损激活: 浮盈{pnl_pct:.1f}%, 止损线设在+{trail:.1f}%")
        print(f"  >>> 若回撤至+{trail:.1f}%即清仓 <<<")
        return

    # 超时
    if days > RULES["max_hold"]:
        print(f"  ⏰ 超时{days}天 > {RULES['max_hold']}天")
        print(f"  >>> 强制清仓 <<<")
        return

    print(f"  ✅ 持仓正常, 继续观察")
    print(f"     下一检查点: 第{days+1}天 或 价格触及以下任一价位:")
    print(f"     -{RULES['abs(hard_stop)']:.0f}%: {entry*(1+RULES['hard_stop']/100):.2f}")
    print(f"     +{RULES['take_profit_half']:.0f}%: {entry*(1+RULES['take_profit_half']/100):.2f}")


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python daily_checklist.py status")
        print("  python daily_checklist.py check <code>")
        print("  python daily_checklist.py plan <code> <name> <price>")
        print("  python daily_checklist.py hold <code> <entry> <current> <days>")
        print("  python daily_checklist.py review [code]")
        print("  python daily_checklist.py reviewed <code> <yes/no> [findings...]")
        return

    cmd = sys.argv[1]
    if cmd == "status":
        cmd_status()
    elif cmd == "check" and len(sys.argv) >= 3:
        cmd_check(sys.argv[2])
    elif cmd == "plan" and len(sys.argv) >= 5:
        cmd_plan(sys.argv[2], sys.argv[3], sys.argv[4])
    elif cmd == "hold" and len(sys.argv) >= 6:
        cmd_hold(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
    elif cmd == "review":
        code = sys.argv[2] if len(sys.argv) >= 3 else None
        cmd_review_check(code)
    elif cmd == "reviewed" and len(sys.argv) >= 4:
        code = sys.argv[2]
        passed = sys.argv[3]
        findings = sys.argv[4:] if len(sys.argv) > 4 else []
        cmd_plan_mark_reviewed(code, passed, *findings)
    else:
        print("参数不足")


if __name__ == "__main__":
    main()
