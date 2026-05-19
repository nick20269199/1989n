"""
dept_status_protocol.py — 跨部门状态协议 v1

每个部门写入 stock_data/status/{dept}_status.json，其他部门读取。
文件协议，不是服务。无外部依赖。

API:
  publish_status(dept_name, status_dict)  → 写入状态文件
  read_status(dept_name)                  → 读自身状态
  read_other_dept(dept_name)              → 读别的部门状态, 缺失返回 None
  get_recent_issues(dept_name)            → 获取某部门最近 issue 列表
"""

import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path("D:/1989n/stock_data")
STATUS_DIR = STOCK_DATA / "status"

logger = logging.getLogger("dept-status")


def _ensure_dir():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _status_path(dept_name: str) -> Path:
    return STATUS_DIR / f"{dept_name}_status.json"


def publish_status(dept_name: str, status_dict: dict) -> bool:
    """写入部门状态文件。自动注入 timestamp。"""
    _ensure_dir()
    record = {
        "department": dept_name,
        "timestamp": datetime.now(CST).isoformat(),
        **status_dict,
    }
    path = _status_path(dept_name)
    try:
        path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("[dept-status] %s → %s 已发布 (health=%s)", dept_name, path, record.get("health", "?"))
        return True
    except Exception as e:
        logger.error("[dept-status] %s 状态写入失败: %s", dept_name, e)
        return False


def read_status(dept_name: str) -> dict:
    """读取本部门状态。缺失 → 返回默认 dict。"""
    path = _status_path(dept_name)
    if not path.exists():
        return {"department": dept_name, "health": "unknown", "timestamp": None}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("[dept-status] %s 状态读取失败: %s", dept_name, e)
        return {"department": dept_name, "health": "corrupted", "timestamp": None}


def read_other_dept(dept_name: str) -> Optional[dict]:
    """读取别的部门状态。缺失/损坏 → 返回 None（不阻塞调用方）。"""
    path = _status_path(dept_name)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, Exception) as e:
        logger.warning("[dept-status] 读取 %s 状态失败: %s", dept_name, e)
        return None


def get_recent_issues(dept_name: str) -> list[dict]:
    """获取某部门最近的 issues 列表。"""
    status = read_other_dept(dept_name)
    if not status:
        return []
    return status.get("issues", [])


def is_status_fresh(status: Optional[dict], max_hours: int = 24) -> bool:
    """检查状态是否在指定小时内更新。"""
    if not status or not status.get("timestamp"):
        return False
    try:
        ts = datetime.fromisoformat(status["timestamp"])
        now = datetime.now(CST)
        return (now - ts).total_seconds() < max_hours * 3600
    except Exception:
        return False


if __name__ == "__main__":
    # CLI test
    dept = sys.argv[1] if len(sys.argv) > 1 else "engineering"
    s = read_other_dept(dept)
    if s:
        print(json.dumps(s, ensure_ascii=False, indent=2))
    else:
        print(f"[dept-status] {dept}: 无状态文件")
