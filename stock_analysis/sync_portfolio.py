"""
持仓数据同步工具 — 调仓后执行，确保三路数据源一致
============================================
数据流: portfolio.json (唯一信源) → SQLite数据库 + 校验 concept_mapping.json

用法:
  python sync_portfolio.py          # 同步数据库（常规调仓后）
  python sync_portfolio.py --check  # 只校验不写入（定时巡检）
"""

from __future__ import annotations

import json
import logging
import sys
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("sync_portfolio")

# ── 路径 ──
PROJECT_DIR = Path(__file__).parent
PORTFOLIO_JSON = PROJECT_DIR / "data" / "portfolio.json"
DB_PATH = PROJECT_DIR.parent / "stock_data" / "stock.db"
CONCEPT_MAP = PROJECT_DIR.parent / "stock_data" / "concept_mapping.json"


def load_portfolio_json() -> list[dict]:
    """从 portfolio.json 加载当前持仓。"""
    if not PORTFOLIO_JSON.exists():
        logger.error(f"文件不存在: {PORTFOLIO_JSON}")
        sys.exit(1)
    try:
        data = json.loads(PORTFOLIO_JSON.read_text(encoding="utf-8"))
        holdings = data.get("holdings", [])
        if not holdings:
            logger.error("portfolio.json 中无持仓数据")
            sys.exit(1)
        return holdings
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"读取 portfolio.json 失败: {e}")
        sys.exit(1)


def sync_database(holdings: list[dict]) -> bool:
    """同步 portfolio.json → SQLite portfolio 表。"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("DELETE FROM portfolio")
        for h in holdings:
            conn.execute(
                "INSERT INTO portfolio (stock_code, shares, cost, sector, updated) VALUES (?, ?, ?, ?, ?)",
                (h["code"], h["shares"], h["cost"], h.get("sector", ""), "sync"),
            )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM portfolio").fetchone()[0]
        conn.close()
        logger.info(f"数据库同步成功: {count} 条持仓")
        return True
    except Exception as e:
        logger.error(f"数据库同步失败: {e}")
        return False


def check_concept_map(holdings: list[dict]) -> bool:
    """校验 concept_mapping.json 的持仓代码与 portfolio.json 一致。"""
    if not CONCEPT_MAP.exists():
        logger.warning(f"concept_mapping.json 不存在: {CONCEPT_MAP}")
        return False
    try:
        cm = json.loads(CONCEPT_MAP.read_text(encoding="utf-8"))
        cm_codes = set(cm.get("holdings", {}).keys())
        pf_codes = {h["code"] for h in holdings}
        missing = pf_codes - cm_codes
        extra = cm_codes - pf_codes
        if missing:
            logger.warning(f"concept_mapping.json 缺少持仓: {missing}")
        if extra:
            logger.warning(f"concept_mapping.json 有多余已清仓代码: {extra}")
        if not missing and not extra:
            logger.info("concept_mapping.json 持仓代码一致 ✅")
            return True
        return False
    except Exception as e:
        logger.error(f"校验 concept_mapping.json 失败: {e}")
        return False


def main():
    only_check = "--check" in sys.argv
    holdings = load_portfolio_json()

    codes = [h["code"] for h in holdings]
    logger.info(f"当前持仓 ({len(holdings)}只): {', '.join(codes)}")

    if only_check:
        logger.info("=== 校验模式 ===")
        db_ok = check_database(holdings)
        cm_ok = check_concept_map(holdings)
        if db_ok and cm_ok:
            logger.info("所有数据源一致 ✅")
        else:
            logger.warning("存在不一致，请运行 python sync_portfolio.py 修复")
    else:
        logger.info("=== 同步模式 ===")
        db_ok = sync_database(holdings)
        check_concept_map(holdings)
        if db_ok:
            logger.info("同步完成 ✅")
        else:
            logger.error("同步失败 ❌")
            sys.exit(1)


def check_database(holdings: list[dict]) -> bool:
    """校验数据库持仓与 portfolio.json 一致。"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        rows = conn.execute("SELECT stock_code, shares, cost FROM portfolio").fetchall()
        conn.close()
        db_map = {r[0]: {"shares": r[1], "cost": r[2]} for r in rows}
        pf_map = {h["code"]: {"shares": h["shares"], "cost": h["cost"]} for h in holdings}
        if db_map == pf_map:
            logger.info("数据库持仓一致 ✅")
            return True
        logger.warning("数据库持仓不一致")
        return False
    except Exception as e:
        logger.error(f"数据库校验失败: {e}")
        return False


if __name__ == "__main__":
    main()
