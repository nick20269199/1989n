"""
隔夜交易计划生成器 — 收盘后跑，输出明天的操作剧本
原则: 盘中不思考，只执行前一天写好的剧本
运行时间: 每天15:40 (在closing_review + daily-compress之后)
"""
import json
import os
import sys
import glob
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

DATA_DIR = "D:/1989n/stock_data"
PLAN_DIR = os.path.join(DATA_DIR, "trade_plans")
os.makedirs(PLAN_DIR, exist_ok=True)

# ============================================================
# 持仓 (与 CLAUDE.md + position_manager.py 同步)
# ============================================================
HOLDINGS = [
    {"code": "002156", "name": "通富微电", "qty": 400, "cost": -1.032, "sector": "半导体封测",
     "buy_date": "2026-04-27", "first_buy": "2026-04-27", "latest_buy": "2026-05-15"},
    {"code": "300136", "name": "信维通信", "qty": 500, "cost": 108.006, "sector": "消费电子/射频",
     "buy_date": "2026-05-18", "first_buy": "2026-05-18", "latest_buy": "2026-05-22"},
    {"code": "600498", "name": "烽火通信", "qty": 800, "cost": 57.132, "sector": "通信设备",
     "buy_date": "2026-05-20", "first_buy": "2026-05-20", "latest_buy": "2026-05-22"},
    {"code": "002077", "name": "大港股份", "qty": 2500, "cost": 18.684, "sector": "半导体/EDA",
     "buy_date": "2026-05-21", "first_buy": "2026-05-21", "latest_buy": "2026-05-21"},
    {"code": "300058", "name": "蓝色光标", "qty": 800, "cost": 18.24, "sector": "AI营销/出海",
     "buy_date": "2026-05-21", "first_buy": "2026-05-21", "latest_buy": "2026-05-21"},
]
PORTFOLIO_JSON = os.path.join(os.path.dirname(__file__), "data", "portfolio.json")


def load_portfolio_holdings() -> list[dict]:
    """从 portfolio.json 加载当前持仓，后备用模块级 HOLDINGS。"""
    try:
        if os.path.exists(PORTFOLIO_JSON):
            with open(PORTFOLIO_JSON, "r", encoding="utf-8") as f:
                data = json.load(f)
            raw = data.get("holdings", [])
            if raw:
                return [
                    {"code": h["code"], "name": h["name"], "qty": h["shares"],
                     "cost": h["cost"], "sector": h.get("sector", ""),
                     "buy_date": h.get("first_buy", ""), "first_buy": h.get("first_buy", ""),
                     "latest_buy": h.get("latest_buy", "")}
                    for h in raw if h.get("code")
                ]
    except Exception as e:
        print(f"  加载 portfolio.json 失败: {e}, 使用模块级后备")
    return HOLDINGS


# ============================================================
# 规则 (与 trade_engine 一致)
# ============================================================
STOP = {"hard": -7.0, "soft": -3.0}
PROFIT = {"half": 8.0, "full": 15.0}
TRAIL = {"activate": 5.0, "distance": 3.0}
DANGER = (3, 5)
MAX_HOLD = 10


def load_market_calendar():
    for fname in ["market_calendar_full.json", "market_calendar.json"]:
        path = os.path.join(DATA_DIR, fname)
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    return {}


def get_latest_closing_prices(holdings: list[dict] = None):
    """获取收盘价：优先用已验证的批量行情接口 → 30min文件回退"""
    if holdings is None:
        holdings = HOLDINGS
    prices = {}
    source = ""

    # 源1: 复用 daily_task 的稳定批量行情（Sina+Eastmoney多级回退）
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from daily_task import fetch_quotes_batch
        codes = [h["code"] for h in holdings]
        quotes = fetch_quotes_batch(codes)
        for code, q in quotes.items():
            if q.get("price", 0) > 0:
                prices[code] = q["price"]
        if prices:
            source = f"API(direct) {len(prices)}/{len(codes)}"
    except Exception as e:
        print(f"  ⚠ 批量行情获取失败: {e}")

    # 源2: 30min分析文件补充 (按修改时间取最新)
    pattern = os.path.join(DATA_DIR, "analysis_30min_*.json")
    all_files = sorted(glob.glob(pattern), key=lambda f: os.path.getmtime(f), reverse=True)
    today = datetime.now().strftime("%Y%m%d")
    today_files = [f for f in all_files if today in f]
    files_to_check = today_files if today_files else all_files[:1]

    for f in files_to_check:
        try:
            with open(f, "r") as fh:
                data = json.load(fh)
            for h in data.get("holdings", []):
                code = h["code"]
                if code not in prices:
                    prices[code] = float(h["price"])
            if source:
                source += f" + {os.path.basename(f)}"
            else:
                source = os.path.basename(f)
            break  # 只取最新一个文件
        except Exception:
            pass

    return prices, source


def get_recent_digest():
    """加载最近的市场摘要"""
    digest_dir = os.path.join(DATA_DIR, "learning")
    pattern = os.path.join(digest_dir, "daily_digest_*.json")
    files = sorted(glob.glob(pattern))
    if files:
        with open(files[-1], "r") as f:
            return json.load(f)
    return {}


def load_intel_signals() -> dict:
    """加载情报部收盘推演信号 (intel_deduce)。"""
    intel_file = os.path.join(DATA_DIR, "intel", "intel_latest.json")
    if not os.path.exists(intel_file):
        return {}
    try:
        with open(intel_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("kind") not in ("deduce", "recon"):
            return {}
        return data
    except (json.JSONDecodeError, IOError):
        return {}


def build_position_plan(holding: dict, close_price: float, market: dict,
                        hold_days: int) -> dict:
    """为单个持仓生成明天的完整行动计划"""
    code = holding["code"]
    name = holding["name"]
    cost = holding["cost"]
    qty = holding["qty"]
    market_value = qty * close_price
    pnl_pct = (close_price - cost) / cost * 100
    pnl_amount = (close_price - cost) * qty

    plan = {
        "code": code,
        "name": name,
        "qty": qty,
        "cost": cost,
        "close": close_price,
        "market_value": round(market_value, 0),
        "pnl_pct": round(pnl_pct, 2),
        "pnl_amount": round(pnl_amount, 0),
        "hold_days": hold_days,
        "sector": holding["sector"],
        "scenarios": [],
        "levels": {},
        "priority": "正常",  # 紧急 / 关注 / 正常
    }

    # === 关键价位 ===
    plan["levels"]["hard_stop"] = round(cost * (1 + STOP["hard"] / 100), 2)
    plan["levels"]["soft_stop"] = round(cost * (1 + STOP["soft"] / 100), 2)
    plan["levels"]["take_profit_half"] = round(cost * (1 + PROFIT["half"] / 100), 2)
    plan["levels"]["take_profit_all"] = round(cost * (1 + PROFIT["full"] / 100), 2)
    plan["levels"]["trail_activate"] = round(cost * (1 + TRAIL["activate"] / 100), 2)

    # 如果浮盈已超过5%，计算移动止损线
    if pnl_pct >= TRAIL["activate"]:
        trail_stop_pct = pnl_pct - TRAIL["distance"]
        trail_stop_price = close_price * (1 - TRAIL["distance"] / 100)
        plan["levels"]["trail_stop"] = round(trail_stop_price, 2)
        plan["trail_active"] = True
    else:
        plan["trail_active"] = False

    # === 明日情景 ===

    # 情景1: 高开 >3%
    gap_up_big = close_price * 1.03
    action_up_big = _determine_gap_action(pnl_pct, hold_days, "gap_up_big")
    plan["scenarios"].append({
        "name": "高开>3%",
        "trigger": f"开盘价 ≥ {gap_up_big:.2f}",
        "action": action_up_big,
    })

    # 情景2: 高开 1-3%
    action_up = _determine_gap_action(pnl_pct, hold_days, "gap_up")
    plan["scenarios"].append({
        "name": "高开1-3%",
        "trigger": f"开盘价在 {close_price*1.01:.2f} ~ {close_price*1.03:.2f}",
        "action": action_up,
    })

    # 情景3: 平开 (±1%)
    plan["scenarios"].append({
        "name": "平开±1%",
        "trigger": f"开盘价在 {close_price*0.99:.2f} ~ {close_price*1.01:.2f}",
        "action": _determine_normal_action(pnl_pct, hold_days, cost),
    })

    # 情景4: 低开 1-3%
    action_down = _determine_gap_action(pnl_pct, hold_days, "gap_down")
    plan["scenarios"].append({
        "name": "低开1-3%",
        "trigger": f"开盘价在 {close_price*0.97:.2f} ~ {close_price*0.99:.2f}",
        "action": action_down,
    })

    # 情景5: 低开 >3% 或触及止损
    gap_down_big = close_price * 0.97
    action_down_big = _determine_gap_action(pnl_pct, hold_days, "gap_down_big")
    plan["scenarios"].append({
        "name": "低开>3%",
        "trigger": f"开盘价 ≤ {gap_down_big:.2f} 或触及硬止损{plan['levels']['hard_stop']:.2f}",
        "action": action_down_big,
    })

    # 危险区状态
    if DANGER[0] <= hold_days <= DANGER[1]:
        plan["danger_zone"] = True
        plan["danger_day"] = hold_days
        plan["danger_rule"] = "浮亏即清仓, 微利(<2%)也减半"
        plan["priority"] = "关注"
    else:
        plan["danger_zone"] = False

    # 明天是危险区第一天?
    if hold_days + 1 == DANGER[0]:
        plan["enter_danger_tomorrow"] = True
        plan["scenarios"].insert(0, {
            "name": "⚠ 明天进入危险区(第3天)",
            "trigger": "开盘即进入",
            "action": "任何情况下, 收盘前必须盈利>2%, 否则减仓或清仓",
        })

    # 止损接近警告
    if pnl_pct <= -4 and pnl_pct > STOP["hard"]:
        plan["priority"] = "紧急"
    if close_price <= plan["levels"]["hard_stop"] * 1.02:
        plan["priority"] = "紧急"

    return plan


def _determine_gap_action(pnl_pct: float, hold_days: int, gap_type: str) -> str:
    """根据当前盈亏和持仓天数，决定开盘后的动作"""
    in_danger = DANGER[0] <= hold_days <= DANGER[1]
    overtime = hold_days > MAX_HOLD

    if overtime:
        if gap_type in ("gap_up_big", "gap_up"):
            return f"超时{hold_days}天 → 趁高开立即清仓，不犹豫"
        if gap_type in ("gap_down_big", "gap_down"):
            return f"超时{hold_days}天 → 集合竞价清仓，不再拖延"
        return f"超时{hold_days}天 → 强制清仓"

    if gap_type in ("gap_down_big",):
        if pnl_pct <= STOP["hard"]:
            return "集合竞价挂跌停价清仓，不犹豫"
        if pnl_pct <= STOP["soft"]:
            return "开盘观察5分钟，不反弹则清仓"
        if in_danger:
            return "开盘即砍半仓，剩余设-3%止损"
        return "开盘观察，若持续走弱10分钟内减半仓"

    if gap_type == "gap_down":
        if pnl_pct <= STOP["hard"]:
            return "立即清仓，不等反弹"
        if pnl_pct <= STOP["soft"]:
            return "减半仓，剩余设硬止损"
        if in_danger:
            return "开盘30分钟不翻红则清仓"
        return "观察，不急于操作但设好-3%止损单"

    if gap_type == "gap_up":
        if pnl_pct >= PROFIT["half"]:
            return "开盘先止盈一半，剩余移动止损到+3%"
        if pnl_pct >= TRAIL["activate"]:
            return "设置移动止损，回撤3%即清仓"
        return "持有，设好止损单即可"

    if gap_type == "gap_up_big":
        if pnl_pct >= PROFIT["full"]:
            return "集合竞价全部止盈，不贪"
        if pnl_pct >= PROFIT["half"]:
            return "开盘止盈一半，剩余设+5%移动止盈"
        return "大幅高开不追，已持有的话设好止损继续持有"

    return "按止损/止盈价位执行"


def _determine_normal_action(pnl_pct: float, hold_days: int, cost: float) -> str:
    """平开时的操作"""
    in_danger = DANGER[0] <= hold_days <= DANGER[1]

    if pnl_pct >= PROFIT["full"]:
        return "全部止盈，不犹豫"
    if pnl_pct >= PROFIT["half"]:
        return "止盈一半，剩余设移动止损"
    if pnl_pct >= TRAIL["activate"]:
        return "持有，移动止损线+2%，回撤即清"
    if pnl_pct <= STOP["hard"]:
        return "立即清仓"
    if pnl_pct <= STOP["soft"]:
        return "减半仓"
    if in_danger and pnl_pct < 0:
        return "危险区+浮亏 → 减半仓或清仓"
    if in_danger and pnl_pct < 2:
        return "危险区+微利 → 至少止盈一半"
    if hold_days >= MAX_HOLD:
        return f"超时{hold_days}天 → 强制清仓"

    return "持有，观察盘中走势"


def build_market_outlook(calendar: dict, digest: dict, intel: dict = None) -> dict:
    """构建明天市场展望"""
    today = datetime.now().strftime("%Y-%m-%d")
    mkt_today = calendar.get(today, {})

    # 找最近交易日
    if not mkt_today:
        for d in sorted(calendar.keys(), reverse=True):
            if d <= today:
                mkt_today = calendar[d]
                break

    outlook = {
        "date": today,
        "next_trading_day": _next_trading_day(),
        "today_market": mkt_today,
        "can_open_new": True,
        "restrictions": [],
        "watch_notes": [],
    }

    trend = mkt_today.get("trend", "")
    vol = mkt_today.get("volume_state", "")
    sent = mkt_today.get("sentiment", "")
    vol_val = mkt_today.get("volatility", 0)

    # 开仓条件
    if vol == "缩量":
        outlook["can_open_new"] = False
        outlook["restrictions"].append("缩量环境 — 明日不主动开新仓")
    if trend == "空头排列":
        outlook["can_open_new"] = False
        outlook["restrictions"].append("空头排列 — 新仓只做超短(0-2天)")
    if sent == "恐慌":
        outlook["can_open_new"] = False
        outlook["restrictions"].append("恐慌情绪 — 明日只卖不买")

    # 积极信号
    if vol == "放量":
        outlook["watch_notes"].append("放量环境 — 可积极寻找开仓机会")
    if trend == "多头排列":
        outlook["watch_notes"].append("多头排列 — 持仓可适当延长")

    # 波动率提示
    if vol_val and vol_val > 1.5:
        outlook["watch_notes"].append(f"高波动({vol_val}) — 止损放宽1%, 仓位减半")

    # 摘要中的信号
    if digest:
        cycle = digest.get("cycle_stage", {}).get("stage", "")
        if cycle:
            outlook["cycle_stage"] = cycle
        alerts = digest.get("ratio_alerts", {}).get("triggered", {})
        if alerts:
            outlook["watch_notes"].append(f"比率警报: {list(alerts.keys())}")

    # 情报部收盘推演信号
    if intel and intel.get("signals"):
        for s in intel["signals"]:
            sig_text = s.get("signal", "")
            chain = s.get("logic_chain", [])
            if "流出" in sig_text or "谨慎" in sig_text:
                outlook["can_open_new"] = False
                outlook["restrictions"].append(f"情报信号: {sig_text} — {'; '.join(chain[:2])}")
            elif "流入" in sig_text or "偏暖" in sig_text:
                outlook["watch_notes"].append(f"情报信号: {sig_text} — {'; '.join(chain[:2])}")
            else:
                outlook["watch_notes"].append(f"情报信号: {sig_text}")

    return outlook


def _next_trading_day():
    """计算下一个交易日"""
    today = datetime.now()
    # 简化: 周六→周一, 周日→周一, 其他→明天
    if today.weekday() == 4:  # 周五
        return (today + timedelta(days=3)).strftime("%Y-%m-%d")
    elif today.weekday() == 5:  # 周六
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
    else:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")


def generate_full_plan():
    """生成完整的隔夜交易计划"""
    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")
    plan_date = _next_trading_day()

    print(f"\n{'='*65}")
    print(f"  隔夜交易计划 — 为 {plan_date} 准备")
    print(f"  生成时间: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*65}")

    # 加载数据（持仓优先从 portfolio.json）
    calendar = load_market_calendar()
    digest = get_recent_digest()
    intel = load_intel_signals()
    holdings = load_portfolio_holdings()
    prices, price_source = get_latest_closing_prices(holdings)

    print(f"\n  价格来源: {price_source}")

    # 市场展望
    outlook = build_market_outlook(calendar, digest, intel)

    print(f"\n  ── 明日市场展望 ──")
    print(f"  今日收盘: 趋势{outlook['today_market'].get('trend','?')}  "
          f"量能{outlook['today_market'].get('volume_state','?')}  "
          f"情绪{outlook['today_market'].get('sentiment','?')}")

    if intel and intel.get("signals"):
        print(f"  情报部: {intel['signal_count']}条推演信号")

    if outlook["can_open_new"]:
        print(f"  ✅ 明日可以开新仓")
    else:
        print(f"  ⛔ 明日不建议开新仓")

    for r in outlook["restrictions"]:
        print(f"    - {r}")
    for n in outlook["watch_notes"]:
        print(f"    - {n}")

    # 情报部推演信号详情
    if intel and intel.get("signals"):
        print(f"\n  ── 情报部收盘推演 ──")
        for s in intel["signals"]:
            conf = {"high": "★★★", "medium": "★★", "low": "★"}.get(s.get("confidence", ""), "★")
            print(f"  {conf} {s['signal']}")
            for step in s.get("logic_chain", [])[:2]:
                print(f"      {step}")

    # 逐个持仓计划
    positions_plan = []
    emergency_count = 0

    print(f"\n  {'='*65}")
    print(f"  持仓交易计划 ({len(holdings)}只)")
    print(f"  {'='*65}")

    total_value = 0
    total_pnl = 0

    for h in holdings:
        code = h["code"]
        name = h["name"]
        close = prices.get(code, h["cost"])  # 无价格用成本价
        market_value = h["qty"] * close
        total_value += market_value
        total_pnl += (close - h["cost"]) * h["qty"]

        # 估算持仓天数 — 用最早买入日期(first_buy)
        hold_days = 1
        buy_date_str = h.get("first_buy") or h.get("buy_date")
        if buy_date_str:
            try:
                bd = datetime.strptime(buy_date_str, "%Y-%m-%d")
                hold_days = (now - bd).days
            except Exception:
                pass

        pos_plan = build_position_plan(h, close, calendar.get(today_str, {}), hold_days)
        positions_plan.append(pos_plan)

        if pos_plan["priority"] == "紧急":
            emergency_count += 1

        # 打印单个持仓计划
        pnl_str = f"{pos_plan['pnl_pct']:+.1f}%"
        danger_str = f" ⚠危险区D{pos_plan['danger_day']}" if pos_plan.get("danger_zone") else ""
        trail_str = " 📈移动止损" if pos_plan.get("trail_active") else ""
        priority_str = " 🔴紧急" if pos_plan["priority"] == "紧急" else (" 🟡关注" if pos_plan["priority"] == "关注" else "")

        print(f"\n  ┌─ {name}({code}) {pnl_str} 持{hold_days}天{danger_str}{trail_str}{priority_str}")
        print(f"  │  {h['qty']}股 成本{h['cost']:.2f} 现价{close:.2f} 市值{market_value:,.0f}")
        print(f"  │  硬止损: {pos_plan['levels']['hard_stop']:.2f}  止盈50%: {pos_plan['levels']['take_profit_half']:.2f}  止盈全部: {pos_plan['levels']['take_profit_all']:.2f}")
        if pos_plan.get("trail_active"):
            print(f"  │  移动止损线: {pos_plan['levels'].get('trail_stop', 0):.2f} (浮盈>5%激活)")
        if pos_plan.get("enter_danger_tomorrow"):
            print(f"  │  ⚠ 明日进入危险区(第3天) — 必须特别谨慎!")

        print(f"  ├─ 明日情景 ─")
        for s in pos_plan["scenarios"]:
            print(f"  │  [{s['name']}] {s['trigger']}")
            print(f"  │    → {s['action']}")

        print(f"  └{'─'*40}")

    # 组合总览
    total_cost = sum(h["cost"] * h["qty"] for h in holdings)
    print(f"\n  {'='*65}")
    print(f"  组合总览")
    print(f"  {'='*65}")
    print(f"  总成本: {total_cost:,.0f}  总市值: {total_value:,.0f}  总盈亏: {total_pnl:+,.0f} ({total_pnl/total_cost*100:+.2f}%)")
    print(f"  需紧急处理: {emergency_count}只")

    if emergency_count > 0:
        print(f"\n  ╔════════════════════════════════╗")
        print(f"  ║ 🔴 开盘优先处理: {emergency_count}只  ║")
        print(f"  ╚════════════════════════════════╝")
        for p in positions_plan:
            if p["priority"] == "紧急":
                print(f"  → {p['name']}({p['code']}): 现价{p['close']:.2f} 盈亏{p['pnl_pct']:+.1f}%")
                for s in p["scenarios"]:
                    if "低开" in s["name"] or "止损" in s["name"]:
                        print(f"     [{s['name']}] {s['action']}")

    # 保存
    plan_data = {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "for_date": plan_date,
        "market_outlook": outlook,
        "positions": positions_plan,
        "summary": {
            "total_cost": round(total_cost, 0),
            "total_value": round(total_value, 0),
            "total_pnl": round(total_pnl, 0),
            "total_pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
            "emergency_count": emergency_count,
            "can_open_new": outlook["can_open_new"],
        },
    }

    # 保存JSON (机器读)
    json_path = os.path.join(PLAN_DIR, f"plan_{plan_date}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(plan_data, f, ensure_ascii=False, indent=2, default=str)

    # 保存Markdown (人读)
    md_path = os.path.join(PLAN_DIR, f"plan_{plan_date}.md")
    _write_markdown_plan(plan_data, md_path)

    print(f"\n  计划已保存:")
    print(f"    {json_path}")
    print(f"    {md_path}")

    return plan_data


def _write_markdown_plan(plan_data: dict, path: str):
    """写人类可读的Markdown版交易计划"""
    lines = []
    lines.append(f"# 隔夜交易计划 — {plan_data['for_date']}")
    lines.append(f"")
    lines.append(f"生成: {plan_data['generated_at']}")
    lines.append(f"")

    # 市场展望
    outlook = plan_data["market_outlook"]
    lines.append(f"## 明日市场展望")
    lines.append(f"")
    mkt = outlook.get("today_market", {})
    lines.append(f"- 趋势: {mkt.get('trend','?')}")
    lines.append(f"- 量能: {mkt.get('volume_state','?')}")
    lines.append(f"- 情绪: {mkt.get('sentiment','?')}")
    lines.append(f"- 可开新仓: {'是' if outlook['can_open_new'] else '否'}")
    for r in outlook.get("restrictions", []):
        lines.append(f"- ⛔ {r}")
    for n in outlook.get("watch_notes", []):
        lines.append(f"- 💡 {n}")
    lines.append(f"")

    # 持仓计划
    lines.append(f"## 持仓计划 ({len(plan_data['positions'])}只)")
    lines.append(f"")

    for p in plan_data["positions"]:
        urgency = "🔴" if p["priority"] == "紧急" else ("🟡" if p["priority"] == "关注" else "🟢")
        lines.append(f"### {urgency} {p['name']}({p['code']})")
        lines.append(f"")
        lines.append(f"| 项目 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 持仓 | {p['qty']}股 |")
        lines.append(f"| 成本 | {p['cost']:.2f} |")
        lines.append(f"| 现价 | {p['close']:.2f} |")
        lines.append(f"| 盈亏 | {p['pnl_pct']:+.2f}% ({p['pnl_amount']:+,.0f}元) |")
        lines.append(f"| 持仓天数 | {p['hold_days']}天 |")
        lines.append(f"| 硬止损 | {p['levels']['hard_stop']:.2f} (-7%) |")
        lines.append(f"| 止盈50% | {p['levels']['take_profit_half']:.2f} (+8%) |")
        lines.append(f"| 止盈全部 | {p['levels']['take_profit_all']:.2f} (+15%) |")
        if p.get("trail_active"):
            lines.append(f"| 移动止损 | {p['levels'].get('trail_stop', 0):.2f} |")
        if p.get("danger_zone"):
            lines.append(f"| ⚠ 危险区 | 第{p.get('danger_day',0)}天 |")
        lines.append(f"")

        lines.append(f"**明日情景:**")
        lines.append(f"")
        for s in p["scenarios"]:
            lines.append(f"- **{s['name']}** ({s['trigger']})")
            lines.append(f"  → {s['action']}")
        lines.append(f"")

    # 组合汇总
    s = plan_data["summary"]
    lines.append(f"## 组合汇总")
    lines.append(f"")
    lines.append(f"| 指标 | 值 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 总成本 | {s['total_cost']:,.0f} |")
    lines.append(f"| 总市值 | {s['total_value']:,.0f} |")
    lines.append(f"| 总盈亏 | {s['total_pnl']:+,.0f} ({s['total_pnl_pct']:+.2f}%) |")
    lines.append(f"| 紧急处理 | {s['emergency_count']}只 |")
    lines.append(f"| 可开新仓 | {'是' if s['can_open_new'] else '否'} |")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def cmd_latest():
    """查看最新交易计划"""
    files = sorted(glob.glob(os.path.join(PLAN_DIR, "plan_*.json")))
    if not files:
        print("暂无交易计划，先运行 python nightly_plan.py generate")
        return

    with open(files[-1], "r") as f:
        plan = json.load(f)

    print(f"\n  最新交易计划: {plan['for_date']}")
    print(f"  生成时间: {plan['generated_at']}")
    print(f"  可开新仓: {'是' if plan['summary']['can_open_new'] else '否'}")
    print(f"  紧急处理: {plan['summary']['emergency_count']}只")
    print(f"  总盈亏: {plan['summary']['total_pnl']:+,.0f} ({plan['summary']['total_pnl_pct']:+.2f}%)")
    print(f"\n  阅读完整计划: {files[-1].replace('.json', '.md')}")


def main():
    # 周末守卫：非交易日跳过
    if datetime.now().weekday() >= 5:
        print("非交易日，跳过 nightly_plan")
        return

    if len(sys.argv) < 2:
        print("用法:")
        print("  python nightly_plan.py generate   # 生成隔夜交易计划")
        print("  python nightly_plan.py latest     # 查看最新计划")
        print("  python nightly_plan.py auto       # 自动模式(供cron调用)")
        return

    cmd = sys.argv[1]
    if cmd in ("generate", "auto"):
        generate_full_plan()
    elif cmd == "latest":
        cmd_latest()
    else:
        print(f"未知命令: {cmd}")


if __name__ == "__main__":
    main()
