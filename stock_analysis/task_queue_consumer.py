"""
task_queue_consumer.py — 任务队列消费器

每5分钟由 Windows Task Scheduler 触发:
  1. 扫描 task_queue.json 中所有 pending 任务
  2. 逐条调 task_router.py 获取分派方案
  3. 执行 Agent/Skill（或标记 needs_claude 留给主会话）
  4. 标记完成或失败

用法:
  python task_queue_consumer.py              # 正常执行
  python task_queue_consumer.py --dry-run    # 只预览不执行
"""

import json
import logging
import os
import re
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path("D:/1989n/stock_data")
PROJECT_DIR = Path(__file__).parent
PYTHON = r"D:\Python314\python"
TASK_QUEUE = STOCK_DATA / "task_queue.json"
ROUTER = Path("D:/1989n/task-router/task_router.py")
CONSUMER_LOG = STOCK_DATA / "consumer_log.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(STOCK_DATA / "consumer_run.log", encoding="utf-8")],
)
logger = logging.getLogger("task-consumer")


# ── 队列 IO ──

def read_queue() -> list[dict]:
    if not TASK_QUEUE.exists():
        return []
    try:
        return json.loads(TASK_QUEUE.read_text("utf-8"))
    except Exception as e:
        logger.error(f"读取队列失败: {e}")
        return []


def write_queue(tasks: list[dict]):
    TASK_QUEUE.write_text(json.dumps(tasks, ensure_ascii=False, indent=2), "utf-8")


def update_task(tasks: list[dict], task_id: str, task_raw: str, status: str, result: str = ""):
    """按 task_id + raw 更新任务状态（避免重复 ID 误更新）"""
    for t in tasks:
        if t["id"] == task_id and t.get("raw", "") == task_raw:
            t["status"] = status
            if result:
                t["result"] = result[:500]
            t["processed_at"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
            break


def append_log(entry: dict):
    CONSUMER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CONSUMER_LOG, "a", encoding="utf-8") as f:
        entry["_ts"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S")
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ── 任务路由 ──

def call_router(raw_text: str) -> dict:
    """调 task_router.py，返回路由结果"""
    try:
        result = subprocess.run(
            [PYTHON, str(ROUTER), raw_text],
            capture_output=True, text=True, timeout=30,
            cwd=str(PROJECT_DIR),
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout.strip())
        return {"status": "error", "reason": f"Router exit={result.returncode}: {result.stderr[:200]}"}
    except json.JSONDecodeError as e:
        return {"status": "error", "reason": f"Router JSON parse error: {e}"}
    except Exception as e:
        return {"status": "error", "reason": f"Router call failed: {e}"}


def run_agent(agent_name: str, task_raw: str) -> dict:
    """执行 Agent 脚本。按 agent 名映射到可执行脚本或技能。"""
    agent_map = {
        "code-reviewer": ["python", "-m", "code_review.cli"],
        "test-engineer": ["python", "-m", "pytest", "stock_analysis/tests/", "-x"],
        "architect": [PYTHON, str(PROJECT_DIR / "tools" / "architect_agent.py")],
        "data-verify": [PYTHON, str(PROJECT_DIR / "data_verify.py")],
    }
    cmd = agent_map.get(agent_name)
    if not cmd:
        return {"status": "skipped", "reason": f"Agent {agent_name} 无自动处理器，需主会话介入"}

    logger.info(f"  执行 Agent: {agent_name}")
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd=str(PROJECT_DIR))
        ok = proc.returncode == 0
        return {
            "status": "completed" if ok else "failed",
            "exit_code": proc.returncode,
            "output": (proc.stdout or "")[:300] + ("..." if proc.stdout and len(proc.stdout) > 300 else ""),
            "error": proc.stderr[:200] if proc.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "超时 (120s)"}
    except Exception as e:
        return {"status": "failed", "reason": str(e)}


def run_skill(skill_name: str, task_raw: str) -> dict:
    """执行 Skill。目前 Skill 需要 Claude 主会话介入，标记为 deferred。"""
    return {"status": "deferred", "reason": f"Skill {skill_name} 需主会话执行", "skill": skill_name, "task": task_raw}


# ── 内置处理器（当 router 返回 allow_direct 时）──

def _map_task_type(raw: str) -> str:
    """从原始文本识别任务类型"""
    if any(kw in raw for kw in ("背调", "背景调查", "调查", "尽调")):
        return "background_check"
    if any(kw in raw for kw in ("晨报", "盘前", "早报", "简报")):
        return "morning_brief"
    if any(kw in raw for kw in ("复盘", "收盘", "回顾")):
        return "closing_review"
    if any(kw in raw for kw in ("新想法", "想法", "优化止损", "规则", "策略")):
        return "rd_idea"
    if any(kw in raw for kw in ("查询", "查", "多少", "行情")):
        return "simple_query"
    return "general"


def execute_background_check(task: dict) -> dict:
    """背调 → 运行 expert lead pipeline"""
    code_match = re.search(r'\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b', task.get("raw", ""))
    name_match = re.search(r'[（(]?(\w+)[)）]', task.get("raw", "").split("背调")[-1] if "背调" in task.get("raw", "") else "")
    code = code_match.group(0) if code_match else ""
    name = task.get("raw", "").split("(")[1].split(")")[0] if "(" in task.get("raw", "") else ""

    if not code:
        return {"status": "failed", "reason": "未识别到股票代码"}

    logger.info(f"  执行背调: {name}({code})")
    cmd = [PYTHON, "-m", "stock_analysis.experts.lead", "--symbol", code]
    if name:
        cmd += ["--name", name]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=str(PROJECT_DIR))
        ok = proc.returncode == 0
        output = proc.stdout[-1000:] if proc.stdout else ""
        return {
            "status": "completed" if ok else "failed",
            "exit_code": proc.returncode,
            "summary": f"{name}({code}) 背调完成" if ok else f"背调失败: {proc.stderr[:200]}",
            "output_preview": output[:500],
        }
    except subprocess.TimeoutExpired:
        return {"status": "failed", "reason": "背调超时 (180s)"}
    except Exception as e:
        return {"status": "failed", "reason": str(e)}


def execute_morning_brief(task: dict) -> dict:
    """晨报 — 已由定时任务处理，跳过"""
    return {"status": "skipped", "reason": "晨报已由 StockAnalysis_MorningBrief 定时任务处理"}


def execute_closing_review(task: dict) -> dict:
    """复盘 — 已由定时任务处理，跳过"""
    return {"status": "skipped", "reason": "复盘已由 StockAnalysis_ClosingReview 定时任务处理"}


def execute_rd_idea(task: dict) -> dict:
    """新想法 — 需 Claude 深度参与，标记 deferred"""
    return {"status": "deferred", "reason": "研发想法需主会话 Claude 深度参与", "task": task.get("raw", "")}


def execute_simple_query(task: dict) -> dict:
    """简单查询 — 运行 data_source_router 直接查"""
    code_match = re.search(r'\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b', task.get("raw", ""))
    if not code_match:
        return {"status": "deferred", "reason": "未识别到股票代码，需主会话处理"}
    code = code_match.group(0)
    try:
        result = subprocess.run(
            [PYTHON, "-c", f"""
import json
from stock_analysis.data_source_router import get_quotes
q = get_quotes(["{code}"])
print(json.dumps(q.get("{code}", {{}}), ensure_ascii=False))
            """],
            capture_output=True, text=True, timeout=30, cwd=str(PROJECT_DIR),
        )
        if result.returncode == 0 and result.stdout.strip():
            return {"status": "completed", "data": result.stdout.strip()[:500]}
        return {"status": "failed", "reason": f"查询失败: {result.stderr[:200]}"}
    except Exception as e:
        return {"status": "failed", "reason": str(e)}


def execute_general(task: dict) -> dict:
    """通用 — 无法自动处理，标记 deferred"""
    return {"status": "deferred", "reason": "需主会话 Claude 处理", "task": task.get("raw", "")}


TASK_HANDLERS = {
    "background_check": execute_background_check,
    "morning_brief": execute_morning_brief,
    "closing_review": execute_closing_review,
    "rd_idea": execute_rd_idea,
    "simple_query": execute_simple_query,
    "general": execute_general,
}


# ── 主逻辑 ──

def process_task(task: dict, dry_run: bool = False) -> dict:
    """处理单条任务。"""
    task_id = task["id"]
    dept = task.get("dept", "?")
    raw = task.get("raw", "")
    logger.info(f"[{task_id}] {dept}: {task.get('task', '?')} | {raw[:60]}")

    if dry_run:
        logger.info(f"  [DRY-RUN] 跳过执行")
        return {"status": "dry_run", "task_id": task_id}

    # Step 1: 调 task_router
    route = call_router(raw)
    logger.info(f"  路由: {json.dumps(route, ensure_ascii=False)[:200]}")

    # Step 2: 按路由结果执行
    agents = route.get("agents", [])
    skills = route.get("skills", [])
    reason = route.get("reason", "")
    result = {"status": "unknown", "agents_results": [], "skills_results": []}

    if agents:
        for agent in agents:
            r = run_agent(agent, raw)
            result["agents_results"].append({"agent": agent, **r})
            result["status"] = "completed" if r["status"] == "completed" else result["status"]

    if skills:
        for skill in skills:
            r = run_skill(skill, raw)
            result["skills_results"].append({"skill": skill, **r})
            result["status"] = result.get("status", "deferred") if r["status"] == "deferred" else "completed"

    # Step 3: 无 Agent/Skill → 用内置处理器
    if not agents and not skills:
        task_type = _map_task_type(raw)
        logger.info(f"  内置处理器: {task_type}")
        handler = TASK_HANDLERS.get(task_type, execute_general)
        result = handler(task)
        result["task_type"] = task_type

    result["task_id"] = task_id
    return result


def run(dry_run: bool = False):
    """主函数：扫描队列，逐条处理。"""
    now = datetime.now(CST)
    logger.info(f"=== Consumer run at {now.strftime('%H:%M:%S')} (dry_run={dry_run}) ===")

    tasks = read_queue()
    if not tasks:
        logger.info("队列为空")
        return {"processed": 0, "tasks": []}

    pending = [t for t in tasks if t.get("status") == "pending"]
    logger.info(f"队列共 {len(tasks)} 条，其中 pending {len(pending)} 条")

    results = []
    for task in pending:
        try:
            result = process_task(task, dry_run)
        except Exception as e:
            logger.error(f"处理异常: {e}\n{traceback.format_exc()}")
            result = {"status": "failed", "reason": str(e), "task_id": task["id"]}

        results.append(result)

        if not dry_run:
            # 任务标记逻辑
            if result["status"] in ("completed", "skipped"):
                new_status = result["status"]
            elif result["status"] in ("deferred", "unknown"):
                # unknown = 被路由到 Agent 但无自动处理器 → 需主会话
                new_status = "needs_claude"
            elif result["status"] == "failed":
                new_status = "failed"
            else:
                new_status = "needs_claude"
            update_task(tasks, task["id"], task.get("raw", ""), new_status, json.dumps(result, ensure_ascii=False)[:500])

            append_log({
                "task_id": task["id"],
                "dept": task.get("dept", "?"),
                "status": new_status,
                "result_summary": result.get("summary", result.get("reason", result["status"])),
            })

    if not dry_run:
        write_queue(tasks)

    summary = {
        "processed": len(pending),
        "results": results,
    }
    logger.info(f"处理完成: {len(pending)} 条")
    for r in results:
        logger.info(f"  {r.get('task_id', '?')}: {r.get('status', '?')}")

    # 如果有 deferred 的任务，写入 claude_inbox.json 供主会话读取
    deferred = [r for r in results if r.get("status") == "deferred"]
    if deferred and not dry_run:
        inbox = []
        inbox_file = STOCK_DATA / "claude_inbox.json"
        if inbox_file.exists():
            try:
                inbox = json.loads(inbox_file.read_text("utf-8"))
            except Exception:
                pass
        for d in deferred:
            inbox.append({
                "source": "task_consumer",
                "task_id": d.get("task_id"),
                "reason": d.get("reason", ""),
                "task": d.get("task", ""),
                "created": datetime.now(CST).strftime("%Y-%m-%d %H:%M:%S"),
            })
        inbox_file.write_text(json.dumps(inbox, ensure_ascii=False, indent=2), "utf-8")
        logger.info(f"写入 {len(deferred)} 条到 claude_inbox.json")

    return summary


def main():
    import argparse
    parser = argparse.ArgumentParser(description="任务队列消费器")
    parser.add_argument("--dry-run", action="store_true", help="只预览不执行")
    args = parser.parse_args()
    summary = run(dry_run=args.dry_run)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
