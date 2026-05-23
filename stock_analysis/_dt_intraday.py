"""Daily task command: intraday_analysis — run_intraday_analysis"""
import json
from datetime import datetime

from daily_task import (
    logger, ensure_data_dir, date_today, send_feishu_message,
    load_portfolio, fetch_quotes_batch, fetch_news_for_holdings,
    _already_ran_today, date_now_compact, GLOBAL_INDICES,
    STOCK_DATA_DIR, fetch_index_quote,
    load_vv_insights, format_vv_for_feishu,
)


def run_intraday_analysis(mode: str):
    """30分钟盘中快照 (11:30 或 15:00 执行)"""
    logger.info("=" * 50)
    logger.info(f"执行 intraday_analysis — {mode}")
    ensure_data_dir()

    dt = datetime.now()
    dedup_key = f"analysis_{mode}_{dt.strftime('%Y%m%d')}"
    if _already_ran_today(dedup_key):
        logger.warning(f"[{mode}] 今日已执行过，跳过重复调用")
        return None

    ts_compact = date_now_compact()

    indices = {}
    for code, name in GLOBAL_INDICES:
        q = fetch_index_quote(code, name)
        if q:
            key_map = {"上证指数": "sh", "深证成指": "sz", "创业板指": "cy", "科创50": "kc50"}
            indices[key_map.get(name, name)] = q.get("price", 0)

    holdings = load_portfolio()
    codes = [h["code"] for h in holdings]
    quotes = fetch_quotes_batch(codes)

    holdings_data = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        q = quotes.get(h["code"])
        if q is None or q.get("price", 0) <= 0:
            logger.warning(f"⚠ {h['code']} 30min行情缺失，使用成本价")
            price = h.get("cost", 0)
            q = {}
        else:
            price = q.get("price", h.get("cost", 0))
        cost = h["cost"]
        shares = h["shares"]
        mv = price * shares
        pnl_pct = round(((price - cost) / cost * 100), 2) if cost > 0 else 0

        holdings_data.append({
            "code": h["code"],
            "name": h.get("name", ""),
            "price": price,
            "today_chg": q.get("change_pct", 0),
            "cost": cost,
            "pnl_pct": pnl_pct,
            "mv": round(mv, 2),
        })
        total_value += mv
        total_cost += cost * shares

    total_pnl = total_value - total_cost
    total_pnl_pct = round((total_pnl / total_cost * 100), 2) if total_cost > 0 else 0

    holdings_news = fetch_news_for_holdings(codes, limit=10)

    morning_check = None
    if mode == "midday":
        try:
            brief_path = STOCK_DATA_DIR / "morning_brief_agent_latest.md"
            if brief_path.exists():
                brief_text = brief_path.read_text(encoding="utf-8")
                bullish_kw = ["看多", "反弹", "上涨", "走强", "关注", "布局", "积极"]
                bearish_kw = ["看空", "下跌", "走弱", "回避", "风险", "减仓", "谨慎"]
                bullish_count = sum(1 for s in bullish_kw if s in brief_text)
                bearish_count = sum(1 for s in bearish_kw if s in brief_text)

                if total_pnl_pct > 0.5:
                    actual_trend = "上涨"
                elif total_pnl_pct < -0.5:
                    actual_trend = "下跌"
                else:
                    actual_trend = "震荡"

                tone = "偏多" if bullish_count > bearish_count else ("偏空" if bearish_count > bullish_count else "中性")
                match = (tone == "偏多" and actual_trend == "上涨") or (tone == "偏空" and actual_trend == "下跌")
                morning_check = {
                    "brief_exists": True,
                    "brief_tone": tone,
                    "actual_trend": actual_trend,
                    "portfolio_pnl": total_pnl_pct,
                    "match": match,
                }
        except Exception as e:
            logger.warning(f"晨报预测验证失败: {e}")

    vv_feishu = ""
    if mode == "midday":
        try:
            vv_data = load_vv_insights(hours=96)
            vv_feishu = format_vv_for_feishu(vv_data)
            if vv_data["total_videos"] > 0:
                logger.info(f"大V雷达: {vv_data['author_count']}位大V, {vv_data['total_videos']}条视频")
        except Exception as e:
            logger.warning(f"大V雷达加载失败: {e}")

    output = {
        "type": "30min_analysis",
        "time": dt.strftime("%Y-%m-%d %H:%M"),
        "indices": indices,
        "portfolio": {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": total_pnl_pct,
        },
        "holdings": holdings_data,
        "holdings_news": holdings_news,
        "morning_check": morning_check,
        "vv_insights": vv_feishu,
    }

    json_path = ensure_data_dir() / f"analysis_30min_{ts_compact}.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    md_path = ensure_data_dir() / f"analysis_30min_{ts_compact}.md"
    md_lines = []
    md_lines.append(f"# 盘中快照 | {dt.strftime('%Y-%m-%d %H:%M')}\n")
    if indices:
        md_lines.append("\n## 指数\n")
        for k, v in indices.items():
            md_lines.append(f"- {k}: {v:.2f}\n")
    md_lines.append(f"\n组合市值: {total_value:,.0f} | 盈亏: {total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)\n")
    md_lines.append("| 股票 | 现价 | 日内涨跌 | 盈亏 | 市值 |")
    md_lines.append("|------|------|----------|------|------|")
    for h in holdings_data:
        sign = "+" if h["pnl_pct"] >= 0 else ""
        md_lines.append(f"| {h['name']}({h['code']}) | {h['price']} | {h['today_chg']:+.1f}% | {sign}{h['pnl_pct']:.1f}% | {h['mv']:,.0f} |")
    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown 输出: {md_path}")

    feishu_content = f"盘中快照 ({dt.strftime('%H:%M')})\n组合市值: **{total_value:,.0f}元** | 盈亏: **{total_pnl:+,.0f}元 ({total_pnl_pct:+.1f}%)**\n"
    feishu_content += "\n".join(
        f"- {h['name']}: {h['price']} ({h['today_chg']:+.1f}%)"
        for h in holdings_data
    )

    if holdings_news:
        feishu_content += "\n\n**持仓相关新闻**:\n" + "\n".join(
            f"- [{n.get('time','?')}] {n['title'][:60]}"
            for n in holdings_news[:5]
        )

    if morning_check:
        mark = "✓" if morning_check["match"] else "✗"
        feishu_content += (
            f"\n\n**晨报验证** {mark}\n"
            f"晨报{ morning_check['brief_tone'] } | "
            f"实盘{morning_check['portfolio_pnl']:+.1f}%\n"
        )
        if not morning_check["match"] and morning_check["portfolio_pnl"] < -1:
            feishu_content += "⚠ 方向偏差，注意下午策略修正\n"

    if vv_feishu:
        feishu_content += "\n\n" + vv_feishu

    ok = send_feishu_message(f"盘中快照 | {dt.strftime('%m/%d %H:%M')}", feishu_content, chat_id="midday")
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("intraday_analysis 完成")
    return output
