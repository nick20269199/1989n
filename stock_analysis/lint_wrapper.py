"""
lint_wrapper.py — 工程部 Lint 包装器

在 sel_lint.py 执行完成后，将扫描结果发布到部门状态协议。
只做两件事：运行 sel_lint、发布状态。不修改 sel_lint 的任何逻辑。
"""

import json
import logging
import sys
from datetime import date
from pathlib import Path

from dept_status_protocol import publish_status, read_other_dept

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lint-wrapper")

HISTORY_PATH = Path("D:/1989n/.claude/memory/daily/_lint_history.json")


def _get_today_lint_entry() -> dict | None:
    """从 _lint_history.json 读取今日的扫描结果。"""
    if not HISTORY_PATH.exists():
        return None
    try:
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        today = date.today().isoformat()
        for entry in history:
            if entry.get("date") == today:
                return entry
        return None
    except Exception as e:
        logger.warning("读取 _lint_history.json 失败: %s", e)
        return None


def main():
    # 1) 运行 sel_lint（捕获它的 sys.exit）
    try:
        import sel_lint
        sel_lint.main()
    except SystemExit:
        pass  # sel_lint 的终止码由调度器处理，这里不关心
    except Exception as e:
        logger.error("sel_lint 执行异常: %s", e)
        publish_status("engineering", {
            "health": "critical",
            "pipeline": {"lint": {"status": "error", "error": str(e)[:200]}},
            "issues": [{"area": "sel_lint", "severity": "high", "message": str(e)[:200]}],
        })
        sys.exit(2)

    # 2) 读取今日结果
    entry = _get_today_lint_entry()
    if not entry:
        logger.warning("未找到今日 Lint 记录")
        publish_status("engineering", {
            "health": "degraded",
            "pipeline": {"lint": {"status": "completed", "note": "Lint 运行完成但未找到历史记录"}},
            "issues": [{"area": "lint_wrapper", "severity": "medium",
                        "message": "sel_lint 执行完毕但 _lint_history.json 无今日记录"}],
        })
        return

    # 3) 提取关键指标
    high = entry.get("high", 0)
    med = entry.get("med", 0)
    draft_count = entry.get("draft_count", 0)
    ghost_count = entry.get("ghost_count", 0)
    draft_max_days = entry.get("draft_max_days", 0)

    # 健康判定
    if high > 0:
        health = "degraded" if high <= 3 else "critical"
    elif med > 5:
        health = "degraded"
    else:
        health = "healthy"

    issues = []
    if draft_count > 0:
        issues.append({
            "area": "draft",
            "severity": "high" if draft_max_days > 14 else "medium",
            "message": f"{draft_count}个draft文件待验证, 最长{draft_max_days}天",
        })
    if ghost_count > 0:
        issues.append({
            "area": "ghost_refs",
            "severity": "high" if ghost_count > 5 else "medium",
            "message": f"{ghost_count}个幽灵引用",
        })

    publish_status("engineering", {
        "health": health,
        "pipeline": {
            "lint": {
                "status": "ok",
                "at": entry.get("date", ""),
                "high": high,
                "med": med,
            }
        },
        "issues": issues,
        "consumers": ["front-office"],
    })

    logger.info("[工程部] 状态已发布: health=%s high=%d med=%d", health, high, med)


if __name__ == "__main__":
    main()
