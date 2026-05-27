"""
知识查询层 — 在 stock.db 上扩展，不依赖上下文加载即可检索记忆和存储

表结构:
  file_index      — stock_data JSON 文件索引 (路径/类型/关联股票/摘要)
  knowledge_entry — 记忆知识条目 (来源/分类/标签/内容片段)
  decision_log    — 分析/交易决策记录 (时间/股票/类型/结论/回顾)

使用:
  from knowledge_db import query_stock_history, search_knowledge, list_files
  files = list_files("000062")          # 所有关联某股票的文件
  decisions = query_stock_history("000062", days=30)  # 过去30天决策
  entries = search_knowledge("放量突破")  # 搜索相关知识
"""
import json
import sqlite3
import re
from pathlib import Path
from datetime import datetime
from contextlib import contextmanager
from config import DATABASE_PATH, STOCK_DATA_DIR

STOCK_DATA = Path(STOCK_DATA_DIR)
MEMORY_DIRS = [
    Path("D:/1989n/.claude/memory"),
    Path("D:/1989n/.claude/projects/d--1989n/memory"),
]


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


def init_knowledge_db():
    """初始化知识层表 (在已有 stock.db 上扩展)"""
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS file_index (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            file_type TEXT,           -- intraday_news/daily_analysis/closing_review/scan_result
            category TEXT,            -- news/analysis/portfolio/health
            created_at TEXT,          -- 文件时间戳
            size_bytes INTEGER,
            stock_codes TEXT,         -- JSON array of related stock codes
            headline TEXT,            -- 标题/摘要 (供检索)
            indexed_at TEXT           -- 索引时间
        );
        CREATE INDEX IF NOT EXISTS idx_file_type ON file_index(file_type);
        CREATE INDEX IF NOT EXISTS idx_file_created ON file_index(created_at);
        CREATE INDEX IF NOT EXISTS idx_file_stocks ON file_index(stock_codes);

        CREATE TABLE IF NOT EXISTS knowledge_entry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file TEXT,         -- 来源 md 文件路径
            topic TEXT,               -- 主题 (stock/strategy/psychology/rule)
            tags TEXT,                -- JSON array of tags
            content_snippet TEXT,     -- 关键内容片段 (前500字)
            created_at TEXT,
            updated_at TEXT,
            status TEXT DEFAULT 'active',  -- active/outdated/deprecated
            tier INTEGER DEFAULT 3,        -- L1=会话 L2=日频 L3=知识库 L4=规则
            access_count INTEGER DEFAULT 0, -- 访问次数，用于自动升降级
            last_accessed TEXT              -- 最后访问时间
        );
        CREATE INDEX IF NOT EXISTS idx_knowledge_topic ON knowledge_entry(topic);
        CREATE INDEX IF NOT EXISTS idx_knowledge_tags ON knowledge_entry(tags);

        CREATE TABLE IF NOT EXISTS decision_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            stock_code TEXT,
            stock_name TEXT,
            decision_type TEXT,       -- analysis/signal/buy/sell/hold/review
            summary TEXT,             -- 决策摘要
            confidence TEXT,          -- 置信度
            factors TEXT,             -- JSON array of factors considered
            outcome TEXT,             -- 结果 (事后填)
            review_notes TEXT         -- 回顾笔记 (事后填)
        );
        CREATE INDEX IF NOT EXISTS idx_decision_stock ON decision_log(stock_code);
        CREATE INDEX IF NOT EXISTS idx_decision_time ON decision_log(timestamp);
        CREATE INDEX IF NOT EXISTS idx_decision_type ON decision_log(decision_type);
        """)

        # 迁移：为已有表添加 tier/access_count 列
        _migrate_knowledge_entry(db)

        # 迁移后才建 tier 索引（旧表无 tier 列时 CREATE INDEX 会失败）
        try:
            db.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_tier ON knowledge_entry(tier)")
        except Exception:
            pass
        try:
            db.execute("CREATE INDEX IF NOT EXISTS idx_knowledge_access ON knowledge_entry(access_count)")
        except Exception:
            pass

    return True


def _migrate_knowledge_entry(db):
    """为已有 knowledge_entry 表添加 tier/access_count 列（幂等）。"""
    existing = [r["name"] for r in db.execute("PRAGMA table_info(knowledge_entry)").fetchall()]
    migrations = [
        ("tier", "ALTER TABLE knowledge_entry ADD COLUMN tier INTEGER DEFAULT 3"),
        ("access_count", "ALTER TABLE knowledge_entry ADD COLUMN access_count INTEGER DEFAULT 0"),
        ("last_accessed", "ALTER TABLE knowledge_entry ADD COLUMN last_accessed TEXT"),
    ]
    for col_name, sql in migrations:
        if col_name not in existing:
            try:
                db.execute(sql)
            except Exception:
                pass  # column may already exist despite PRAGMA


# ── file_index CRUD ───────────────────────────────────────────


def index_json_file(file_path: str) -> dict | None:
    """索引单个 JSON 文件，提取股票代码和标题。返回索引记录或 None"""
    path = Path(file_path)
    if not path.exists() or path.suffix != ".json":
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    # 推断 file_type
    fname = path.name
    if fname.startswith("news_intraday"):
        file_type = "intraday_news"
        category = "news"
    elif fname.startswith("news_evening"):
        file_type = "evening_news"
        category = "news"
    elif fname.startswith("news_morning") or fname.startswith("morning_enhanced"):
        file_type = "morning_news"
        category = "news"
    elif fname.startswith("news_manual"):
        file_type = "manual_news"
        category = "news"
    elif fname.startswith("news_flash"):
        file_type = "flash_news"
        category = "news"
    elif fname.startswith("morning_report"):
        file_type = "morning_news"
        category = "news"
    elif fname.startswith("intel_report"):
        file_type = "intel_report"
        category = "intelligence"
    elif fname.startswith("intel_data"):
        file_type = "intel_data"
        category = "intelligence"
    elif fname.startswith("research_"):
        file_type = "research"
        category = "intelligence"
    elif fname.startswith("closing_review") or fname.startswith("analysis_close"):
        file_type = "closing_review"
        category = "analysis"
    elif fname.startswith("analysis_overnight"):
        file_type = "overnight_analysis"
        category = "analysis"
    elif fname.startswith("analysis_30min"):
        file_type = "intraday_analysis"
        category = "analysis"
    elif fname.startswith("scan_"):
        file_type = "scan_result"
        category = "analysis"
    elif fname.startswith("call_auction"):
        file_type = "call_auction"
        category = "analysis"
    elif fname.startswith("emotional"):
        file_type = "emotional_data"
        category = "analysis"
    elif fname.startswith("monitor_"):
        file_type = "stock_monitor"
        category = "analysis"
    elif fname.startswith("sector_"):
        file_type = "sector_rank"
        category = "market_data"
    elif fname.startswith("hot_stocks"):
        file_type = "hot_stocks"
        category = "market_data"
    elif fname.startswith("health"):
        file_type = "health_check"
        category = "health"
    elif fname.startswith("bilibili_"):
        file_type = "bilibili_data"
        category = "other"
    else:
        file_type = "unknown"
        category = "other"

    # 提取股票代码
    stock_codes = _extract_stock_codes(data)

    # 提取标题
    headline = _extract_headline(data, fname)

    # 文件时间：优先从文件名提取，否则用文件修改时间
    ts_match = re.search(r"(\d{8})_?(\d{4})?", fname)
    if ts_match:
        created_at = f"{ts_match.group(1)} {ts_match.group(2) or '0000'}"
    else:
        created_at = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H%M")

    size_bytes = path.stat().st_size

    with get_db() as db:
        db.execute(
            """INSERT OR REPLACE INTO file_index
               (file_path, file_type, category, created_at, size_bytes, stock_codes, headline, indexed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(path), file_type, category, created_at, size_bytes,
             json.dumps(stock_codes, ensure_ascii=False), headline,
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        )

    return {"path": str(path), "type": file_type, "stocks": stock_codes, "headline": headline}


def _extract_stock_codes(data) -> list[str]:
    """从 JSON 数据中递归提取6位股票代码"""
    codes = set()
    text = json.dumps(data, ensure_ascii=False)

    # 精确匹配6位数字（A股代码）
    for m in re.finditer(r"\b(0[0-9]{5}|3[0-9]{5}|6[0-9]{5})\b", text):
        codes.add(m.group(1))

    # 也尝试从 "code"/"stock_code"/"symbol" 字段提取
    if isinstance(data, dict):
        for key in ("code", "stock_code", "symbol", "股票代码"):
            if key in data and isinstance(data[key], str) and re.match(r"^\d{6}$", data[key]):
                codes.add(data[key])
        # 递归检查 data 子字段
        if "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
                for key in ("code", "stock_code"):
                    if key in item and isinstance(item[key], str) and re.match(r"^\d{6}$", item[key]):
                        codes.add(item[key])

    return sorted(codes)


def _extract_headline(data, fname: str) -> str:
    """从 JSON 数据提取标题"""
    if isinstance(data, dict):
        for key in ("title", "headline", "name", "market_status"):
            if key in data and isinstance(data[key], str) and data[key].strip():
                return data[key][:200]
        # 取 type 字段
        if "type" in data and isinstance(data["type"], str):
            return data["type"][:200]
        # 取第一个有意义的 key-value
        for k, v in data.items():
            if isinstance(v, str) and len(v) > 3:
                return f"{k}: {v[:180]}"
    return fname


def list_files(stock_code: str = None, file_type: str = None,
               category: str = None, days: int = 30, limit: int = 50) -> list[dict]:
    """查询文件索引。可按股票代码/类型/分类/天数过滤"""
    conditions = []
    params = []

    if stock_code:
        conditions.append("stock_codes LIKE ?")
        params.append(f"%{stock_code}%")

    if file_type:
        conditions.append("file_type = ?")
        params.append(file_type)

    if category:
        conditions.append("category = ?")
        params.append(category)

    if days:
        conditions.append("created_at >= ?")
        params.append(f"{(datetime.now().strftime('%Y-%m-%d'))}-{days}")

    where = " AND ".join(conditions) if conditions else "1=1"
    query = f"SELECT * FROM file_index WHERE {where} ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    with get_db() as db:
        rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def file_index_stats() -> dict:
    """文件索引统计"""
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) as n FROM file_index").fetchone()["n"]
        by_type = db.execute(
            "SELECT file_type, COUNT(*) as n FROM file_index GROUP BY file_type ORDER BY n DESC"
        ).fetchall()
        latest = db.execute(
            "SELECT MAX(indexed_at) as t FROM file_index"
        ).fetchone()["t"]
    return {
        "total_files": total,
        "by_type": [dict(r) for r in by_type],
        "last_indexed": latest,
    }


# ── 记忆分层 CRUD ─────────────────────────────────────────────


def search_knowledge(query: str, topic: str = None, limit: int = 20) -> list[dict]:
    """搜索 knowledge_entry，同时更新访问计数用于自动升降级。"""
    conditions = ["status = 'active'"]
    params = []

    if topic:
        conditions.append("topic = ?")
        params.append(topic)

    # 搜索 content_snippet 和 tags
    conditions.append("(content_snippet LIKE ? OR tags LIKE ?)")
    params.append(f"%{query}%")
    params.append(f"%{query}%")

    where = " AND ".join(conditions)
    sql = f"SELECT * FROM knowledge_entry WHERE {where} ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
        results = [dict(r) for r in rows]

    # 更新访问计数（异步风格：不阻塞主路径）
    _bump_access([r["id"] for r in results])

    return results


def _bump_access(entry_ids: list[int]):
    """递增 knowledge_entry 的 access_count + 更新 last_accessed。"""
    if not entry_ids:
        return
    try:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as db:
            for eid in entry_ids:
                db.execute(
                    "UPDATE knowledge_entry SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                    (now, eid),
                )
    except Exception:
        pass  # non-critical, don't block reads


def auto_tier_promote(threshold: int = 5) -> dict:
    """自动升降级：访问次数达到 threshold 的 L3 条目升到 L2。

    L1=会话(瞬时) L2=日频(短期) L3=知识库(长期) L4=规则(持久)
    当前策略只做 L3→L2 升级（高频访问的知识值得更短刷新）。
    """
    counts = {"promoted": 0, "demoted": 0}
    try:
        with get_db() as db:
            # L3→L2: access_count >= threshold
            promoted = db.execute(
                "UPDATE knowledge_entry SET tier = 2, updated_at = ? "
                "WHERE status = 'active' AND tier = 3 AND access_count >= ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), threshold),
            )
            counts["promoted"] = promoted.rowcount

            # L2→L3: access_count < threshold / 2 and last_accessed older than 7 days
            demoted = db.execute(
                "UPDATE knowledge_entry SET tier = 3, updated_at = ? "
                "WHERE status = 'active' AND tier = 2 AND access_count < ? "
                "AND last_accessed < ?",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                 threshold // 2,
                 (datetime.now().strftime("%Y-%m-%d 00:00:00"))),
            )
            counts["demoted"] = demoted.rowcount
    except Exception as e:
        return {"error": str(e)}
    return counts


def index_memory_file(md_path: str) -> int:
    """索引单个 memory markdown 文件。返回提取的条目数"""
    path = Path(md_path)
    if not path.exists() or path.suffix != ".md":
        return 0

    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 0

    # 推断 topic — 文件名优先，目录次之
    fname_l = path.name.lower()
    pdir_l = str(path.parent).lower()

    if "feedback" in fname_l or "feedback" in pdir_l:
        topic = "feedback"
    elif "project" in fname_l or ("project" in pdir_l and "memory" in pdir_l):
        topic = "project"
    elif "readme" in fname_l or "index" in fname_l:
        topic = "tools"
    elif any(k in pdir_l for k in ("knowledge/stocks", "stocks")):
        topic = "stock"
    elif any(k in pdir_l for k in ("knowledge/economics", "economics")):
        topic = "economics"
    elif any(k in pdir_l for k in ("ai-method", "model", "agent")):
        topic = "ai-methods"
    elif any(k in pdir_l for k in ("tool", "claude", "code-setup", "setup")):
        topic = "tools"
    elif any(k in pdir_l for k in ("concept", "second-brain", "reading")):
        topic = "concept"
    else:
        topic = "general"

    # 提取 tags: 从 content 中的关键词
    tags = _extract_tags(content, topic)

    # 提取内容片段 (前500非空字符, 跳过 frontmatter)
    lines = content.split("\n")
    body_start = 0
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body_start = i + 1
                break
    body = " ".join(line.strip() for line in lines[body_start:] if line.strip())
    snippet = body[:500]

    if not snippet:
        return 0

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        # 先删除同源文件的旧条目
        db.execute("DELETE FROM knowledge_entry WHERE source_file = ?", (str(path),))
        db.execute(
            """INSERT INTO knowledge_entry
               (source_file, topic, tags, content_snippet, created_at, updated_at, status)
               VALUES (?, ?, ?, ?, ?, ?, 'active')""",
            (str(path), topic, json.dumps(tags, ensure_ascii=False),
             snippet, now, now),
        )

    return 1


def _extract_tags(content: str, topic: str) -> list[str]:
    """从内容中提取关键标签和股票代码"""
    tag_keywords = {
        "stock": ["量价", "突破", "支撑", "阻力", "放量", "缩量", "涨停", "跌停",
                   "趋势", "震荡", "反转", "背离", "均线", "MACD", "KDJ", "RSI",
                   "龙头", "补涨", "板块", "题材", "仓位", "止损", "止盈"],
        "economics": ["GDP", "CPI", "利率", "通胀", "周期", "货币政策", "财政政策"],
        "ai-methods": ["模型", "Agent", "推理", "学习", "优化", "进化"],
        "feedback": ["纠正", "规则", "错误", "成功", "学习", "改进", "验证"],
    }

    keywords = tag_keywords.get(topic, tag_keywords.get("stock", []))
    found = []
    for kw in keywords:
        if kw.lower() in content.lower():
            found.append(kw)

    # 提取A股股票代码 (6位数字，0/3/6开头) 作为标签
    import re
    stock_codes = re.findall(r"\b(0[0-9]{5}|3[0-9]{5}|6[0-9]{5})\b", content)
    found.extend(sorted(set(stock_codes)))

    return found[:20]


def search_knowledge(query: str, topic: str = None, limit: int = 20) -> list[dict]:
    """搜索 knowledge_entry"""
    conditions = ["status = 'active'"]
    params = []

    if topic:
        conditions.append("topic = ?")
        params.append(topic)

    # 搜索 content_snippet 和 tags
    conditions.append("(content_snippet LIKE ? OR tags LIKE ?)")
    params.append(f"%{query}%")
    params.append(f"%{query}%")

    where = " AND ".join(conditions)
    sql = f"SELECT * FROM knowledge_entry WHERE {where} ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    with get_db() as db:
        rows = db.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def list_knowledge_by_topic(topic: str, limit: int = 50) -> list[dict]:
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM knowledge_entry WHERE topic = ? AND status = 'active' "
            "ORDER BY updated_at DESC LIMIT ?",
            (topic, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def knowledge_stats() -> dict:
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) as n FROM knowledge_entry WHERE status='active'").fetchone()["n"]
        by_topic = db.execute(
            "SELECT topic, COUNT(*) as n FROM knowledge_entry WHERE status='active' GROUP BY topic ORDER BY n DESC"
        ).fetchall()
    return {"total_entries": total, "by_topic": [dict(r) for r in by_topic]}


# ── decision_log CRUD ─────────────────────────────────────────


def log_decision(stock_code: str, stock_name: str, decision_type: str,
                 summary: str, confidence: str = "", factors: list[str] = None) -> int:
    """记录一次分析/决策"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        cursor = db.execute(
            """INSERT INTO decision_log
               (timestamp, stock_code, stock_name, decision_type, summary, confidence, factors)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (now, stock_code, stock_name, decision_type, summary, confidence,
             json.dumps(factors or [], ensure_ascii=False)),
        )
        return cursor.lastrowid


def query_stock_history(stock_code: str, days: int = 30, limit: int = 20) -> list[dict]:
    """查询某只股票的决策历史"""
    from datetime import timedelta
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")
    with get_db() as db:
        rows = db.execute(
            """SELECT * FROM decision_log
               WHERE stock_code = ? AND timestamp >= ?
               ORDER BY timestamp DESC LIMIT ?""",
            (stock_code, cutoff, limit),
        ).fetchall()
    return [dict(r) for r in rows]


def add_outcome(decision_id: int, outcome: str, review_notes: str = ""):
    """事后补充决策结果"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as db:
        db.execute(
            "UPDATE decision_log SET outcome = ?, review_notes = ? WHERE id = ?",
            (outcome, review_notes, decision_id),
        )


# ── 便捷查询 ──────────────────────────────────────────────────


def quick_lookup(query: str, limit: int = 10) -> dict:
    """一键查询：同时搜索文件索引和知识条目"""
    return {
        "files": list_files(stock_code=query, limit=limit),
        "knowledge": search_knowledge(query, limit=limit),
        "decisions": query_stock_history(query, limit=limit),
    }


if __name__ == "__main__":
    init_knowledge_db()
    print("Knowledge DB initialized")
    print(f"DB path: {DATABASE_PATH}")
