#!/usr/bin/env python3
"""
SEL Digest v1 — 读取今日 Lint 报告，分析重点，发布状态。
在 Lint 完成后运行（09:00 每日）。

流程:
  1. 读取今日 _lint.md 报告
  2. 提取 HIGH/MEDIUM 问题
  3. 发布到 engineering 状态协议
  4. HIGH 问题触发飞书告警

用法:
  cd D:/1989n/stock_analysis && python sel_digest.py
"""

import json
import sys
from datetime import date
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
LINT_HISTORY = Path("D:/1989n/.claude/memory/daily/_lint_history.json")
LINT_DAILY_DIR = Path("D:/1989n/.claude/memory/daily")
DEPT_STATUS_DIR = Path("D:/1989n/stock_data/status")

# ── Feishu ─────────────────────────────────────────────────────────────
try:
    from feishu_sender import send_feishu_alert
except ImportError:
    def send_feishu_alert(*a, **kw):
        pass


def main():
    today = date.today().isoformat()

    # 1) 读历史记录
    if not LINT_HISTORY.exists():
        print("[digest] 无 _lint_history.json，跳过")
        return

    history = json.loads(LINT_HISTORY.read_text(encoding="utf-8"))
    today_entry = None
    for entry in history:
        if entry.get("date") == today:
            today_entry = entry
            break

    if not today_entry:
        print(f"[digest] 今日({today})无 Lint 记录")
        return

    high = today_entry.get("high", 0)
    med = today_entry.get("med", 0)
    low = today_entry.get("low", 0)
    draft_count = today_entry.get("draft_count", 0)
    ghost_count = today_entry.get("ghost_count", 0)

    print(f"[digest] Lint 今日结果: HIGH={high} MED={med} LOW={low} "
          f"draft={draft_count} ghost={ghost_count}")

    # 2) 读完整报告（如果有）
    report_file = LINT_DAILY_DIR / f"{today}_lint.md"
    report_text = ""
    if report_file.exists():
        report_text = report_file.read_text(encoding="utf-8", errors="ignore")

    # 3) 发布状态
    dept_status = {
        "department": "engineering",
        "timestamp": __import__("datetime").datetime.now(
            __import__("datetime").timezone(__import__("datetime").timedelta(hours=8))
        ).isoformat(),
        "health": "degraded" if high > 0 else ("healthy" if med <= 5 else "degraded"),
        "pipeline": {
            "lint": {"status": "ok", "at": today, "high": high, "med": med},
            "digest": {"status": "ok", "at": today},
            "maintain": {"status": "pending"},
        },
        "issues": [],
        "consumers": ["front-office"],
    }

    issues = []
    if high > 0:
        issues.append({"area": "lint_high", "severity": "high",
                        "message": f"{high} 项 HIGH 问题"})
    if draft_count > 3:
        issues.append({"area": "draft", "severity": "medium",
                        "message": f"{draft_count} 个 draft 文件待验证"})
    if ghost_count > 0:
        issues.append({"area": "ghost_refs", "severity": "medium",
                        "message": f"{ghost_count} 个幽灵引用"})
    dept_status["issues"] = issues

    dept_status_file = DEPT_STATUS_DIR / "engineering_status.json"
    dept_status_file.parent.mkdir(parents=True, exist_ok=True)
    dept_status_file.write_text(
        json.dumps(dept_status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[digest] 状态已发布 → {dept_status_file}")

    # 4) HIGH 告警
    if high > 0:
        alert_msg = f"[SEL Digest] Lint 发现 {high} 项 HIGH 问题"
        print(f"[digest] 触发飞书告警: {alert_msg}")
        send_feishu_alert(alert_msg)


if __name__ == "__main__":
    main()
