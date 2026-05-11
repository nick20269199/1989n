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
        """)
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


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DATABASE_PATH}")
