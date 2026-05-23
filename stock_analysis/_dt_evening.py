"""Daily task command: evening — run_evening"""
import json
from datetime import datetime

from daily_task import (
    logger, ensure_data_dir, date_today, send_feishu_message,
    load_portfolio, fetch_news_for_holdings,
)


def run_evening():
    """晚间总结 (22:00 执行)"""
    logger.info("=" * 50)
    logger.info("执行 evening — 晚间总结")
    ensure_data_dir()

    dt = datetime.now()
    date_str = date_today()

    news_items = fetch_news_for_holdings([h["code"] for h in load_portfolio()], limit=30)

    snapshots = []
    try:
        for f in sorted(ensure_data_dir().glob("analysis_30min_*.json")):
            if date_str.replace("-", "") in f.name:
                snapshots.append(f.name)
    except Exception:
        pass

    hot_data = {}
    hot_path = ensure_data_dir() / "hot_stocks.json"
    if hot_path.exists():
        try:
            hot_data = json.loads(hot_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    output = {
        "title": f"晚间总结 | {date_str}日",
        "date": date_str,
        "time": dt.strftime("%H:%M:%S"),
        "news_count": len(news_items),
        "top_news": news_items[:15],
        "snapshots_available": snapshots,
        "hot_stocks_summary": {
            "total": len(hot_data.get("top", [])),
            "top5": [
                {"name": s.get("name", ""), "code": s.get("code", ""),
                 "change_pct": s.get("change_pct", 0), "rank": s.get("rank", "")}
                for s in hot_data.get("top", [])[:5]
            ],
        },
    }

    json_path = ensure_data_dir() / f"news_evening_{date_str.replace('-', '')}_2200.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    md_lines = []
    md_lines.append(f"# 晚间总结 | {date_str}\n")
    md_lines.append(f"**生成时间**: {dt.strftime('%H:%M:%S')}\n")
    md_lines.append(f"\n## 今日新闻 ({len(news_items)}条)\n")
    for n in news_items[:15]:
        md_lines.append(f"- [{n.get('source','')}] {n.get('title','')}\n")

    report_path = ensure_data_dir() / f"report_evening_{date_str.replace('-', '')}.md"
    report_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"报告输出: {report_path}")

    feishu_content = f"今日新闻 **{len(news_items)}** 条\n"
    for n in news_items[:10]:
        feishu_content += f"- {n.get('title', '')[:80]}\n"

    ok = send_feishu_message(f"晚间总结 | {date_str}", feishu_content)
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("evening 完成")
    return output
