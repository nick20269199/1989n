#!/usr/bin/env python3
"""Agent 执行日志写入 — 供所有 Agent/Skill 调用结束时使用。

用法:
  import: from task_router.agent_exec_logger import log_execution
          log_execution(task="分析茅台", agent="stock-analysis", skill="stock-analysis",
                       exit_code=0, output_summary="返回技术面分析", output_hash="abc...")

  CLI:   python agent_exec_logger.py --task "分析茅台" --agent stock-analysis \
         --skill stock-analysis --exit_code 0 --summary "技术面分析" --hash "abc..."
"""
import json, sys, socket, os
from datetime import datetime, timezone
from pathlib import Path
from hashlib import sha256

LOG_BASE = Path("d:/1989n/logs/agent_exec")


def log_execution(*, task: str, agent: str, skill: str = "",
                  exit_code: int = 0, output_summary: str = "", output_hash: str = "") -> Path:
    """写入一条 Agent 执行日志。返回日志文件路径。"""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.isoformat()

    record = {
        "hostname": socket.gethostname(),
        "task": task,
        "agent": agent,
        "skill": skill,
        "start_time": time_str,
        "end_time": time_str,
        "exit_code": exit_code,
        "output_summary": output_summary[:200],
        "output_hash": output_hash if output_hash else sha256(output_summary.encode()).hexdigest(),
    }

    log_dir = LOG_BASE / date_str
    log_dir.mkdir(parents=True, exist_ok=True)

    log_file = log_dir / f"{agent}.json"
    records = []
    if log_file.exists():
        try:
            records = json.loads(log_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            records = []
        if not isinstance(records, list):
            records = [records]

    records.append(record)
    log_file.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return log_file


def cli():
    import argparse
    parser = argparse.ArgumentParser(description="Agent 执行日志写入")
    parser.add_argument("--task", required=True, help="原始任务描述")
    parser.add_argument("--agent", required=True, help="Agent 名称")
    parser.add_argument("--skill", default="", help="Skill 名称")
    parser.add_argument("--exit-code", type=int, default=0, help="退出码")
    parser.add_argument("--summary", default="", help="输出摘要 (≤200字)")
    parser.add_argument("--hash", default="", help="输出 sha256")
    args = parser.parse_args()

    path = log_execution(
        task=args.task,
        agent=args.agent,
        skill=args.skill,
        exit_code=args.exit_code,
        output_summary=args.summary,
        output_hash=args.hash,
    )
    print(f"日志已写入: {path}")


if __name__ == "__main__":
    cli()
