#!/usr/bin/env python3
"""
三线桥接模块 — 打通早间→盘中→收盘数据流

三条独立分析线：
  早间: morning_enhanced.json (news_scheduler.py)
  盘中: intel_report_*.json (intraday_report.py)
  收盘: closing_review.json (daily_task.py closing_review)

问题：各跑各的，早上的新闻没喂给盘中判断，盘中的异动没传到复盘。
解决：每个阶段读取前序阶段的 JSON，提取关键上下文。

用法:
  from stage_context import get_morning_context, get_intraday_context
  ctx = get_morning_context()  # 在 intraday_report.py 里调用
  ctx = get_intraday_context() # 在 closing_review 里调用
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta

from config import STOCK_DATA_DIR

logger = logging.getLogger(__name__)

DATA_DIR = Path(STOCK_DATA_DIR)
CST = __import__('datetime').timezone(timedelta(hours=8))


def _load_json(filename: str) -> dict | None:
    """加载 JSON 文件，不存在返回 None"""
    path = DATA_DIR / filename
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"读取 {filename} 失败: {e}")
        return None


def _find_latest(prefix: str) -> dict | None:
    """找到最新的匹配 JSON 文件"""
    files = sorted(DATA_DIR.glob(f"{prefix}*.json"), reverse=True)
    for f in files:
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def get_morning_context() -> dict:
    """
    获取早间新闻上下文。
    在 intraday_report.py 中调用，让盘中分析知道早上发生了什么。
    """
    data = _load_json("morning_enhanced.json")
    if not data:
        return {"available": False, "reason": "morning_enhanced.json 不存在"}

    ctx = {"available": True}

    # 隔夜外盘
    global_ov = data.get("global_overnight", {})
    if global_ov:
        ctx["global_overnight"] = global_ov

    # 今日关注题材/个股
    focus = data.get("today_focus", {})
    if focus:
        ctx["today_focus"] = focus

    # 经济日历今日事件
    cal = data.get("economic_calendar", {})
    today = datetime.now(CST).strftime("%m/%d")
    todays_events = []
    for ev in cal.get("monthly_events", []):
        if ev.get("date") == today:
            todays_events.append(ev)
    if todays_events:
        ctx["events_today"] = todays_events

    # 持仓扫描摘要
    portfolio = data.get("portfolio_scan", {})
    if portfolio:
        ctx["portfolio_scan"] = portfolio

    logger.info(f"早间上下文: {len(ctx)} 个字段")
    return ctx


def get_intraday_context(lookback_minutes: int = 60) -> dict:
    """
    获取盘中最新异动上下文。
    在 daily_task.py closing_review 中调用，让复盘知道盘中发生了什么。
    """
    data = _find_latest("intel_report_")
    if not data:
        return {"available": False, "reason": "无盘中报告"}

    ctx = {
        "available": True,
        "time": data.get("time", ""),
    }

    # 涨停/跌停数
    breadth = data.get("breadth", {})
    ctx["breadth"] = {
        "up": breadth.get("up", 0),
        "down": breadth.get("down", 0),
        "limit_up": breadth.get("limit_up", 0),
        "limit_down": breadth.get("limit_down", 0),
    }

    # 盘中异动 — pnl_pct 偏离超过 3% 的持仓
    holdings = data.get("holdings", [])
    anomalies = []
    for h in holdings:
        pnl = h.get("pnl_pct") or 0
        chg = h.get("chg_pct") or 0
        if abs(pnl) >= 7 or abs(chg) >= 5:
            anomalies.append({
                "code": h.get("code"),
                "name": h.get("name"),
                "pnl_pct": pnl,
                "chg_pct": chg,
                "vol_ratio": h.get("vol_ratio") or 0,
            })
    if anomalies:
        ctx["anomalies"] = anomalies

    # 盘中催化题材
    catalysts = data.get("catalysts", [])
    if catalysts:
        ctx["catalysts"] = [c.get("concept", "") for c in catalysts]

    logger.info(f"盘中上下文: {len(ctx)} 个字段, {len(anomalies)} 个异动")
    return ctx


def get_closing_context() -> dict:
    """获取收盘复盘上下文（供隔夜分析使用）"""
    data = _load_json("closing_review.json")
    if not data:
        return {"available": False, "reason": "closing_review.json 不存在"}

    ctx = {"available": True, "time": data.get("date", "")}

    # 提取收盘关键结论（如果有结构化字段）
    for key in ("conclusion", "summary", "highlights"):
        if key in data:
            ctx[key] = data[key]

    return ctx


# ── 快捷函数：生成上下文摘要文本 ──

def morning_summary() -> str:
    """早间上下文 → 一段文字，可直接拼入盘中报告"""
    ctx = get_morning_context()
    if not ctx["available"]:
        return ""

    lines = ["## 早间回顾"]
    if "today_focus" in ctx:
        tf = ctx["today_focus"]
        if isinstance(tf, dict):
            for k, v in tf.items():
                lines.append(f"- {k}: {v}")
        elif isinstance(tf, list):
            for item in tf:
                lines.append(f"- {item}")
    if "events_today" in ctx:
        lines.append("- 今日事件: " + ", ".join(
            e.get("event", "") for e in ctx["events_today"]
        ))
    if "global_overnight" in ctx:
        go = ctx["global_overnight"]
        if isinstance(go, dict):
            for k, v in go.items():
                lines.append(f"- 隔夜{k}: {v}")
    return "\n".join(lines) + "\n"


def intraday_summary() -> str:
    """盘中异动 → 一段文字，可直接拼入收盘复盘"""
    ctx = get_intraday_context()
    if not ctx["available"]:
        return ""

    lines = ["## 盘中异动回顾"]
    lines.append(f"涨跌比 {ctx['breadth']['up']}/{ctx['breadth']['down']} "
                 f"涨停{ctx['breadth']['limit_up']} 跌停{ctx['breadth']['limit_down']}")
    if ctx.get("catalysts"):
        lines.append(f"催化题材: {', '.join(ctx['catalysts'][:5])}")
    if ctx.get("anomalies"):
        lines.append("### 异常个股")
        for a in ctx["anomalies"]:
            lines.append(
                f"- **{a['name']}**({a['code']}) "
                f"涨幅{a['chg_pct']:+.2f}% PnL{a['pnl_pct']:+.2f}% "
                f"量比{a['vol_ratio']:.1f}"
            )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    print("=== 早间上下文 ===")
    print(morning_summary() or "(无)")
    print("\n=== 盘中上下文 ===")
    print(intraday_summary() or "(无)")
    print("\n=== 收盘上下文 ===")
    ctx = get_closing_context()
    print(json.dumps(ctx, ensure_ascii=False, indent=2))
