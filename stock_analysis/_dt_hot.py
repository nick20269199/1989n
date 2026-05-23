"""Daily task command: hot_stocks — run_hot_stocks"""
import json
from datetime import datetime

from daily_task import (
    logger, ensure_data_dir, send_feishu_message,
    collect_hot_stocks, db_save_hot_stocks, _DB_AVAILABLE,
)


def run_hot_stocks():
    """热门股票采集 (09:15 起每小时执行)"""
    logger.info("=" * 50)
    logger.info("执行 hot_stocks — 热门股票采集")

    ensure_data_dir()

    stocks = collect_hot_stocks()

    output = {
        "update_time": datetime.now().isoformat(),
        "top": stocks,
    }

    json_path = ensure_data_dir() / "hot_stocks.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path} ({len(stocks)} 条)")

    if _DB_AVAILABLE and stocks:
        try:
            db_save_hot_stocks(stocks)
            logger.info(f"数据库保存: {len(stocks)} 条")
        except Exception as e:
            logger.warning(f"数据库保存失败: {e}")

    if not stocks:
        logger.warning("hot_stocks 采集结果为空，跳过飞书发送")
    else:
        lines = ["**热门股票 Top 10**\n"]
        for s in stocks[:10]:
            sign = "+" if s.get("change_pct", 0) >= 0 else ""
            lines.append(f"- {s.get('rank','')}. {s['name']}({s['code']}) {s.get('price','')} ({sign}{s.get('change_pct',0):.2f}%)")
        ok = send_feishu_message(f"热门股票 | {datetime.now().strftime('%H:%M')}", "\n".join(lines), chat_id="midday")
        logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("hot_stocks 完成")
    return output
