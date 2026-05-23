"""Daily task command: overnight — run_overnight"""
import json
from datetime import datetime

from daily_task import (
    logger, ensure_data_dir, date_today, date_now_compact,
    send_feishu_message,
    load_portfolio, fetch_news_for_holdings,
    get_us_index_quotes, fetch_quote_eastmoney,
    _already_ran_today, is_trading_day, EASTMONEY_BLOCKED,
    US_INDICES,
)


def run_overnight():
    """隔夜分析 (23:30 执行)"""
    logger.info("=" * 50)
    logger.info("执行 overnight — 隔夜分析")
    ensure_data_dir()

    dt = datetime.now()
    if _already_ran_today(f"overnight_{dt.strftime('%Y%m%d')}"):
        logger.warning("[overnight] 今日已执行过，跳过重复调用")
        return None

    ts_compact = date_now_compact()

    us_market = get_us_index_quotes()
    if not us_market and not EASTMONEY_BLOCKED:
        for code, name in US_INDICES:
            q = fetch_quote_eastmoney(code)
            if q:
                us_market.append({
                    "name": name,
                    "price": q.get("price", 0),
                    "change_pct": q.get("change_pct", 0),
                })

    holdings = load_portfolio()
    today_news = fetch_news_for_holdings([h["code"] for h in holdings], limit=20)

    outlook = "观望"
    if is_trading_day():
        outlook = "正常交易"

    output = {
        "title": f"隔夜分析 | {date_today()}日",
        "date": date_today(),
        "time": dt.strftime("%H:%M:%S"),
        "us_market": us_market,
        "key_developments": today_news[:10],
        "next_day_outlook": outlook,
    }

    json_path = ensure_data_dir() / f"analysis_overnight_{ts_compact}.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    md_lines = []
    md_lines.append(f"# 隔夜分析 | {date_today()}\n")
    md_lines.append(f"**时间**: {dt.strftime('%H:%M:%S')}\n")
    md_lines.append("\n## 美股\n")
    for m in us_market:
        sign = "+" if m["change_pct"] >= 0 else ""
        md_lines.append(f"- {m['name']}: {m['price']:.2f} ({sign}{m['change_pct']:.2f}%)\n")
    md_lines.append(f"\n**明日展望**: {outlook}\n")

    if today_news:
        md_lines.append("\n## 关键进展\n")
        for n in today_news[:10]:
            md_lines.append(f"- {n.get('title', '')}\n")

    md_path = ensure_data_dir() / f"analysis_overnight_{ts_compact}.md"
    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown 输出: {md_path}")

    feishu_content = ""
    if us_market:
        feishu_content += "**美股**\n"
        for m in us_market:
            sign = "+" if m["change_pct"] >= 0 else ""
            feishu_content += f"- {m['name']}: {sign}{m['change_pct']:.2f}%\n"
    feishu_content += f"\n明日展望: **{outlook}**"

    ok = send_feishu_message(f"隔夜分析 | {date_today()}", feishu_content, chat_id="overnight")
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("overnight 完成")
    return output
