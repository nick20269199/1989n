#!D:/Python314/python
"""
Task Sentinel v1.0 — 任务哨兵
==============================
每小时检查 Windows 计划任务 + Claude cron 任务状态。
发现缺失 → 自动修复（调用 register_tasks.ps1）
发现异常 → 飞书告警
设计原则: 只修复不删除，所有操作可审计
"""

from error_capture import trap; trap()

import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))

SCRIPT_DIR = Path(__file__).parent
STOCK_DATA = Path(r"D:\1989n\stock_data")
SENTINEL_LOG = STOCK_DATA / "sentinel_status.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("task-sentinel")

# ── 期望的 Windows 计划任务 ──
EXPECTED_WIN_TASKS = [
    "StockAnalysis_MorningBrief",
    "StockAnalysis_HotStocks",
    "StockAnalysis_IntradayMidday",
    "StockAnalysis_IntradayClose",
    "StockAnalysis_ClosingReview",
    "StockAnalysis_TechScan",
    "StockAnalysis_NightlyPlan",
    "StockAnalysis_Overnight",
]

# ── 期望的 Claude cron 任务关键词 ──
EXPECTED_CRON_KEYWORDS = [
    "morning_enhanced", "call_auction", "closing_review", "tech_scan",
    "daily-load", "daily-compress", "deep-research", "weekly-audit",
    "health_check", "nightly_health", "morning_brief",
    "news_scheduler", "intraday_report", "vv_radar",
]

# 合并中文关键词映射
CRON_KW_CN = [
    "盘前", "集合竞价", "收盘", "技术形态", "晨间", "压缩", "深度研究",
    "健康检查", "夜间", "盘前晨报", "新闻", "盘中", "大V",
]


def check_win_tasks() -> dict:
    """检查 Windows 计划任务状态。返回 {found: [...], missing: [...]}"""
    found = []
    missing = []
    for name in EXPECTED_WIN_TASKS:
        try:
            result = subprocess.run(
                ["C:/Windows/System32/schtasks.exe", "/Query", "/TN", name, "/FO", "LIST"],
                capture_output=True, timeout=10
            )
            # schtasks outputs GBK on Chinese Windows
            stdout = result.stdout.decode("gbk", errors="replace") if result.stdout else ""
            if result.returncode == 0 and "ERROR" not in stdout:
                found.append(name)
            else:
                missing.append(name)
        except Exception as e:
            logger.warning(f"schtasks query failed for {name}: {e}")
            missing.append(name)
    return {"found": found, "missing": missing}


def repair_win_tasks() -> bool:
    """调用 register_tasks.ps1 安全重建所有任务 (/F 覆盖，不先删)。"""
    ps1 = SCRIPT_DIR / "register_tasks.ps1"
    if not ps1.exists():
        logger.error(f"register_tasks.ps1 not found at {ps1}")
        return False
    try:
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", str(ps1)],
            capture_output=True, timeout=120
        )
        stdout = result.stdout.decode("gbk", errors="replace") if result.stdout else ""
        stderr = result.stderr.decode("gbk", errors="replace") if result.stderr else ""
        if "All tasks verified OK" in stdout or "All tasks verified OK" in stderr:
            logger.info("Windows tasks repaired successfully")
            return True
        else:
            logger.error(f"Repair failed. stdout={stdout[-200:]}, stderr={stderr[-200:]}")
            return False
    except Exception as e:
        logger.error(f"Repair error: {e}")
        return False


def check_claude_cron() -> dict:
    """检查 Claude cron 任务。读取项目 .claude/scheduled_tasks.json"""
    cron_file = Path(r"D:\1989n\.claude\scheduled_tasks.json")
    if not cron_file.exists():
        return {"found": [], "missing": EXPECTED_CRON_KEYWORDS, "total": 0}
    try:
        data = json.loads(cron_file.read_text(encoding="utf-8"))
        tasks = data.get("tasks", [])
        prompts_all = " ".join(t.get("prompt", "") for t in tasks)
        # 中英文关键词都匹配
        all_keywords = EXPECTED_CRON_KEYWORDS + CRON_KW_CN
        found = [kw for kw in all_keywords if kw.lower() in prompts_all.lower()]
        missing = [kw for kw in EXPECTED_CRON_KEYWORDS if kw.lower() not in prompts_all.lower()]
        return {"found": found, "missing": missing, "total": len(tasks)}
    except Exception as e:
        logger.error(f"Cron check failed: {e}")
        return {"found": [], "missing": EXPECTED_CRON_KEYWORDS, "total": 0}


def check_data_files() -> dict:
    """检查关键数据文件是否存在且非空。"""
    required = [
        "concept_mapping.json",
        "learning/rules.json",
        "learning/ratio_baselines.json",
        "closing_review.json",
    ]
    status = {"ok": [], "missing": [], "empty": []}
    for fname in required:
        fpath = STOCK_DATA / fname
        if not fpath.exists():
            status["missing"].append(fname)
        elif fpath.stat().st_size < 10:
            status["empty"].append(fname)
        else:
            status["ok"].append(fname)
    return status


def run():
    """主巡检函数。"""
    now = datetime.now(CST)
    logger.info(f"Sentinel scan at {now.strftime('%H:%M')}")

    report = {
        "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
        "win_tasks": check_win_tasks(),
        "cron_tasks": check_claude_cron(),
        "data_files": check_data_files(),
        "actions": [],
    }

    # 自动修复: Windows 任务缺失
    if report["win_tasks"]["missing"]:
        logger.warning(f"Missing Win tasks: {report['win_tasks']['missing']}")
        if repair_win_tasks():
            report["actions"].append("auto-repaired Windows tasks")
        else:
            report["actions"].append("WIN_TASKS_REPAIR_FAILED")

    # 飞书告警判断
    alerts = []
    if len(report["win_tasks"]["missing"]) >= 3:
        alerts.append(f"WIN_TASKS_MISSING: {len(report['win_tasks']['missing'])} tasks")
    if len(report["cron_tasks"]["missing"]) >= 3:
        alerts.append(f"CRON_MISSING: {len(report['cron_tasks']['missing'])} keywords")
    if report["data_files"]["missing"]:
        alerts.append(f"DATA_MISSING: {report['data_files']['missing']}")

    report["alerts"] = alerts

    # 持久化
    SENTINEL_LOG.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if alerts:
        logger.warning(f"ALERTS: {alerts}")
    else:
        logger.info("All systems normal")

    return report


if __name__ == "__main__":
    report = run()
    print(json.dumps({
        "time": report["timestamp"],
        "win": f"{len(report['win_tasks']['found'])}/{len(EXPECTED_WIN_TASKS)}",
        "cron": f"{report['cron_tasks']['total']} jobs, {len(report['cron_tasks']['missing'])} missing kw",
        "data": f"{len(report['data_files']['ok'])} ok, {len(report['data_files']['missing'])} missing",
        "alerts": report["alerts"],
    }, ensure_ascii=False, indent=2))
