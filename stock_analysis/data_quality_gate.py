"""
data_quality_gate.py — 发送前数据保鲜校验

所有输出（飞书/文件）在发送前必须经过 freshness_check。
过时数据 → 阻止发送 → 改发 STALE 告警。

用法:
    from data_quality_gate import freshness_check, preflight_scan
    result = freshness_check("hot_stocks.json", max_hours=6)
    if not result["pass"]:
        send_alert(f"数据过期: {result['file']} 已 {result['age_hours']:.0f}h")
"""

import json
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger("data_quality_gate")

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path("D:/1989n/stock_data")
PROJECT_DIR = Path(__file__).parent

# ── 文件路径映射（部分文件不在 stock_data/ 下）──
FILE_PATHS = {
    "portfolio.json": PROJECT_DIR / "data" / "portfolio.json",
    "concept_mapping.json": PROJECT_DIR / "data" / "concept_mapping.json",
}

# ── 各类数据的保鲜阈值 ──
FRESHNESS_RULES = {
    "portfolio.json": {"max_hours": 24, "severity": "critical"},
    "concept_mapping.json": {"max_hours": 48, "severity": "high"},
    "concept_stocks.json": {"max_hours": 48, "severity": "medium"},
    "stock_name_lookup.json": {"max_hours": 72, "severity": "low"},
    "hot_stocks.json": {"max_hours": 6, "severity": "medium"},  # 交易时段6h
    "morning_brief_latest.md": {"max_hours": 12, "severity": "medium"},
    "morning_brief_latest.json": {"max_hours": 12, "severity": "medium"},
    "closing_review.json": {"max_hours": 24, "severity": "medium"},
    "call_auction_latest.json": {"max_hours": 1, "severity": "low"},  # 集合竞价1h内有效
}


def freshness_check(filepath: Path, max_hours: Optional[float] = None,
                    severity: str = "medium") -> dict:
    """检查单个数据文件的时效性。

    Args:
        filepath: 数据文件路径
        max_hours: 最大允许时效（覆盖规则表）
        severity: 过期严重度（默认 medium）

    Returns:
        {"pass": bool, "file": str, "age_hours": float,
         "max_hours": float, "severity": str, "warning": str or None}
    """
    rel = filepath.name
    if max_hours is None:
        rule = FRESHNESS_RULES.get(rel, {})
        max_hours = rule.get("max_hours", 24)
        severity = rule.get("severity", severity)

    if not filepath.exists():
        return {
            "pass": False, "file": rel,
            "age_hours": -1, "max_hours": max_hours,
            "severity": "critical",
            "warning": f"{rel} 不存在",
        }

    mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=CST)
    age = datetime.now(CST) - mtime
    age_hours = age.total_seconds() / 3600

    if age_hours > max_hours:
        warning = f"{rel} 已 {age_hours:.1f}h 未更新 (阈值 {max_hours}h)"
        logger.warning(f"[STALE] {warning}")
        return {
            "pass": False, "file": rel,
            "age_hours": round(age_hours, 1),
            "max_hours": max_hours,
            "severity": severity,
            "warning": warning,
        }

    return {
        "pass": True, "file": rel,
        "age_hours": round(age_hours, 1),
        "max_hours": max_hours,
        "severity": severity,
        "warning": None,
    }


def preflight_scan(categories: Optional[list[str]] = None) -> dict:
    """扫描指定的数据文件列表，返回全面体检报告。

    Args:
        categories: 要检查的数据类别（默认全部）

    Returns:
        {"healthy": bool, "checks": [dict], "summary": str}
    """
    if categories is None:
        categories = list(FRESHNESS_RULES.keys())

    checks = []
    for rel in categories:
        # 优先使用自定义路径
        if rel in FILE_PATHS:
            fp = FILE_PATHS[rel]
        else:
            fp = STOCK_DATA / rel

        if not fp.exists():
            # 尝试用 glob 匹配（有些文件带时间戳后缀）
            matches = list(STOCK_DATA.glob(f"{rel}*"))
            if matches:
                fp = max(matches, key=lambda p: p.stat().st_mtime)
            else:
                checks.append({
                    "pass": False, "file": rel,
                    "age_hours": -1, "max_hours": 0,
                    "severity": "critical",
                    "warning": f"{rel} 不存在",
                })
                continue

        result = freshness_check(fp)
        checks.append(result)

    stale = [c for c in checks if not c["pass"]]
    healthy = len(stale) == 0

    if stale:
        summary = f"⚠ {len(stale)}/{len(checks)} 项数据过期"
        for s in stale:
            summary += f"\n  [{s['severity']}] {s['warning']}"
    else:
        summary = f"✓ {len(checks)}/{len(checks)} 项数据新鲜"

    return {"healthy": healthy, "checks": checks, "summary": summary}


def require_fresh(filepath: Path, max_hours: float, label: str = "") -> bool:
    """守卫函数：数据过期则阻止后续操作。

    Args:
        filepath: 数据文件路径
        max_hours: 最大允许时效
        label: 操作名称（用于日志）

    Returns:
        True=数据新鲜可继续, False=数据过期应阻止
    """
    result = freshness_check(filepath, max_hours=max_hours)
    if not result["pass"]:
        logger.error(f"[BLOCKED] {label}: {result['warning']}")
        return False
    return True
