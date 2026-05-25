"""
System Health Check — validates scheduled tasks, disk space, and Feishu push.
Run as a daily Claude Code cron to monitor system health.
"""
import json
import logging
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from config import (
    FEISHU_APP_ID,
    FEISHU_APP_SECRET,
    FEISHU_BOT_CHAT_ID,
)
from dept_status_protocol import publish_status

logger = logging.getLogger("health_check")

STOCK_DATA = Path("D:/1989n/stock_data")
TOOLS_DIR = Path(__file__).parent / "tools"

# Windows tasks expected — loaded from data/tasks.json
TASKS_JSON = Path(__file__).parent / "data" / "tasks.json"
_FALLBACK_WIN_TASKS = [
    "StockAnalysis_HealthCheck",
    "Cognitive_MorningBrief",
    "StockAnalysis_CallAuction",
    "StockAnalysis_HotStocks",
    "StockAnalysis_IntradayMidday",
    "StockAnalysis_IntradayClose",
    "StockAnalysis_ClosingReview",
    "StockAnalysis_TechScan",
    "StockAnalysis_NightlyPlan",
    "StockAnalysis_Evening",
    "StockAnalysis_Overnight",
]


def _load_win_tasks() -> list[str]:
    if TASKS_JSON.exists():
        try:
            data = json.loads(TASKS_JSON.read_text(encoding="utf-8"))
            return [
                t["name"] for t in data.get("tasks", [])
                if t.get("enabled") and t.get("type") == "win_task" and t.get("name")
            ]
        except Exception:
            pass
    return _FALLBACK_WIN_TASKS


WIN_TASKS = _load_win_tasks()

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


def check_import_gate() -> dict:
    """Run syntax gate scan, return {gate, passed, failures, details}."""
    try:
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "import_gate.py"), "--full", "--json"],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(result.stdout)
    except (json.JSONDecodeError, KeyError, subprocess.TimeoutExpired) as e:
        return {"gate": "import_syntax", "passed": False, "failures": 1,
                "details": [{"file": "_subprocess", "msg": str(e)[:200]}]}


def check_schema_gate() -> dict:
    """Run schema gate scan, return {files_checked, passed, violations}."""
    try:
        result = subprocess.run(
            [sys.executable, str(TOOLS_DIR / "schema_gate.py"), "--json"],
            capture_output=True, text=True, timeout=30,
        )
        return json.loads(result.stdout)
    except (json.JSONDecodeError, KeyError, subprocess.TimeoutExpired) as e:
        return {"files_checked": 0, "passed": False,
                "violations": [{"file": "_subprocess", "issues": [{"detail": str(e)[:200]}]}]}


def generate_report(
    win_ok: list, win_missing: list, disk: dict, feishu_ok: bool,
    import_gate: dict | None = None,
    schema_gate: dict | None = None,
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

    # ── 门禁状态 ──
    ig = import_gate or {}
    lines.append(f" 语法门禁: {'通过' if ig.get('passed') else '异常'}"
                 f" ({ig.get('failures', '?')} 个错误)")

    sg = schema_gate or {}
    v_count = sum(len(v.get("issues", [])) for v in sg.get("violations", []))
    lines.append(f" Schema门禁: {'通过' if sg.get('passed') else '异常'}"
                 f" (校验 {sg.get('files_checked', 0)} 个文件, {v_count} 个问题)")

    alerts = []
    if win_missing:
        alerts.append(f"缺失计划任务: {', '.join(win_missing)}")
    if not disk["ok"]:
        alerts.append(f"D盘空间不足: 仅剩 {disk['free_gb']}GB")
    if not ig.get("passed", True):
        alerts.append(f"语法错误: {ig.get('failures', '?')} 个")
    if not sg.get("passed", True):
        alerts.append(f"Schema违规: {v_count} 项")

    if alerts:
        lines.insert(1, " 异常: " + "; ".join(alerts))

    return "\n".join(lines)


def _write_channel_health():
    """快速通道连通性检测，写 channel_health_latest.json。"""
    import urllib.request
    channels = {
        "sina_stock": "https://vip.stock.finance.sina.com.cn/",
        "tencent": "https://web.ifzq.gtimg.cn/",
        "eastmoney": "https://push2.eastmoney.com/",
    }
    result = {}
    for name, url in channels.items():
        try:
            urllib.request.urlopen(url, timeout=5)
            result[name] = True
        except Exception:
            result[name] = False
    result["healthy"] = any(result.values())
    (STOCK_DATA / "channel_health_latest.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    logger.info("通道健康已更新: %d/3 可用", sum(1 for v in result.values() if v))


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    disk = check_disk()
    feishu_ok = check_feishu_push()
    # Note: Claude Code cron tasks can only be checked within Claude session
    # win_tasks are checked from this script
    win_ok, win_missing = check_windows_tasks()

    # ── 门禁检查 (工程部) ──
    import_gate_result = check_import_gate()
    schema_gate_result = check_schema_gate()

    report = generate_report(win_ok, win_missing, disk, feishu_ok,
                             import_gate_result, schema_gate_result)
    logger.info("Health check complete")

    # Send report to Feishu
    send_alert(report)

    # 后勤部状态发布
    issues = []
    if win_missing:
        issues.append(f"缺失计划任务: {', '.join(win_missing)}")
    if not disk["ok"]:
        issues.append(f"D盘空间不足: 仅剩 {disk['free_gb']}GB")
    publish_status("logistics", {"health": "healthy" if not issues else "degraded", "issues": issues, "consumers": []})

    # 工程部门禁状态发布
    eng_issues = []
    if not import_gate_result.get("passed", True):
        eng_issues.append(f"语法门禁: {import_gate_result.get('failures', '?')} 个错误")
    sg = schema_gate_result or {}
    v_count = sum(len(v.get("issues", [])) for v in sg.get("violations", []))
    if not sg.get("passed", True):
        eng_issues.append(f"Schema门禁: {v_count} 项违规")
    eng_health = "healthy" if not eng_issues else "degraded"
    publish_status("engineering", {"health": eng_health, "issues": eng_issues, "consumers": ["logistics"]})

    # 通道健康快照 — 供 dept_preflight 保鲜检查
    _write_channel_health()

    # Print for local log
    print(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
