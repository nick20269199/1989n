"""
System Health Check — validates scheduled tasks, disk space, and Feishu push.
Run as a daily Claude Code cron to monitor system health.
"""
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime

import requests

from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_BOT_CHAT_ID,
)

logger = logging.getLogger("health_check")

# Windows tasks expected (StockNews_* and StockNightlyHealth are Claude Code crons)
WIN_TASKS = [
    "StockAnalysis_MorningBrief",
    "StockAnalysis_ClosingReview",
    "StockAnalysis_HotStocks",
    "StockAnalysis_IntradayMidday",
    "StockAnalysis_IntradayClose",
    "StockAnalysis_TechScan",
    "StockAnalysis_Overnight",
]

# Claude Code cron tasks expected (by description keyword)
CRON_KEYWORDS = [
    "news_scheduler.py morning",
    "news_scheduler.py evening",
    "news_scheduler.py intraday",
    "夜间健康检查",
    "早间快速 Lint",
    "完整五阶段自进化",
    "每周定时任务续期",
    "进化阅读",
]

DISK_MIN_FREE_GB = 20
TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
IM_URL = "https://open.feishu.cn/open-apis/im/v1/messages"


def get_feishu_token() -> str:
    try:
        r = requests.post(
            TOKEN_URL,
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            timeout=10,
        )
        return r.json().get("tenant_access_token", "")
    except Exception as e:
        logger.error("Token fetch failed: %s", e)
        return ""


def send_alert(text: str) -> bool:
    token = get_feishu_token()
    if not token:
        return False
    try:
        r = requests.post(
            IM_URL + "?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "receive_id": FEISHU_BOT_CHAT_ID,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
            timeout=10,
        )
        return r.json().get("code") == 0
    except Exception as e:
        logger.error("Alert send failed: %s", e)
        return False


def check_windows_tasks() -> tuple[list[str], list[str]]:
    ok, missing = [], []
    try:
        result = subprocess.run(
            ["schtasks", "/query", "/fo", "CSV", "/nh"],
            capture_output=True, timeout=15,
        )
        output = result.stdout.decode("gbk", errors="replace")
        for task in WIN_TASKS:
            if task in output:
                ok.append(task)
            else:
                missing.append(task)
    except Exception as e:
        logger.warning("schtasks query failed: %s", e)
        missing = WIN_TASKS[:]
    return ok, missing


def check_disk() -> dict:
    d = shutil.disk_usage("D:/")
    free_gb = d.free / (1024 ** 3)
    return {
        "total_gb": round(d.total / (1024 ** 3), 1),
        "free_gb": round(free_gb, 1),
        "ok": free_gb >= DISK_MIN_FREE_GB,
    }


def check_feishu_push() -> bool:
    return send_alert("[系统健康检查] 定时推送测试通过")


def generate_report(
    win_ok: list, win_missing: list, disk: dict, feishu_ok: bool
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [f"系统健康检查报告 {now}", "=" * 30]

    # Windows tasks
    if win_missing:
        lines.append(f" Windows 计划任务: {len(win_ok)}/{len(WIN_TASKS)} 正常")
        for t in win_missing:
            lines.append(f"   缺失: {t}")
    else:
        lines.append(f" Windows 计划任务: {len(win_ok)}/{len(WIN_TASKS)} 正常")

    # Disk
    status = "正常" if disk["ok"] else "告警"
    lines.append(f" D盘空间: {disk['free_gb']}GB 剩余 ({status})")

    # Feishu
    lines.append(f" 飞书推送: {'正常' if feishu_ok else '异常'}")

    # Claude Code cron tasks (note: can't check from script, skip)
    lines.append(" Claude Code cron: 需在Claude内检查 (见下方)")

    alerts = []
    if win_missing:
        alerts.append(f"缺失计划任务: {', '.join(win_missing)}")
    if not disk["ok"]:
        alerts.append(f"D盘空间不足: 仅剩 {disk['free_gb']}GB")

    if alerts:
        lines.insert(1, " 异常: " + "; ".join(alerts))

    return "\n".join(lines)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    disk = check_disk()
    feishu_ok = check_feishu_push()
    # Note: Claude Code cron tasks can only be checked within Claude session
    # win_tasks are checked from this script
    win_ok, win_missing = check_windows_tasks()

    report = generate_report(win_ok, win_missing, disk, feishu_ok)
    logger.info("Health check complete")

    # Send report to Feishu
    send_alert(report)

    # Print for local log
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
