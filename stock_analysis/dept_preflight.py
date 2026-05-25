"""
dept_preflight.py — 跨部门预检 v1

在部门操作前运行。验证：
  - 此部门的依赖关系是否健康（读取其他部门状态）
  - 所依赖的数据是否存在且新鲜
  - 跨部门是否存在可能导致静默故障的问题

用法:
  python dept_preflight.py --dept front-office  检查前厅部可否运行
  python dept_preflight.py --dept engineering    检查工程部可否运行
  python dept_preflight.py --all                 检查全部（健康检查用）

退出码: 0=全部OK  1=有注意事项  2=阻塞（建议中止）
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from dept_status_protocol import read_other_dept, is_status_fresh
from data_quality_gate import preflight_scan, FRESHNESS_RULES

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path("D:/1989n/stock_data")
PREFLIGHT_LOG = STOCK_DATA / "status" / "preflight_report.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("preflight")


# ── 依赖定义 ───────────────────────────────────────────────────────────
_DEP_MAP_PATH = STOCK_DATA / "status" / "dependencies.json"

def _load_dependency_map() -> dict:
    if not _DEP_MAP_PATH.exists():
        logger.warning("依赖映射文件不存在: %s", _DEP_MAP_PATH)
        return {}
    try:
        return json.loads(_DEP_MAP_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("加载依赖映射失败: %s", e)
        return {}

def _get_deps(dept: str) -> list[str]:
    return _load_dependency_map().get(dept, [])

# 部门数据文件映射 — 文件名列表, 阈值从 FRESHNESS_RULES 统一获取
DEPT_DATA_FILES = {
    "front-office": ["portfolio.json", "closing_review.json", "channel_health_latest.json", "sentinel_status.json"],
    "engineering": ["_lint_history.json"],
    "intelligence": ["intel/intel_latest.json"],
    "logistics": ["task_dashboard.md", "news_manual_*.json"],
}


# ── 检查函数 ───────────────────────────────────────────────────────────

def check_other_dept_status(dept: str) -> dict:
    """检查被依赖部门的状态。"""
    result = {"check": "other_dept_status", "target": dept, "severity": "ok", "detail": ""}

    status = read_other_dept(dept)
    if status is None:
        result["severity"] = "advisory"
        result["detail"] = f"{dept} 状态不存在 — 可能尚未运行过"
        return result

    health = status.get("health", "unknown")
    if health == "critical":
        result["severity"] = "fail"
        result["detail"] = f"{dept} 状态为 critical: {status.get('issues', [])}"
        return result

    if not is_status_fresh(status, max_hours=24):
        result["severity"] = "advisory"
        result["detail"] = f"{dept} 状态超过24小时未更新 (上次: {status.get('timestamp', '?')})"
        return result

    if health == "degraded":
        result["severity"] = "advisory"
        issues = status.get("issues", [])
        # issues 可能是字符串列表或字典列表，统一处理
        issue_texts = [i.get("message", str(i)) if isinstance(i, dict) else str(i) for i in issues[:3]]
        result["detail"] = f"{dept} 状态 degraded: {issue_texts}"
        return result

    result["detail"] = f"{dept} 状态 healthy (更新于 {status.get('timestamp', '?')})"
    return result


def check_data_freshness(dept: str) -> list[dict]:
    """检查本部门依赖的数据文件 (通过 data_quality_gate.preflight_scan)。"""
    files = DEPT_DATA_FILES.get(dept, [])
    if not files:
        return []

    scan = preflight_scan(files)
    results = []
    for check in scan["checks"]:
        age = check["age_hours"]
        max_h = check["max_hours"]
        if age < 0:
            severity = "fail" if max_h <= 24 else "advisory"
            detail = f"{check['file']} 不存在"
        elif age > max_h * 2:
            severity = "fail"
            detail = f"{check['file']} 过期 ({age:.0f}h > {max_h}h 阈值)"
        elif age > max_h:
            severity = "advisory"
            detail = f"{check['file']} 接近过期 ({age:.0f}h, 阈值{max_h}h)"
        else:
            severity = "ok"
            detail = f"{check['file']} 正常 (更新于{age:.0f}h前)"
        results.append({
            "check": "data_freshness", "target": check["file"],
            "severity": severity, "detail": detail,
        })
    return results


def check_dependency_cycle() -> dict:
    """检测依赖图是否有循环（A等B, B等A）。"""
    result = {"check": "dependency_cycle", "severity": "ok", "detail": "无循环依赖"}

    dep_map = _load_dependency_map()
    all_depts = list(dep_map.keys())
    for dept in all_depts:
        visited = set()
        queue = [dept]
        while queue:
            current = queue.pop(0)
            if current in visited:
                result["severity"] = "fail"
                result["detail"] = f"检测到循环依赖: {dept} → ... → {current}"
                return result
            visited.add(current)
            for dep in dep_map.get(current, []):
                if dep in all_depts:
                    queue.append(dep)

    return result


# ── 报告生成 ───────────────────────────────────────────────────────────

def run_preflight(dept: str) -> dict:
    """执行指定部门的预检，返回报告 dict。"""
    checks = []

    # 1) 依赖循环检测
    cycle_check = check_dependency_cycle()
    checks.append(cycle_check)
    if cycle_check["severity"] == "fail":
        return _build_report(dept, checks)

    # 2) 被依赖部门状态检查
    for dep in _get_deps(dept):
        checks.append(check_other_dept_status(dep))

    # 3) 数据文件新鲜度
    checks.extend(check_data_freshness(dept))

    return _build_report(dept, checks)


def _build_report(dept: str, checks: list[dict]) -> dict:
    """汇总检查结果，判断整体状态。"""
    fail_count = sum(1 for c in checks if c["severity"] == "fail")
    advisory_count = sum(1 for c in checks if c["severity"] == "advisory")

    if fail_count > 0:
        overall = "blocking"
    elif advisory_count > 0:
        overall = "advisory"
    else:
        overall = "pass"

    report = {
        "timestamp": datetime.now(CST).isoformat(),
        "checking_for": dept,
        "overall": overall,
        "checks": checks,
        "blocking": fail_count > 0,
        "fail_count": fail_count,
        "advisory_count": advisory_count,
    }

    return report


def print_report(report: dict):
    """人可读的输出。"""
    icon = {"pass": "✅", "advisory": "⚠️", "blocking": "⛔"}
    print(f"\n{'='*50}")
    print(f"  预检报告 — {report['checking_for']}")
    print(f"  状态: {icon.get(report['overall'], '?')} {report['overall']}")
    print(f"{'='*50}")

    for c in report["checks"]:
        sev_icon = {"ok": "✅", "advisory": "⚠️", "fail": "⛔"}.get(c["severity"], "⚪")
        print(f"  {sev_icon} [{c['check']}] {c.get('target', '')}")
        print(f"    {c['detail']}")

    print(f"\n  阻塞: {report['fail_count']}项  注意事项: {report['advisory_count']}项")
    print(f"{'='*50}\n")


def main():
    parser = argparse.ArgumentParser(description="跨部门预检")
    parser.add_argument("--dept", choices=["front-office", "engineering", "intelligence", "logistics"], help="部门名称")
    parser.add_argument("--all", action="store_true", help="检查全部部门")
    args = parser.parse_args()

    if not args.dept and not args.all:
        parser.print_help()
        sys.exit(2)

    depts = ["front-office", "engineering", "intelligence", "logistics"] if args.all else [args.dept]

    all_reports = []
    overall_blocking = False
    for dept in depts:
        report = run_preflight(dept)
        all_reports.append(report)
        print_report(report)
        if report["blocking"]:
            overall_blocking = True

    # 写入 JSON
    combined = {
        "timestamp": datetime.now(CST).isoformat(),
        "reports": all_reports,
        "overall_blocking": overall_blocking,
    }
    try:
        PREFLIGHT_LOG.parent.mkdir(parents=True, exist_ok=True)
        PREFLIGHT_LOG.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning("预检报告写入失败: %s", e)

    # 退出码
    if overall_blocking:
        sys.exit(2)
    elif any(r["advisory_count"] > 0 for r in all_reports):
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
