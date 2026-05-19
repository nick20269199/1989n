#!/usr/bin/env python3
"""
夜间健康检查 (Nightly Health Check)
- C盘空间 < 10GB → 飞书告警
- D盘空间 < 10GB → 飞书告警
- Windows计划任务异常 → 飞书告警
- Claude Code cron 持久化文件检查 → 飞书告警
- 无异常则静默 (不发消息)
"""

import os
import sys
import json
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from feishu_sender import send_feishu_alert
from config import FEISHU_ROUTES

_ALERT_CHAT_ID = FEISHU_ROUTES.get("alerts", "")

# ── helpers ──────────────────────────────────────────────

def send_feishu(title, content_lines):
    """发送飞书告警到问题组"""
    if not _ALERT_CHAT_ID:
        print("[ERROR] 问题组 chat_id 未配置")
        return False
    content = "\n".join(content_lines)
    return send_feishu_alert(title, content, chat_id=_ALERT_CHAT_ID)


def check_disk(path, label):
    """检查磁盘空间，返回 (free_gb, alert_msg)"""
    usage = shutil.disk_usage(path)
    free_gb = usage.free / (1024 ** 3)
    total_gb = usage.total / (1024 ** 3)
    pct = (free_gb / total_gb) * 100

    if free_gb < 10:
        return free_gb, f"{label}盘仅剩 **{free_gb:.1f}GB** ({pct:.1f}%)，总容量 {total_gb:.0f}GB"
    return free_gb, None


def check_windows_tasks():
    """检查所有Stock*计划任务状态，返回告警列表"""
    alerts = []
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-ScheduledTask -TaskName 'Stock*' | "
             "Select-Object TaskName,State,LastTaskResult,LastRunTime | "
             "ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return [f"PowerShell查询计划任务失败: {result.stderr.strip()}"]

        tasks = json.loads(result.stdout) if result.stdout.strip() else []
        if not tasks:
            return []

        # 单任务→列表
        if isinstance(tasks, dict):
            tasks = [tasks]

        STATE_NAMES = {0: "Unknown", 1: "Disabled", 2: "Queued", 3: "Ready", 4: "Running"}
        for t in tasks:
            name = t.get("TaskName", "?")
            state = t.get("State", -1)
            last_result = t.get("LastTaskResult")
            last_run = t.get("LastRunTime") or "从未运行"

            # Disabled 是人为操作，不视为异常
            if state == 1:
                continue
            if state != 3:
                state_name = STATE_NAMES.get(state, f"未知({state})")
                alerts.append(f"**{name}** 状态异常: `{state_name}`")
            elif last_result is not None and last_result != 0:
                alerts.append(
                    f"**{name}** 上次执行失败 (0x{last_result:08X})，上次运行: {last_run}"
                )

        return alerts
    except Exception as e:
        return [f"检查计划任务异常: {e}"]


def _get_cron_threshold(cron_expr: str) -> float:
    """根据cron表达式返回合适的过期阈值（小时）。

    工作日任务 (1-5): 周末 ~64h 空档 → 75h
    周任务 (单DOW如"6"): 最大间隔168h → 172h
    多DOW如"0,6","1,3,5": 保守取168h安全
    *: 日多次 → 48h
    """
    parts = cron_expr.split()
    if len(parts) >= 5:
        dow = parts[4].strip()
        if dow in ("1-5", "1,2,3,4,5"):
            return 75
        if dow == "*":
            return 48
        # 单天（如"6"=周六）或 多天列表 — 周任务，~168h间隔
        return 172
    return 48


def check_claude_cron():
    """检查 scheduled_tasks.json，返回告警列表"""
    alerts = []
    # 优先检查项目路径（D:），回退到用户路径（C:）
    cron_candidates = [
        "D:/1989n/.claude/scheduled_tasks.json",
        os.path.expanduser("~/.claude/scheduled_tasks.json"),
    ]
    cron_file = None
    for p in cron_candidates:
        if os.path.exists(p):
            cron_file = p
            break
    if not cron_file:
        return [f"Claude Code cron 持久化文件不存在，检查过: {cron_candidates}"]
    print(f"[OK] Claude cron 文件: {cron_file}")

    try:
        with open(cron_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        tasks = data.get("tasks", [])
        if not tasks:
            return ["Claude Code cron 任务列表为空"]

        now_ts = datetime.now().timestamp() * 1000
        for t in tasks:
            name = t.get("id", "?")
            cron = t.get("cron", "?")
            threshold = _get_cron_threshold(cron)
            last_fired = t.get("lastFiredAt")
            if last_fired:
                hours_since = (now_ts - last_fired) / 3600000
                if hours_since > threshold:
                    alerts.append(
                        f"**{cron}** 上次触发 {hours_since:.0f}小时前（阈值{threshold:.0f}h），可能过期"
                    )
            else:
                # 新任务还没触发过，不算问题
                pass
        return alerts
    except Exception as e:
        return [f"检查Claude cron异常: {e}"]


# ── main ─────────────────────────────────────────────────

def main():
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    alerts = []

    # 1. 磁盘空间
    for drive, label in [("C:\\", "C"), ("D:\\", "D")]:
        free, msg = check_disk(drive, label)
        if msg:
            alerts.append(msg)
        else:
            print(f"[OK] {label}盘剩余 {free:.1f}GB")

    # 2. Windows 计划任务
    task_alerts = check_windows_tasks()
    alerts.extend(task_alerts)
    if not task_alerts:
        print("[OK] 所有 Windows 计划任务正常")

    # 3. Claude Code cron
    cron_alerts = check_claude_cron()
    alerts.extend(cron_alerts)
    if not cron_alerts:
        print("[OK] Claude Code cron 正常")

    # 4. 汇总
    if alerts:
        title = f"夜间健康告警 ({timestamp})"
        content = [f"共 **{len(alerts)}** 项异常:\n"] + [f"- {a}" for a in alerts]
        print(f"[ALERT] {len(alerts)} 项异常，发送飞书告警...")
        ok = send_feishu(title, content)
        print(f"[{'OK' if ok else 'FAIL'}] 飞书发送{'成功' if ok else '失败'}")
    else:
        print(f"[ALL CLEAR] {timestamp} — 所有检查通过，静默退出")


if __name__ == "__main__":
    main()
