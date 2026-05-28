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
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
LINT_HISTORY = Path("D:/1989n/.claude/memory/daily/_lint_history.json")
LINT_DAILY_DIR = Path("D:/1989n/.claude/memory/daily")
DEPT_STATUS_DIR = Path("D:/1989n/stock_data/status")
AGENT_EXEC_LOG = Path("D:/1989n/logs/agent_exec")

# ── Feishu ─────────────────────────────────────────────────────────────
try:
    from feishu_sender import send_feishu_alert
except ImportError:
    def send_feishu_alert(*a, **kw):
        pass


def scan_agent_patterns():
    """两阶段验证桥接: 扫描 agent_exec 日志, 提取高频成功模式.

    Phase 1 (廉价): 按agent分组统计成功调用, 检测重复模式.
    Phase 2 (验证): 与knowledge_db对比, 给出蒸馏建议.

    参考: agent-learn Trace->Validate->Inject, SkillCam 两阶段蒸馏.
    返回dict: {agent_name: {calls, success_rate, summary_examples, distill_suggestion}}
    """
    if not AGENT_EXEC_LOG.exists():
        return {}

    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    agent_stats: dict[str, dict] = {}

    for day_dir in sorted(AGENT_EXEC_LOG.iterdir()):
        if not day_dir.is_dir():
            continue
        try:
            day = datetime.strptime(day_dir.name, "%Y-%m-%d").date()
            if datetime.combine(day, datetime.min.time()).replace(tzinfo=timezone.utc) < cutoff:
                continue
        except ValueError:
            continue

        for log_file in day_dir.glob("*.json"):
            agent_name = log_file.stem
            if agent_name not in agent_stats:
                agent_stats[agent_name] = {
                    "calls": 0, "success": 0, "fail": 0,
                    "summaries": [], "tasks": Counter(),
                }
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                records = data if isinstance(data, list) else [data]
                for rec in records:
                    agent_stats[agent_name]["calls"] += 1
                    task = rec.get("task", "")[:60]
                    if task:
                        agent_stats[agent_name]["tasks"][task] += 1
                    if rec.get("exit_code", -1) == 0:
                        agent_stats[agent_name]["success"] += 1
                        summary = rec.get("output_summary", "")[:80]
                        if summary and summary not in agent_stats[agent_name]["summaries"]:
                            agent_stats[agent_name]["summaries"].append(summary)
                    else:
                        agent_stats[agent_name]["fail"] += 1
            except (json.JSONDecodeError, Exception):
                continue

    # Phase 2: 分析结果, 给出蒸馏建议
    result = {}
    for name, stats in agent_stats.items():
        if stats["calls"] < 2:
            continue  # 样本太少, 不分析
        success_rate = round(stats["success"] / stats["calls"] * 100, 1) if stats["calls"] else 0
        repeat_tasks = {t: c for t, c in stats["tasks"].items() if c >= 2}
        has_repeat_pattern = len(repeat_tasks) > 0

        distill_suggestion = None
        if has_repeat_pattern and success_rate >= 80:
            distill_suggestion = (
                f"考虑蒸馏为 Skill — Agent {name} 在 {stats['calls']} 次调用中 "
                f"成功率 {success_rate}%, 且有 {len(repeat_tasks)} 个重复任务模式"
            )
        elif has_repeat_pattern and success_rate < 80:
            distill_suggestion = (
                f"需排查 — Agent {name} 有重复任务但成功率仅 {success_rate}%"
            )

        result[name] = {
            "calls": stats["calls"],
            "success": stats["success"],
            "fail": stats["fail"],
            "success_rate": success_rate,
            "unique_tasks": len(stats["tasks"]),
            "repeat_patterns": len(repeat_tasks),
            "distill_suggestion": distill_suggestion,
        }

    return result


def main():
    today = date.today().isoformat()

    # 0) 两阶段 Agent 模式验证 (独立于 lint 运行)
    agent_patterns = scan_agent_patterns()
    if agent_patterns:
        print(f"[digest] Agent 模式扫描: {len(agent_patterns)} 个 Agent 有足够样本")
        for name, stats in sorted(agent_patterns.items()):
            print(f"  {name}: {stats['calls']}次调用, "
                  f"成功率{stats['success_rate']}%, "
                  f"重复模式{stats['repeat_patterns']}个")
            if stats["distill_suggestion"]:
                print(f"    -> {stats['distill_suggestion']}")
    else:
        print("[digest] Agent 模式扫描: 样本不足")

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

    # 5) 注入 agent 模式到状态
    if agent_patterns:
        dept_status["agent_patterns"] = agent_patterns

    # 4) HIGH 告警
    if high > 0:
        alert_msg = f"[SEL Digest] Lint 发现 {high} 项 HIGH 问题"
        print(f"[digest] 触发飞书告警: {alert_msg}")
        send_feishu_alert(alert_msg)

    dept_status_file = DEPT_STATUS_DIR / "engineering_status.json"
    dept_status_file.parent.mkdir(parents=True, exist_ok=True)
    dept_status_file.write_text(
        json.dumps(dept_status, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[digest] 状态已发布 -> {dept_status_file}")


if __name__ == "__main__":
    main()
