"""
task_dashboard.py — 定时任务一键看板

汇总 Windows 定时任务 + 部门健康 + 数据保鲜度 → 一张表发飞书。

用法:
    cd D:/1989n/stock_analysis && /d/Python314/python task_dashboard.py
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
            # 良性退出码白名单: STATUS_CONTROL_C_EXIT (Python/akshare退出时子进程发送Ctrl+C)
            _BENIGN_CODES = {"0", "1", "3221225786", "-1073741510", "267009"}
            result_icon = "✅" if last_result in _BENIGN_CODES else f"❌({last_result})"
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
    """获取所有需要监控的任务状态 (从 data/tasks.json 加载)。"""
    # Load from tasks.json
    tasks_json = STOCK_ANALYSIS / "data" / "tasks.json"
    task_names = []
    if tasks_json.exists():
        try:
            data = json.loads(tasks_json.read_text(encoding="utf-8"))
            task_names = [
                t["name"] for t in data.get("tasks", [])
                if t.get("name") and t.get("type") == "win_task"
            ]
        except Exception as e:
            logger.warning(f"Failed to load {tasks_json}: {e}")

    # Fallback if loading failed
    if not task_names:
        task_names = [
            "Cognitive_MorningBrief",
            "Cognitive_ConversationMiner",
            "StockAnalysis_HotStocks",
            "StockAnalysis_MorningBrief",
            "StockAnalysis_ClosingReview",
            "StockAnalysis_Evening",
            "StockAnalysis_IntradayMidday",
            "StockAnalysis_IntradayClose",
            "StockAnalysis_TechScan",
            "StockAnalysis_NightlyPlan",
            "StockAnalysis_Overnight",
            "StockNightlyHealth",
            "StockNews_Morning",
            "StockNews_Intraday",
            "StockNews_Evening",
        ]

    results = []
    for name in task_names:
        results.append(get_win_task_status(name))
    return results


def get_dept_health() -> dict:
    """读取各部门健康状态。"""
    health = {}
    for dept in ["front-office", "engineering", "intelligence", "logistics"]:
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


# 部门数据文件映射 (与 dept_preflight 同步)
DEPT_DATA_FILES = {
    "前厅部": ["portfolio.json", "closing_review.json", "channel_health_latest.json", "sentinel_status.json",
               "hot_stocks.json", "morning_brief_agent_latest.json", "call_auction_*.json",
               "analysis_30min_*.json", "analysis_overnight_*.json", "scan_*.json", "recon_report_*.md",
               "trade_plans/plan_*.json", "vv_radar.db", "position_check.json"],
    "工程部": ["_lint_history.json"],
    "情报部": ["intel/intel_latest.json"],
    "后勤部": ["task_dashboard.md"],
    "其他": None,  # None = 不在前四部门的全部文件
}

def _build_dept_file_map() -> dict[str, str]:
    """构建 文件名 → 部门名 的映射。"""
    m = {}
    for dept, files in DEPT_DATA_FILES.items():
        if files is None:
            continue
        for f in files:
            m[f] = dept
    return m

_DEPT_FILE_MAP = _build_dept_file_map()


def get_data_freshness() -> dict:
    """汇总关键数据保鲜度，按部门分组。"""
    scan = dqg.preflight_scan()
    checks = scan["checks"]

    by_dept: dict[str, list] = {"前厅部": [], "工程部": [], "其他": []}
    for c in checks:
        dept = _DEPT_FILE_MAP.get(c["file"], "其他")
        by_dept[dept].append(c)

    return {"healthy": scan["healthy"], "by_dept": by_dept, "all_checks": checks}


def build_report(tasks: list[dict], dept_health: dict, data_fresh: dict) -> str:
    """生成 markdown 看板。"""
    now = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    lines = [f"## 📊 系统看板 | {now}", ""]

    # 任务状态表
    lines.append("### 定时任务")
    lines.append("| 任务 | 状态 | 上次运行 | 结果 |")
    lines.append("|------|------|----------|------|")
    for t in tasks:
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
            "StockAnalysis_HealthCheck": "健康检查",
            "StockAnalysis_CallAuction": "集合竞价",
            "StockAnalysis_Recon": "侦查日报",
            "StockAnalysis_VVRadar": "大V雷达(早)",
            "StockAnalysis_VVRadar_Afternoon": "大V雷达(午)",
            "StockNightlyHealth": "夜间健康",
            "StockForecastCloser": "预测闭环",
            "StockNews_Morning": "早间新闻",
            "StockNews_Intraday": "盘中新闻",
            "StockNews_Evening": "晚间新闻",
        }
        # 未知任务保留原名, 去掉 StockAnalysis_/StockNews_/Cognitive_ 前缀
        short = t["name"]
        if short not in display_names:
            for prefix in ["StockAnalysis_", "StockNews_", "Cognitive_", "Stock"]:
                if short.startswith(prefix):
                    short = short[len(prefix):]
                    break
        name = display_names.get(t["name"], short)
        lines.append(f"| {name} | {t['state']} | {t['last_run']} | {t['result']} |")

    lines.append("")
    lines.append("### 部门健康")
    for dept, health in dept_health.items():
        if "_issues" not in dept:
            lines.append(f"- {dept}: {health}")

    # 数据保鲜 — 按部门分组
    lines.append("")
    lines.append("### 数据保鲜")
    if data_fresh["healthy"]:
        lines.append("✅ 全部新鲜")
    else:
        for dept_name in ["前厅部", "工程部", "其他"]:
            checks = data_fresh["by_dept"].get(dept_name, [])
            stale = [c for c in checks if not c["pass"]]
            if not stale:
                continue
            lines.append(f"**{dept_name}** ({len(stale)}项过期):")
            for s in stale:
                lines.append(f"  ⚠ {s['file']}: {s['age_hours']:.0f}h (阈值{s.get('max_hours', 0):.0f}h)")

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

    # 数据保鲜告警（过多过期项）
    stale_checks = [c for c in data_fresh["all_checks"] if not c["pass"]]
    if len(stale_checks) > 3:
        stale_summary = "\n".join(f"- {s['file']}: {s['age_hours']:.0f}h" for s in stale_checks)
        send_feishu_message("⚠ 数据保鲜告警", f"{len(stale_checks)} 项数据过期:\n{stale_summary}", chat_id="alerts")

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
