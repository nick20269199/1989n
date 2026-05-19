"""
backfill_hot_stocks.py — 回补5月11-20日热门股票数据

数据源: akshare stock_zt_pool_em（涨停板）
输出: stock.db hot_stocks 表 + hot_stocks.json（最新）
"""

import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import akshare as ak

sys.path.insert(0, str(Path(__file__).parent))
from database import get_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")

STOCK_DATA = Path("D:/1989n/stock_data")
DB_PATH = STOCK_DATA / "stock.db"


def fetch_limit_up(date: str) -> list[dict]:
    """获取指定日期的涨停板数据。

    Args:
        date: YYYYMMDD 格式

    Returns:
        [{"code":, "name":, "price":, "change_pct":, "amount":, "market_cap":, "turnover":, "rank":}, ...]
    """
    try:
        df = ak.stock_zt_pool_em(date=date)
        if df is None or df.empty:
            logger.info(f"  {date}: 无涨停数据")
            return []
    except Exception as e:
        logger.warning(f"  {date}: 接口失败 {e}")
        return []

    stocks = []
    for _, row in df.iterrows():
        stocks.append({
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": float(row.get("最新价", 0)),
            "change_pct": round(float(row.get("涨跌幅", 0)), 2),
            "amount": float(row.get("成交额", 0)),
            "market_cap": float(row.get("总市值", 0)),
            "turnover": float(row.get("换手率", 0)),
            "rank": len(stocks) + 1,
            "sources": ["涨停板"],
        })

    logger.info(f"  {date}: {len(stocks)}只涨停")
    return stocks


def save_to_db(stocks: list[dict], date: str):
    """写入 stock.db hot_stocks 表。"""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute("DELETE FROM hot_stocks WHERE date = ?", (date,))
        for s in stocks:
            conn.execute(
                """INSERT INTO hot_stocks
                   (stock_code, stock_name, rank, price, change_pct, volume, amount,
                    turnover_rate, pe, market_cap, sources, date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    s["code"], s["name"], s["rank"],
                    s["price"], s["change_pct"],
                    0,  # volume
                    s["amount"], s["turnover"],
                    0,  # pe
                    s["market_cap"],
                    json.dumps(s.get("sources", ["涨停板"]), ensure_ascii=False),
                    date,
                ),
            )
        conn.commit()
        logger.info(f"  -> DB写入 {len(stocks)}条 ({date})")
    finally:
        conn.close()


def main():
    # 已有的日期（不覆盖）
    conn = sqlite3.connect(str(DB_PATH))
    existing = {r[0] for r in conn.execute("SELECT DISTINCT date FROM hot_stocks").fetchall()}
    conn.close()
    logger.info(f"现有日期: {sorted(existing)}")

    # 需要回补的日期 5/11 ~ 5/20
    start = datetime(2026, 5, 11)
    end = datetime(2026, 5, 20)
    dates = []
    d = start
    while d <= end:
        dates.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)

    fmt_dates = [d[:4] + "-" + d[4:6] + "-" + d[6:] for d in dates]
    missing = [d for d in fmt_dates if d not in existing]
    logger.info(f"需回补: {missing}")
    logger.info(f"跳过(已有): {sorted(set(fmt_dates) - set(missing))}")

    total = 0
    for date_str in missing:
        # akshare 需要 YYYYMMDD 格式
        api_date = date_str.replace("-", "")
        stocks = fetch_limit_up(api_date)
        if stocks:
            save_to_db(stocks, date_str)

        total += len(stocks)
        time.sleep(1.5)  # 避免触发风控

    # 同时更新 hot_stocks.json（最新日期）
    if missing:
        latest_date = fmt_dates[-1]
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute(
            "SELECT * FROM hot_stocks WHERE date = ? ORDER BY rank ASC LIMIT 30",
            (latest_date,),
        ).fetchall()
        conn.close()
        if rows:
            cols = ["id", "stock_code", "stock_name", "rank", "price", "change_pct",
                     "volume", "amount", "turnover_rate", "pe", "market_cap", "sources", "date"]
            top = [dict(zip(cols, r)) for r in rows]
            json_path = STOCK_DATA / "hot_stocks.json"
            json_path.write_text(
                json.dumps({"update_time": datetime.now().isoformat(), "top": top},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"hot_stocks.json 已更新 ({len(top)}条)")

    logger.info(f"完成: 共回补 {total} 条")


if __name__ == "__main__":
    main()
