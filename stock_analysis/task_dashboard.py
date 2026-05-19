"""
task_dashboard.py — 定时任务一键看板

汇总 Windows 定时任务 + 部门健康 + 数据保鲜度 → 一张表发飞书。

用法:
    cd D:\1989n\stock_analysis && /d/Python314/python task_dashboard.py
"""

import json
import logging
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import data_quality_gate as dqg
from dept_status_protocol import read_other_dept
from feishu_sender import send_feishu_message

CST = timezone(timedelta(hours=8))
STOCK_ANALYSIS = Path(__file__).parent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("task_dashboard")


def get_win_task_status(task_name: str) -> dict:
    """查询单个 Windows 定时任务状态。"""
    try:
        r = subprocess.run(
            ["schtasks", "/Query", "/TN", task_name, "/FO", "CSV", "/V"],
            capture_output=True, text=True, timeout=10, encoding="gbk", errors="replace",
        )
        if r.returncode != 0:
            return {"name": task_name, "state": "缺失", "last_run": "N/A", "result": "N/A"}

        lines = r.stdout.strip().split("\n")
        if len(lines) < 2:
            return {"name": task_name, "state": "未知", "last_run": "N/A", "result": "N/A"}

        # CSV format: Host,TaskName,NextRun,Status,LogonMode,LastRun,LastResult,...
        parts = lines[1].split(",")
        if len(parts) >= 7:
            state = parts[3].strip().strip('"')
            last_run = parts[5].strip().strip('"')
            last_result = parts[6].strip().strip('"')

            # 状态转图标
            state_icon = {"就绪": "✅", "准备就绪": "✅", "运行": "🔄", "已禁用": "⛔", "状态未知": "❓"}
            icon = state_icon.get(state, "❓")

            # 结果转图标
            result_icon = "✅" if last_result == "0" else f"❌({last_result})"
            if last_result in ("267011", "2147942401"):  # 从未运行过
                result_icon = "—"

            return {
                "name": task_name, "state": f"{icon} {state}",
                "last_run": last_run if last_run != "1999/11/30" else "从未",
                "result": result_icon,
                "_raw_state": state, "_raw_result": last_result,
            }
    except Exception as e:
        logger.warning(f"查询 {task_name} 失败: {e}")

    return {"name": task_name, "state": "❓ 查询失败", "last_run": "N/A", "result": "N/A"}


def get_all_tasks() -> list[dict]:
    """获取所有需要监控的任务状态。"""
    task_names = [
        "Cognitive_MorningBrief",      # 08:37 晨报
        "Cognitive_ConversationMiner", # 22:30 对话挖掘
        "StockAnalysis_HotStocks",     # 09:15起每小时 热门股票
        "StockAnalysis_MorningBrief",  # 08:27 盘前简报(旧,已禁用)
        "StockAnalysis_ClosingReview", # 15:05 收盘复盘
        "StockAnalysis_Evening",       # 22:00 晚间总结
        "StockAnalysis_IntradayMidday",# 11:30 盘中快照
        "StockAnalysis_IntradayClose", # 14:00 盘中快照
        "StockAnalysis_TechScan",      # 15:30 技术扫描
        "StockAnalysis_NightlyPlan",   # 22:00 晚间计划
        "StockAnalysis_Overnight",     # 23:30 隔夜分析
        "StockNightlyHealth",          # 02:00 夜间健康
        "StockNews_Morning",           # 08:00 早间新闻
        "StockNews_Intraday",          # 盘中新闻
        "StockNews_Evening",           # 晚间新闻
    ]
    results = []
    for name in task_names:
        results.append(get_win_task_status(name))
    return results


def get_dept_health() -> dict:
    """读取各部门健康状态。"""
    health = {}
    for dept in ["front-office", "engineering"]:
        status = read_other_dept(dept)
        if status:
            h = status.get("health", "unknown")
            icon = {"healthy": "✅", "degraded": "⚠️", "critical": "🔴", "unknown": "❓"}
            health[dept] = f"{icon.get(h, '❓')} {h}"
            if status.get("issues"):
                health[f"{dept}_issues"] = status["issues"][:3]
        else:
            health[dept] = "❓ 无状态"
    return health


def get_data_freshness() -> str:
    """汇总关键数据保鲜度。"""
    scan = dqg.preflight_scan()
    if scan["healthy"]:
        return "✅ 全部新鲜"
    stale = [c for c in scan["checks"] if not c["pass"]]
    parts = []
    for s in stale[:5]:
        parts.append(f"  ⚠ {s['file']}: {s['age_hours']:.0f}h (阈值{s.get('max_hours', 0):.0f}h)")
    return "⚠ " + ", ".join(f"{s['file']}({s['age_hours']:.0f}h)" for s in stale[:5])


def build_report(tasks: list[dict], dept_health: dict, data_fresh: str) -> str:
    """生成 markdown 看板。"""
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    lines = [f"## 📊 系统看板 | {now}", ""]

    # 任务状态表
    lines.append("### 定时任务")
    lines.append("| 任务 | 状态 | 上次运行 | 结果 |")
    lines.append("|------|------|----------|------|")
    for t in tasks:
        # 截断任务名便于阅读
        # 显示名映射（短名可读）
        display_names = {
            "Cognitive_MorningBrief": "晨报(DeepSeek)",
            "Cognitive_ConversationMiner": "对话挖掘",
            "Cognitive_TaskDashboard": "系统看板",
            "StockAnalysis_HotStocks": "热门股票",
            "StockAnalysis_MorningBrief": "晨报(旧)",
            "StockAnalysis_ClosingReview": "收盘复盘",
            "StockAnalysis_IntradayMidday": "盘中-午",
            "StockAnalysis_IntradayClose": "盘中-收",
            "StockAnalysis_TechScan": "技术扫描",
            "StockAnalysis_NightlyPlan": "晚间计划",
            "StockAnalysis_Overnight": "隔夜分析",
            "StockAnalysis_Evening": "晚间总结",
            "StockNightlyHealth": "夜间健康",
            "StockNews_Morning": "早间新闻",
            "StockNews_Intraday": "盘中新闻",
            "StockNews_Evening": "晚间新闻",
            "Stock_CallAuction": "集合竞价",
        }
        name = display_names.get(t["name"], t["name"])
        lines.append(f"| {name} | {t['state']} | {t['last_run']} | {t['result']} |")

    lines.append("")
    lines.append("### 部门健康")
    for dept, health in dept_health.items():
        if "_issues" not in dept:
            lines.append(f"- {dept}: {health}")

    lines.append("")
    lines.append(f"### 数据保鲜")
    lines.append(data_fresh)

    # 风险汇总
    lines.append("")
    risks = []
    for t in tasks:
        if "❌" in str(t.get("result", "")):
            risks.append(f"- ❌ {t['name']}: {t['result']}")
    for dept, health in dept_health.items():
        if "🔴" in str(health):
            risks.append(f"- 🔴 {dept}: {health}")
        elif "⚠️" in str(health):
            risks.append(f"- ⚠️ {dept}: {health}")

    if risks:
        lines.append("### ⚠ 待关注")
        lines.extend(risks)
    else:
        lines.append("### ✅ 一切正常")

    return "\n".join(lines)


def main():
    logger.info("构建系统看板...")

    tasks = get_all_tasks()
    dept_health = get_dept_health()
    data_fresh = get_data_freshness()

    report = build_report(tasks, dept_health, data_fresh)

    # 输出到文件
    out_dir = STOCK_ANALYSIS / ".." / "stock_data"
    out_path = (out_dir / "task_dashboard.md").resolve()
    out_path.write_text(report, encoding="utf-8")
    logger.info(f"看板已写入: {out_path}")

    # 发送飞书
    ok = send_feishu_message("📊 系统看板", report, chat_id="alerts")
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    # 如果有高风险项，额外告警
    high_risks = [t for t in tasks if "❌" in str(t.get("result", ""))]
    if high_risks:
        risk_names = [t["name"] for t in high_risks]
        send_feishu_message("🔴 任务异常", f"以下任务执行失败:\n" + "\n".join(f"- {n}" for n in risk_names), chat_id="alerts")

    print(report)


if __name__ == "__main__":
    main()
