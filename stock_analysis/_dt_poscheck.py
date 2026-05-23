"""Daily task command: position_check — run_position_check + _simple_position_check"""
import json
from datetime import datetime
from dataclasses import dataclass, field
from typing import List as _List

from daily_task import (
    logger, ensure_data_dir, date_today, timestamp_now,
    send_feishu_message,
    load_portfolio, fetch_quotes_batch,
    _POSITION_MGR_AVAILABLE, PositionManager,
)


def run_position_check():
    """持仓三层检查 — 实时价格 + 硬止损/软止损/危险区/止盈/超时"""
    logger.info("=" * 50)
    logger.info("执行 position_check — 持仓三层检查")
    ensure_data_dir()

    timestamp = timestamp_now()
    date_str = date_today()
    holdings = load_portfolio()

    if not holdings:
        logger.warning("无持仓数据，跳过")
        return

    codes = [h["code"] for h in holdings]
    quotes = fetch_quotes_batch(codes)
    prices = {code: q["price"] for code, q in quotes.items() if q.get("price", 0) > 0}

    if _POSITION_MGR_AVAILABLE:
        mgr = PositionManager()
        mgr.holdings = [
            {"code": h["code"], "name": h["name"], "qty": h["shares"],
             "cost": h["cost"], "sector": h.get("sector", ""),
             "first_buy": h.get("first_buy", ""),
             "latest_buy": h.get("latest_buy", "")}
            for h in holdings
        ]
        positions = mgr.update_positions(prices)
        can_open, open_reasons = mgr.can_open_new()
    else:
        positions = _simple_position_check(holdings, prices)
        can_open = True
        open_reasons = []

    emergency = [p for p in positions if hasattr(p, 'action') and p.action == "清仓"] if _POSITION_MGR_AVAILABLE else []
    warning_ps = [p for p in positions if hasattr(p, 'action') and p.action == "减半"] if _POSITION_MGR_AVAILABLE else []
    normal = [p for p in positions if hasattr(p, 'action') and p.action == "持有"] if _POSITION_MGR_AVAILABLE else positions

    total_value = sum(p.market_value for p in positions if hasattr(p, 'last_price') and p.last_price > 0)
    total_pnl = sum(p.pnl_amount for p in positions if hasattr(p, 'last_price') and p.last_price > 0)
    total_cost = sum(p.cost * p.qty for p in positions)

    output = {
        "date": date_str,
        "time": timestamp,
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
        "can_open_new": can_open,
        "open_blockers": [r[1] for r in open_reasons if r[0] == "NOGO"] if not can_open else [],
        "emergency": [{"code": p.code, "name": p.name, "action": p.action,
                        "pnl_pct": round(p.pnl_pct, 2), "warnings": p.warnings}
                      for p in emergency],
        "warnings": [{"code": p.code, "name": p.name, "action": p.action,
                       "pnl_pct": round(p.pnl_pct, 2), "warnings": p.warnings}
                     for p in warning_ps],
        "all_positions": [
            {"code": p.code, "name": p.name, "qty": p.qty, "cost": p.cost,
             "last_price": p.last_price if p.last_price > 0 else None,
             "pnl_pct": round(p.pnl_pct, 2) if p.last_price > 0 else None,
             "hold_days": p.hold_days, "status": p.status, "action": p.action,
             "warnings": p.warnings if hasattr(p, 'warnings') else []}
            for p in positions
        ],
    }
    json_path = ensure_data_dir() / "position_check.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"持仓数据已写入: {json_path}")

    print(f"\n{'='*60}")
    print(f"  持仓三层检查 — {date_str} {timestamp}")
    print(f"{'='*60}")
    print(f"  总成本: {total_cost:,.0f}  总市值: {total_value:,.0f}  总盈亏: {total_pnl:+,.0f}")
    print(f"  开新仓: {'✅ 允许' if can_open else '⛔ 禁止'}")
    if not can_open:
        for reason in open_reasons:
            if reason[0] == "NOGO":
                print(f"    - {reason[1]}")

    if emergency:
        print(f"\n  ⛔ 紧急: {len(emergency)} 只需要立即处理")
        for p in emergency:
            print(f"    {p.name}({p.code}): {p.action} | {p.pnl_pct:+.1f}%")
            for w in p.warnings:
                print(f"      → {w}")

    if warning_ps:
        print(f"\n  ⚠ 警告: {len(warning_ps)} 只需关注")
        for p in warning_ps:
            print(f"    {p.name}({p.code}): {p.action} | {p.pnl_pct:+.1f}%")

    if not emergency and not warning_ps:
        print(f"\n  ✅ 所有持仓正常")

    if emergency:
        feishu_lines = [f"**⛔ 持仓紧急警报 — {date_str} {timestamp}**\n"]
        feishu_lines.append(f"总盈亏: {total_pnl:+,.0f} ({total_pnl/total_cost*100:+.2f}%)\n" if total_cost > 0 else "")
        for p in emergency:
            feishu_lines.append(f"\n**{p.name}({p.code})**")
            feishu_lines.append(f"- 操作: {p.action}")
            feishu_lines.append(f"- 盈亏: {p.pnl_pct:+.1f}%")
            for w in p.warnings:
                feishu_lines.append(f"- {w}")
        ok = send_feishu_message(f"⚠ 持仓警报 | {date_str}", "\n".join(feishu_lines))
        logger.info(f"飞书警报发送: {'成功' if ok else '失败'}")

    md_lines = [
        f"# 持仓三层检查 | {date_str}\n",
        f"**时间**: {timestamp} | **开新仓**: {'✅ 允许' if can_open else '⛔ 禁止'}\n\n",
        f"## 组合总览\n",
        f"| 指标 | 数值 |\n|------|------|\n",
        f"| 总成本 | {total_cost:,.0f} |\n",
        f"| 总市值 | {total_value:,.0f} |\n",
        f"| 总盈亏 | {total_pnl:+,.0f} ({total_pnl/total_cost*100:+.2f}%) |\n\n" if total_cost > 0 else "\n",
        f"## 持仓明细\n",
        f"| 代码 | 名称 | 持仓 | 成本 | 现价 | 盈亏 | 天数 | 状态 | 操作 |\n",
        f"|------|------|------|------|------|------|------|------|------|\n",
    ]
    for p in positions:
        price_str = f"{p.last_price:.2f}" if p.last_price > 0 else "-"
        pnl_str = f"{p.pnl_pct:+.1f}%" if p.last_price > 0 else "-"
        md_lines.append(
            f"| {p.code} | {p.name} | {p.qty} | {p.cost:.2f} | {price_str} | "
            f"{pnl_str} | {p.hold_days} | {p.status} | {p.action} |\n")
        if hasattr(p, 'warnings') and p.warnings:
            for w in p.warnings:
                md_lines.append(f"| | → {w} | | | | | | | |\n")
    md_path = ensure_data_dir() / "position_check.md"
    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"持仓报告已写入: {md_path}")

    return output


def _simple_position_check(holdings, prices):
    """简易持仓检查（PositionManager 不可用时回退）"""
    RULES = {
        "hard_stop": -7.0, "soft_stop": -3.0, "take_profit_half": 8.0,
        "take_profit_all": 15.0, "danger_zone": (3, 5), "max_hold": 10,
    }

    @dataclass
    class SimplePos:
        code: str; name: str; qty: int; cost: float
        hard_stop_price: float; last_price: float = 0.0
        market_value: float = 0.0; pnl_pct: float = 0.0
        pnl_amount: float = 0.0; hold_days: int = 0
        status: str = "正常"; action: str = "持有"
        warnings: _List[str] = field(default_factory=list)

    results = []
    for h in holdings:
        code = h["code"]
        cost = h["cost"]
        p = SimplePos(code=code, name=h["name"], qty=h["shares"], cost=cost,
                       hard_stop_price=cost * 0.93)
        if code in prices:
            price = prices[code]
            p.last_price = price
            p.market_value = p.qty * price
            p.pnl_pct = (price - cost) / cost * 100
            p.pnl_amount = (price - cost) * p.qty

            if p.pnl_pct <= RULES["hard_stop"]:
                p.status, p.action = "止损", "清仓"
                p.warnings.append(f"硬止损触发: {p.pnl_pct:.1f}%")
            elif p.pnl_pct <= RULES["soft_stop"]:
                p.status, p.action = "预警", "减半"
                p.warnings.append(f"软止损: {p.pnl_pct:.1f}%")
            elif p.pnl_pct >= RULES["take_profit_all"]:
                p.status, p.action = "止盈", "清仓"
                p.warnings.append(f"+15%止盈: {p.pnl_pct:.1f}%")
            elif p.pnl_pct >= RULES["take_profit_half"]:
                p.status, p.action = "止盈", "减半"
                p.warnings.append(f"+8%止盈一半: {p.pnl_pct:.1f}%")
        else:
            p.warnings.append("无实时价格")
        results.append(p)
    return results
