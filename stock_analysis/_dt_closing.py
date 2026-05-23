"""Daily task command: closing_review — run_closing_review"""
import json
from datetime import datetime

from daily_task import (
    logger, ensure_data_dir, date_today, is_market_hours,
    send_feishu_message,
    load_portfolio, calculate_position_report, fetch_index_quote,
    safe_request, GLOBAL_INDICES, EASTMONEY_BLOCKED,
    format_indices_feishu, format_holdings_feishu,
    preflight_scan,
)


def run_closing_review():
    """收盘复盘 (15:15 执行)"""
    logger.info("=" * 50)
    logger.info("执行 closing_review — 收盘复盘")
    ensure_data_dir()

    dt = datetime.now()
    date_str = date_today()

    # 1) 持仓盈亏
    logger.info("计算持仓盈亏...")
    holdings = load_portfolio()
    holdings_report = calculate_position_report(holdings)

    # 2) 市场背景
    logger.info("获取指数行情...")
    indices = []
    for code, name in GLOBAL_INDICES:
        q = fetch_index_quote(code, name)
        if q:
            indices.append({
                "name": name,
                "code": code,
                "price": q.get("price", 0),
                "change_pct": q.get("change_pct", 0),
            })

    # 3) 热门板块 (仅东方财富可用时)
    hot_sectors = []
    if not EASTMONEY_BLOCKED:
        try:
            params = {
                "pn": 1, "pz": 10, "po": 1, "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2, "invt": 2,
                "fid": "f3",
                "fs": "m:90+t:2",
                "fields": "f2,f3,f4,f12,f14",
            }
            r = safe_request("https://push2.eastmoney.com/api/qt/clist/get", params=params, timeout=10)
            if r:
                items = r.json().get("data", {}).get("diff", [])
                for item in items:
                    hot_sectors.append({
                        "name": item.get("f14", ""),
                        "change_pct": item.get("f3", 0),
                    })
        except Exception as e:
            logger.warning(f"板块数据获取失败: {e}")

    # 4) 持仓建议
    recommendations = []
    for h in holdings_report["holdings"]:
        pnl = h["pnl_pct"]
        dist = h["dist_to_stop"]
        if pnl >= 15:
            recommendations.append({
                "code": h["code"], "name": h["name"],
                "action": "考虑部分止盈",
                "detail": f"浮盈{pnl:.1f}%，评估是否分批锁利",
                "urgency": "medium",
            })
        elif dist <= 8:
            recommendations.append({
                "code": h["code"], "name": h["name"],
                "action": "关注",
                "detail": f"距止损位{dist:.1f}%，监控是否企稳",
                "urgency": "medium",
            })

    output = {
        "title": f"收盘复盘 | {date_str}日",
        "date": date_str,
        "time": dt.strftime("%H:%M:%S"),
        "is_trading_hours": is_market_hours(dt),
        "holdings_report": holdings_report,
        "market_context": {
            "indices": indices,
            "breadth": {},
        },
        "hot_sectors": hot_sectors,
        "actions": recommendations,
        "mcp_checklist": {
            "fund_flow_check": [
                {"code": h["code"], "tool": "mcp__china-stock__get_fund_flow",
                 "purpose": "验证超大单方向是否与量价模型一致"}
                for h in holdings_report["holdings"]
            ],
            "volume_price_phase": [
                {"code": h["code"], "tool": "mcp__china-stock__get_hist_data",
                 "purpose": "识别当前处于VCP五阶段中的哪个阶段"}
                for h in holdings_report["holdings"]
            ],
            "investor_sentiment": [
                {"code": h["code"], "tool": "mcp__china-stock__get_investor_sentiment",
                 "purpose": "补充情绪数据辅助判断"}
                for h in holdings_report["holdings"]
            ],
        },
    }

    # 写入JSON
    json_path = ensure_data_dir() / "closing_review.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    # 写入Markdown
    md_path = ensure_data_dir() / "closing_review.md"
    md_lines = []
    md_lines.append(f"# 收盘复盘 | {date_str}\n")
    md_lines.append(f"**时间**: {dt.strftime('%H:%M:%S')}\n")

    try:
        from stage_context import intraday_summary
        ims = intraday_summary()
        if ims:
            md_lines.append("\n" + ims + "\n")
    except ImportError:
        pass

    md_lines.append("\n## 指数\n")
    md_lines.append("| 指数 | 点位 | 涨跌 |")
    md_lines.append("|------|------|------|")
    for idx in indices:
        sign = "+" if idx.get("change_pct", 0) >= 0 else ""
        md_lines.append(f"| {idx['name']} | {idx['price']:.2f} | {sign}{idx['change_pct']:.2f}% |")

    md_lines.append("\n## 持仓\n")
    rpt = holdings_report
    md_lines.append(f"总市值: **{rpt['total_value']:,.0f}** | 总盈亏: **{rpt['total_pnl']:+,.0f}** ({rpt['total_pnl_pct']:+.1f}%)\n")
    md_lines.append("| 股票 | 现价 | 成本 | 盈亏% | 盈亏额 | 距止损 |")
    md_lines.append("|------|------|------|-------|--------|--------|")
    for h in rpt["holdings"]:
        sign = "+" if h["pnl_pct"] >= 0 else ""
        md_lines.append(
            f"| {h['name']}({h['code']}) | {h['price']} | {h['cost']} | "
            f"{sign}{h['pnl_pct']:.1f}% | {sign}{h['pnl_amt']:,.0f} | {h['dist_to_stop']:.1f}% |"
        )

    if hot_sectors:
        md_lines.append("\n## 热门板块\n")
        for s in hot_sectors[:8]:
            md_lines.append(f"- {s['name']}: {s['change_pct']:+.2f}%\n")

    if recommendations:
        md_lines.append("\n## 操作建议\n")
        for r in recommendations:
            md_lines.append(f"- **{r['name']}**: {r['action']} — {r['detail']}\n")

    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown 输出: {md_path}")

    # 发送飞书
    feishu_content = format_indices_feishu(indices)
    feishu_content += f"\n\n组合总市值: **{rpt['total_value']:,.0f}元** | 总盈亏: **{rpt['total_pnl']:+,.0f}元 ({rpt['total_pnl_pct']:+.1f}%)**\n\n"
    feishu_content += format_holdings_feishu(rpt["holdings"])

    if recommendations:
        feishu_content += "\n**操作建议**\n"
        for r in recommendations:
            feishu_content += f"- {r['name']}: {r['action']} ({r['urgency']})\n"

    preflight = preflight_scan(["portfolio.json", "closing_review.json"])
    if preflight["healthy"]:
        ok = send_feishu_message(f"收盘复盘 | {date_str}", feishu_content, chat_id="closing")
        logger.info(f"飞书发送: {'成功' if ok else '失败'}")
    else:
        logger.warning(f"收盘复盘跳过发送: {preflight['summary']}")
        send_feishu_message(f"⚠ 收盘复盘跳过 | {date_str}",
                           f"数据保鲜检查未通过:\n{preflight['summary']}", chat_id="alerts")
    logger.info("closing_review 完成")
    return output
