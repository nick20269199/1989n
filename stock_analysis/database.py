"""
数据库操作 - SQLite 存储/查询
"""
import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager
from config import DATABASE_PATH


@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        # ── schema_version 迁移机制 ──
        db.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)")
        row = db.execute("SELECT version FROM schema_version").fetchone()
        current_ver = row["version"] if row else 0

        if current_ver < 2:
            # V1→V2: l2_tick marker(TEXT) → trade_time(INTEGER)，旧数据作废
            db.execute("DROP TABLE IF EXISTS l2_tick")
            db.execute("DROP TABLE IF EXISTS l2_auction_summary")

        if current_ver < 3:
            # V2→V3: l2_auction_summary 增加 neutral_volume + has_directional 字段
            db.execute("DROP TABLE IF EXISTS l2_auction_summary")

        db.executescript("""
        CREATE TABLE IF NOT EXISTS stocks (
            code TEXT PRIMARY KEY,
            name TEXT,
            industry TEXT,
            market TEXT,
            list_date TEXT
        );
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT,
            shares INTEGER,
            cost REAL,
            sector TEXT,
            updated TEXT
        );
        CREATE TABLE IF NOT EXISTS market_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT,
            date TEXT,
            price REAL,
            change_pct REAL,
            volume REAL,
            amount REAL,
            turnover_rate REAL,
            pe REAL,
            market_cap REAL
        );
        CREATE TABLE IF NOT EXISTS hot_stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT,
            stock_name TEXT,
            rank INTEGER,
            price REAL,
            change_pct REAL,
            volume REAL,
            amount REAL,
            turnover_rate REAL,
            pe REAL,
            market_cap REAL,
            sources TEXT,
            date TEXT
        );
        CREATE TABLE IF NOT EXISTS news (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            source TEXT,
            url TEXT,
            sentiment TEXT,
            related_stocks TEXT,
            category TEXT,
            pub_time TEXT,
            collected_at TEXT
        );
        CREATE TABLE IF NOT EXISTS financials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT,
            report_period TEXT,
            report_type TEXT,
            data_json TEXT,
            collected_at TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_market_data_code_date ON market_data(stock_code, date);
        CREATE INDEX IF NOT EXISTS idx_news_pub_time ON news(pub_time);
        CREATE INDEX IF NOT EXISTS idx_news_related ON news(related_stocks);
        CREATE INDEX IF NOT EXISTS idx_hot_stocks_date ON hot_stocks(date);
        CREATE TABLE IF NOT EXISTS auction_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            date TEXT NOT NULL,
            auction_price REAL,
            prev_close REAL,
            auction_chg_pct REAL,
            open_volume REAL,
            UNIQUE(stock_code, date)
        );
        CREATE INDEX IF NOT EXISTS idx_auction_code_date ON auction_history(stock_code, date);
        CREATE TABLE IF NOT EXISTS l2_tick (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stock_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            trade_time INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            price REAL,
            volume INTEGER,
            direction INTEGER,
            UNIQUE(stock_code, trade_date, trade_time, seq)
        );
        CREATE INDEX IF NOT EXISTS idx_l2_tick_code_date ON l2_tick(stock_code, trade_date);
        CREATE TABLE IF NOT EXISTS l2_auction_summary (
            stock_code TEXT NOT NULL,
            trade_date TEXT NOT NULL,
            auction_price REAL,
            buy_volume INTEGER,
            sell_volume INTEGER,
            neutral_volume INTEGER,
            net_flow INTEGER,
            buy_ratio REAL,
            vwap REAL,
            tick_count INTEGER,
            depth_snapshot_count INTEGER,
            has_directional INTEGER DEFAULT 1,
            UNIQUE(stock_code, trade_date)
        );
        CREATE INDEX IF NOT EXISTS idx_l2_summary_code_date ON l2_auction_summary(stock_code, trade_date);
        CREATE TABLE IF NOT EXISTS l2_sync_state (
            stock_code TEXT NOT NULL,
            file_mtime REAL NOT NULL,
            last_sync TEXT NOT NULL,
            UNIQUE(stock_code)
        );
        """)
        if current_ver < 3:
            db.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (3)")
    return True


def save_portfolio(holdings: list[dict]):
    """保存持仓到数据库"""
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute("DELETE FROM portfolio")
        for h in holdings:
            db.execute(
                "INSERT INTO portfolio (stock_code, shares, cost, sector, updated) VALUES (?, ?, ?, ?, ?)",
                (h["code"], h["shares"], h["cost"], h.get("sector", ""), today),
            )


def get_portfolio() -> list[dict]:
    with get_db() as db:
        rows = db.execute("SELECT * FROM portfolio").fetchall()
    return [dict(r) for r in rows]


def save_market_data(data: list[dict]):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as db:
        for d in data:
            db.execute(
                """INSERT OR REPLACE INTO market_data
                   (stock_code, date, price, change_pct, volume, amount, turnover_rate, pe, market_cap)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (d["code"], today, d.get("price"), d.get("change_pct"),
                 d.get("volume"), d.get("amount"), d.get("turnover_rate"),
                 d.get("pe"), d.get("market_cap")),
            )


def save_news(news_items: list[dict]):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        for n in news_items:
            db.execute(
                "INSERT INTO news (title, source, url, sentiment, related_stocks, category, pub_time, collected_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (n["title"], n.get("source", ""), n.get("url", ""),
                 n.get("sentiment", ""), n.get("related_stocks", ""),
                 n.get("category", ""), n.get("pub_time", ""), now),
            )


def save_hot_stocks(stocks: list[dict]):
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as db:
        db.execute("DELETE FROM hot_stocks WHERE date = ?", (today,))
        for s in stocks:
            db.execute(
                """INSERT INTO hot_stocks
                   (stock_code, stock_name, rank, price, change_pct, volume, amount,
                    turnover_rate, pe, market_cap, sources, date)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (s["code"], s.get("name", ""), s.get("rank"), s.get("price"),
                 s.get("change_pct"), s.get("volume"), s.get("amount"),
                 s.get("turnover_rate"), s.get("pe"), s.get("market_cap"),
                 json.dumps(s.get("sources", []), ensure_ascii=False), today),
            )


def get_recent_news(hours: int = 24, limit: int = 100) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM news WHERE collected_at > datetime('now', ?) ORDER BY pub_time DESC LIMIT ?",
            (f"-{hours} hours", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def get_market_history(code: str, days: int = 60) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM market_data WHERE stock_code = ? ORDER BY date DESC LIMIT ?",
            (code, days),
        ).fetchall()
    return [dict(r) for r in rows]


# ── 竞价数据 ─────────────────────────────────────────────────────


def save_auction_data(portfolio_auction: list[dict]):
    """保存持仓竞价数据到 auction_history 表。"""
    today = datetime.now().strftime("%Y-%m-%d")
    with get_db() as db:
        for p in portfolio_auction:
            db.execute(
                """INSERT OR REPLACE INTO auction_history
                   (stock_code, date, auction_price, prev_close, auction_chg_pct, open_volume)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (p["code"], today,
                 p.get("auction_price"), p.get("prev_close"),
                 p.get("auction_chg_pct"), p.get("open_volume")),
            )


def get_auction_history(code: str, days: int = 20) -> list[dict]:
    """获取某只股票过去N天的竞价历史。"""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM auction_history WHERE stock_code = ? ORDER BY date DESC LIMIT ?",
            (code, days),
        ).fetchall()
    return [dict(r) for r in rows]


def check_auction_volume_signal(code: str, name: str = "",
                                multiplier: float = 1.5,
                                min_days: int = 5) -> dict:
    """
    判断今日竞价是否放量。

    Args:
        code: 股票代码
        name: 股票名称（仅用于返回信息）
        multiplier: 放量阈值，今日量 >= 基线 × multiplier 视为放量
        min_days: 最少需要多少天历史数据

    Returns:
        dict: {code, name, signal, today_volume, avg_volume, ratio, days}
        signal: "放量" / "缩量" / "数据不足"
    """
    rows = get_auction_history(code, days=20)
    if not rows:
        return {"code": code, "name": name, "signal": "数据不足",
                "today_volume": 0, "avg_volume": 0, "ratio": 0, "days": 0}

    today_vol = rows[0].get("open_volume", 0) or 0
    past = [r.get("open_volume", 0) or 0 for r in rows[1:] if (r.get("open_volume") or 0) > 0]
    days = len(past)

    if days < min_days or not past:
        return {"code": code, "name": name, "signal": "数据不足",
                "today_volume": today_vol, "avg_volume": 0, "ratio": 0, "days": days}

    avg_vol = sum(past) / days
    ratio = today_vol / avg_vol if avg_vol > 0 else 0
    if ratio >= multiplier:
        signal = "放量"
    elif ratio <= 1 / multiplier:
        signal = "缩量"
    else:
        signal = "正常"

    return {"code": code, "name": name, "signal": signal,
            "today_volume": today_vol, "avg_volume": round(avg_vol),
            "ratio": round(ratio, 2), "days": days}


def batch_check_auction_volume(portfolio_auction: list[dict],
                               multiplier: float = 1.5) -> list[dict]:
    """批量检查所有持仓的竞价放量信号。"""
    return [
        check_auction_volume_signal(p["code"], p.get("name", ""), multiplier)
        for p in portfolio_auction
    ]


# ── L2 逐笔成交 ─────────────────────────────────────────────────


def save_l2_tick(code: str, trade_date: str, records: list[dict]):
    """批量写入 L2 逐笔成交记录。"""
    with get_db() as db:
        db.execute("DELETE FROM l2_tick WHERE stock_code = ? AND trade_date = ?",
                   (code, trade_date))
        db.executemany(
            """INSERT OR REPLACE INTO l2_tick
               (stock_code, trade_date, trade_time, seq, price, volume, direction)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [(code, trade_date, r["trade_time"], r["seq"],
              r["price"], r["volume"], r["direction"]) for r in records],
        )


def save_l2_auction_summary(code: str, trade_date: str, summary: dict):
    """写入 L2 竞价摘要。"""
    with get_db() as db:
        db.execute(
            """INSERT OR REPLACE INTO l2_auction_summary
               (stock_code, trade_date, auction_price, buy_volume, sell_volume,
                neutral_volume, net_flow, buy_ratio, vwap, tick_count,
                depth_snapshot_count, has_directional)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, trade_date, summary["auction_price"], summary["buy_volume"],
             summary["sell_volume"], summary.get("neutral_volume", 0),
             summary["net_flow"], summary["buy_ratio"],
             summary["vwap"], summary["tick_count"], summary["depth_snapshot_count"],
             1 if summary.get("has_directional") else 0),
        )


def get_l2_auction_summary(code: str, days: int = 20) -> list[dict]:
    """获取某只股票过去 N 天的 L2 竞价摘要。"""
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM l2_auction_summary WHERE stock_code = ? "
            "ORDER BY trade_date DESC LIMIT ?",
            (code, days),
        ).fetchall()
    return [dict(r) for r in rows]


def get_l2_sync_state(code: str) -> float | None:
    """获取上次同步时的文件 mtime，用于增量检测。"""
    with get_db() as db:
        row = db.execute(
            "SELECT file_mtime FROM l2_sync_state WHERE stock_code = ?",
            (code,),
        ).fetchone()
    return row["file_mtime"] if row else None


def set_l2_sync_state(code: str, file_mtime: float, sync_time: str):
    """记录本次同步的文件 mtime。"""
    with get_db() as db:
        db.execute(
            "INSERT OR REPLACE INTO l2_sync_state (stock_code, file_mtime, last_sync) "
            "VALUES (?, ?, ?)",
            (code, file_mtime, sync_time),
        )


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DATABASE_PATH}")
