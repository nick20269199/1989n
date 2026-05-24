"""
竞价数据回填 — 将历史 call_auction_*.json 导入 auction_history 表
一次性脚本，执行后删除。
"""
import json
import logging
from pathlib import Path

from database import get_db, init_db

STOCK_DATA_DIR = Path("D:/1989n/stock_data")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill_auction")


def backfill():
    init_db()

    files = sorted(STOCK_DATA_DIR.glob("call_auction_*.json"))
    if not files:
        logger.warning("没有找到竞价 JSON 文件")
        return

    total_inserted = 0
    total_skipped = 0

    with get_db() as db:
        for fpath in files:
            try:
                data = json.loads(fpath.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"解析失败: {fpath.name} — {e}")
                total_skipped += 1
                continue

            portfolio = data.get("portfolio_auction") or []
            if not portfolio:
                logger.debug(f"跳过 {fpath.name} (无持仓竞价)")
                total_skipped += 1
                continue

            date_str = data.get("date", fpath.name[13:21])
            for p in portfolio:
                try:
                    db.execute(
                        """INSERT OR IGNORE INTO auction_history
                           (stock_code, date, auction_price, prev_close, auction_chg_pct, open_volume)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (p["code"], date_str,
                         p.get("auction_price"), p.get("prev_close"),
                         p.get("auction_chg_pct"), p.get("open_volume")),
                    )
                    total_inserted += 1
                except Exception as e:
                    logger.debug(f"  写入失败 {p.get('code')}@{date_str}: {e}")

            logger.info(f"  {fpath.name} → {len(portfolio)} 条")

        # 在 with 块内查询统计
        row_count = db.execute("SELECT COUNT(*) FROM auction_history").fetchone()[0]
        stock_count = db.execute("SELECT COUNT(DISTINCT stock_code) FROM auction_history").fetchone()[0]

    logger.info(f"完成: 写入 {total_inserted} 条, 跳过 {total_skipped} 文件")
    logger.info(f"auction_history 表: {row_count} 行, {stock_count} 只股票")


if __name__ == "__main__":
    backfill()
