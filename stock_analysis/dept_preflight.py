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

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path("D:/1989n/stock_data")
PREFLIGHT_LOG = STOCK_DATA / "status" / "preflight_report.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("preflight")


# ── 依赖定义 ───────────────────────────────────────────────────────────
# 以下从 stock_data/status/dependencies.json 加载
# 每个部门依赖的另一个部门（谁的状态需要检查）
# engineering 不依赖 front-office（独立运行）
# front-office 依赖 engineering（规则库验证）
_DEP_MAP_PATH = STOCK_DATA / "status" / "dependencies.json"

def _load_dependency_map() -> dict:
    """从 JSON 文件加载依赖映射。文件不存在时返回空字典。"""
    if not _DEP_MAP_PATH.exists():
        logger.warning("依赖映射文件不存在: %s", _DEP_MAP_PATH)
        return {}
    try:
        return json.loads(_DEP_MAP_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("加载依赖映射失败: %s", e)
        return {}

def _get_deps(dept: str) -> list[str]:
    """获取某部门的依赖列表。"""
    return _load_dependency_map().get(dept, [])

# 关键数据文件及其最大新鲜度（小时）
CRITICAL_DATA = {
    "front-office": [
        ("portfolio.json", 48),
        ("closing_review.json", 24),
        ("channel_health_latest.json", 2),
        ("sentinel_status.json", 24),
    ],
    "engineering": [
        ("_lint_history.json", 48),
    ],
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
        result["detail"] = f"{dept} 状态 degraded: {[i['message'] for i in issues[:3]]}"
        return result

    result["detail"] = f"{dept} 状态 healthy (更新于 {status.get('timestamp', '?')})"
    return result


def check_data_freshness(dept: str) -> list[dict]:
    """检查本部门依赖的数据文件。"""
    results = []
    files = CRITICAL_DATA.get(dept, [])

    for rel_path, max_hours in files:
        full_path = STOCK_DATA / rel_path
        entry = {
            "check": "data_freshness",
            "target": rel_path,
            "severity": "ok",
            "detail": "",
        }

        if not full_path.exists():
            entry["severity"] = "fail" if max_hours <= 24 else "advisory"
            entry["detail"] = f"{rel_path} 不存在"
            results.append(entry)
            continue

        mtime = datetime.fromtimestamp(full_path.stat().st_mtime, tz=CST)
        age_hours = (datetime.now(CST) - mtime).total_seconds() / 3600

        if age_hours > max_hours * 2:
            entry["severity"] = "fail"
            entry["detail"] = f"{rel_path} 过期 ({age_hours:.0f}h > {max_hours}h 阈值)"
        elif age_hours > max_hours:
            entry["severity"] = "advisory"
            entry["detail"] = f"{rel_path} 接近过期 ({age_hours:.0f}h, 阈值{max_hours}h)"
        else:
            entry["detail"] = f"{rel_path} 正常 (更新于{age_hours:.0f}h前)"

        results.append(entry)

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
    parser.add_argument("--dept", choices=["front-office", "engineering"], help="部门名称")
    parser.add_argument("--all", action="store_true", help="检查全部部门")
    args = parser.parse_args()

    if not args.dept and not args.all:
        parser.print_help()
        sys.exit(2)

    depts = ["front-office", "engineering"] if args.all else [args.dept]

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
