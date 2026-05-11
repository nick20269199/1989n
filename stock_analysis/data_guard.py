#!D:/Python314/python
"""
Data Guard v1.0 — 数据完整性警卫
================================
每次健康检查时运行，验证 stock_data/ 下所有 JSON/CSV 文件完整性。
检测: JSON损坏、文件空白、关键文件缺失、数据过期
"""

from error_capture import trap; trap()

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path(r"D:\1989n\stock_data")
REPORT_PATH = STOCK_DATA / "data_guard_report.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("data-guard")

# ── 关键文件（缺失立刻告警）──
CRITICAL_FILES = [
    "concept_mapping.json",
    "closing_review.json",
    "learning/rules.json",
    "learning/ratio_baselines.json",
    "learning/daily_digest_index.json",
    "morning_brief_latest.md",
]

# ── 过期阈值 ──
STALE_HOURS = {
    "closing_review.json": 24,       # 交易日收盘后必更新
    "news_manual_": 12,              # 早间新闻12小时内
    "morning_brief_latest.md": 12,   # 早间简报12小时内
}


def is_stale(filepath: Path, max_hours: int) -> bool:
    """判断文件是否过期。"""
    if not filepath.exists():
        return True
    mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=CST)
    age = datetime.now(CST) - mtime
    return age > timedelta(hours=max_hours)


def check_json_valid(filepath: Path) -> tuple[bool, str]:
    """验证 JSON 文件是否可正确解析。"""
    try:
        text = filepath.read_text(encoding="utf-8")
        if not text.strip():
            return False, "empty file"
        json.loads(text)
        return True, "ok"
    except json.JSONDecodeError as e:
        return False, f"JSON error: {e}"
    except UnicodeDecodeError as e:
        return False, f"encoding error: {e}"
    except Exception as e:
        return False, str(e)


def scan_all_json() -> list[dict]:
    """扫描 stock_data/ 下所有 JSON 文件。"""
    issues = []
    for fpath in STOCK_DATA.rglob("*.json"):
        if "models" in str(fpath) or fpath.stat().st_size < 2:
            continue
        valid, msg = check_json_valid(fpath)
        if not valid:
            issues.append({"file": str(fpath.relative_to(STOCK_DATA)), "issue": msg, "severity": "high"})
    return issues


def check_critical() -> list[dict]:
    """检查关键文件是否存在且非空。"""
    issues = []
    for rel in CRITICAL_FILES:
        fpath = STOCK_DATA / rel
        if not fpath.exists():
            issues.append({"file": rel, "issue": "missing", "severity": "critical"})
        elif fpath.stat().st_size < 10:
            issues.append({"file": rel, "issue": "empty", "severity": "critical"})
    return issues


def check_staleness() -> list[dict]:
    """检查关键文件是否过期。"""
    issues = []
    for pattern, hours in STALE_HOURS.items():
        for fpath in STOCK_DATA.glob(f"{pattern}*"):
            if is_stale(fpath, hours):
                age = datetime.now(CST) - datetime.fromtimestamp(fpath.stat().st_mtime, tz=CST)
                issues.append({
                    "file": str(fpath.relative_to(STOCK_DATA)),
                    "issue": f"stale ({age.total_seconds()/3600:.1f}h > {hours}h threshold)",
                    "severity": "medium",
                })
    return issues


def run():
    """主巡检。"""
    now = datetime.now(CST)
    logger.info(f"Data Guard scanning at {now.strftime('%H:%M')}")

    report = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "json_issues": scan_all_json(),
        "critical_issues": check_critical(),
        "stale_issues": check_staleness(),
    }

    total = len(report["json_issues"]) + len(report["critical_issues"]) + len(report["stale_issues"])
    report["total_issues"] = total
    report["healthy"] = total == 0

    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if total:
        logger.warning(f"Issues found: {total}")
        for cat in ["critical_issues", "json_issues", "stale_issues"]:
            for issue in report[cat]:
                logger.warning(f"  [{issue['severity']}] {issue['file']}: {issue['issue']}")
    else:
        logger.info("All data files healthy")

    return report


if __name__ == "__main__":
    run()
