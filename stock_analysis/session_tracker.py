"""
会话追踪层 — 记录 Claude Code 会话的起止时间和报错次数

只做一件事: session_log 表 → 知道什么时候做了什么会话，报了什么错。
不做的事: 决策追踪(用 decision_log)、学习沉淀(用 memory/)、文件变更(用 git log)
"""
import sqlite3
import uuid
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


def init_session_tracker():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS session_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE,
            started_at TEXT,
            ended_at TEXT,
            status TEXT DEFAULT 'active',
            error_count INTEGER DEFAULT 0,
            errors_text TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_session_status ON session_log(status);
        CREATE INDEX IF NOT EXISTS idx_session_started ON session_log(started_at);
        """)
    return True


def start_session() -> str:
    sid = datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        # 先关掉所有旧 active session (防止崩溃遗留的僵尸)
        db.execute(
            "UPDATE session_log SET ended_at = ?, status = 'zombie' WHERE status = 'active'",
            (now,),
        )
        db.execute(
            "INSERT INTO session_log (session_id, started_at, status) VALUES (?, ?, 'active')",
            (sid, now),
        )
    return sid


def end_session(session_id: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute(
            "UPDATE session_log SET ended_at = ?, status = 'closed' WHERE session_id = ?",
            (now, session_id),
        )


def record_error(summary: str, detail: str = "") -> str:
    """便捷入口: 记录错误到当前活跃 session (无活跃则自动创建)"""
    session = get_active_session()
    sid = session["session_id"] if session else start_session()
    now = datetime.now().strftime("%H:%M:%S")
    line = f"[{now}] {summary}"
    with get_db() as db:
        db.execute(
            "UPDATE session_log SET error_count = COALESCE(error_count,0) + 1, "
            "errors_text = COALESCE(errors_text,'') || ? || x'0a' WHERE session_id = ?",
            (line, sid),
        )
    return sid


def get_active_session() -> dict | None:
    with get_db() as db:
        row = db.execute(
            "SELECT * FROM session_log WHERE status = 'active' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def list_sessions(days: int = 7, limit: int = 20) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM session_log WHERE started_at >= date('now', ?) "
            "ORDER BY started_at DESC LIMIT ?",
            (f"-{days} days", limit),
        ).fetchall()
    return [dict(r) for r in rows]


def session_stats(days: int = 30) -> dict:
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) as n FROM session_log").fetchone()["n"]
        active = db.execute(
            "SELECT COUNT(*) as n FROM session_log WHERE status='active'"
        ).fetchone()["n"]
        zombie = db.execute(
            "SELECT COUNT(*) as n FROM session_log WHERE status='zombie'"
        ).fetchone()["n"]
        recent = db.execute(
            "SELECT COUNT(*) as n FROM session_log WHERE started_at >= date('now', ?)",
            (f"-{days} days",),
        ).fetchone()["n"]
        total_errors = db.execute(
            "SELECT COALESCE(SUM(error_count),0) as n FROM session_log"
        ).fetchone()["n"]
    return {
        "total_sessions": total,
        "active_sessions": active,
        "zombie_sessions": zombie,
        "sessions_last_30d": recent,
        "total_errors_logged": total_errors,
    }


if __name__ == "__main__":
    init_session_tracker()
    print("Session tracker (lean) initialized")
    print(f"DB: {DATABASE_PATH}")

    sid = start_session()
    print(f"Started: {sid}")

    record_error(sid, "测试报错: 连接超时")
    record_error(sid, "测试报错: 数据为空")
    print(f"Recorded 2 errors")

    end_session(sid)
    print(f"Closed: {sid}")
    print(f"Stats: {session_stats()}")
