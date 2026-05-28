#!/usr/bin/env python3
"""KAE 日频/周频/SEL 调度入口。

用法:
  python scheduler.py daily     # 日频: pipeline
  python scheduler.py weekly    # 周频: absorb --auto-execute
  python scheduler.py sel       # SEL 循环: lint→digest→...→distill_queue + 后处理
  python scheduler.py --help    # 帮助

Windows Task Scheduler 配置:
  日频: schtasks /create /tn KAE-Daily /tr "D:\\Python314\\python D:\\1989n\\stock_analysis\\scheduler.py daily" /sc daily /st 21:00
  周频: schtasks /create /tn KAE-Weekly /tr "D:\\Python314\\python D:\\1989n\\stock_analysis\\scheduler.py weekly" /sc weekly /d SUN /st 10:00
  SEL:  schtasks /create /tn KAE-SEL /tr "D:\\Python314\\python D:\\1989n\\stock_analysis\\scheduler.py sel" /sc daily /st 09:00
"""  # noqa
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE = Path("D:/1989n/stock_analysis")
PYTHON = "D:/Python314/python"
LOG_DIR = Path("D:/1989n/logs/kae")
LOG_DIR.mkdir(parents=True, exist_ok=True)


def run_cmd(cmd: list[str], log_name: str) -> int:
    """执行命令并写入日志文件。"""
    now = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = LOG_DIR / f"{log_name}_{now}.log"

    print(f"[scheduler] {now} - 执行: {' '.join(cmd)}")
    print(f"[scheduler] 日志: {log_file}")

    with open(log_file, "w", encoding="utf-8") as f:
        f.write(f"[{now}] 启动: {' '.join(cmd)}\n")
        f.flush()
        result = subprocess.run(
            cmd,
            cwd=str(BASE),
            capture_output=True,
            text=True,
            timeout=600,  # 最长10分钟
        )
        f.write(f"STDOUT:\n{result.stdout}\n")
        if result.stderr:
            f.write(f"STDERR:\n{result.stderr}\n")
        f.write(f"\nEXIT CODE: {result.returncode}\n")

    print(f"[scheduler] exit={result.returncode}")

    # 也打印到控制台
    if result.stdout:
        print(result.stdout[-500:])
    if result.stderr:
        print(f"[stderr] {result.stderr[:300]}")

    return result.returncode


def run_sel():
    """SEL 循环: 8 步顺序执行 + 3 步后处理。"""
    steps = [
        ("lint",         [PYTHON, "-m", "lint_wrapper"]),
        ("digest",       [PYTHON, "-m", "sel_digest"]),
        ("maintain",     [PYTHON, "-m", "sel_maintain"]),
        ("connect",      [PYTHON, "-m", "sel_connect"]),
        ("prune",        [PYTHON, "-m", "sel_prune"]),
        ("evolve_read",  [PYTHON, "-m", "sel_evolve_read"]),
        ("evolve_op",    [PYTHON, "-m", "sel_evolve_op"]),
        ("distill",      [PYTHON, "-m", "distill_queue"]),
    ]
    post_steps = [
        ("daily_compress", [PYTHON, "-m", "daily_compress_agent"]),
        ("watchdog",       [PYTHON, str(Path("D:/1989n/task-router/router_watchdog.py"))]),
        ("forecast_close", [PYTHON, "-m", "forecast_closer", "--report"]),
    ]

    all_ok = True
    for name, cmd in steps + post_steps:
        print(f"\n{'='*60}")
        code = run_cmd(cmd, log_name=f"sel_{name}")
        if code != 0:
            print(f"[sel] {name} 失败 (exit={code})")
            all_ok = False
        else:
            print(f"[sel] {name} 通过")
        print(f"{'='*60}")

    print(f"\n[sel] SEL 循环完成，整体状态: {'全部通过' if all_ok else '部分步骤失败'}")


def run_daily():
    """日频: 完整 KAE 管线 + Agent 模式扫描。"""
    code = run_cmd(
        [PYTHON, "-m", "knowledge_runner", "pipeline"],
        log_name="daily_pipeline",
    )
    if code == 0:
        run_cmd(
            [PYTHON, "-m", "sel_digest"],
            log_name="daily_digest",
        )
        from feishu_sender import send_daily_brief
        send_daily_brief()


def run_weekly():
    """周频: 吸收 + 自动执行提案。"""
    code = run_cmd(
        [PYTHON, "-m", "knowledge_runner", "absorb", "--auto-execute"],
        log_name="weekly_absorb",
    )
    if code == 0:
        run_cmd(
            [PYTHON, str(Path("D:/1989n/task-router/router_watchdog.py"))],
            log_name="weekly_watchdog",
        )
        from feishu_sender import send_deep_research
        send_deep_research()


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    mode = sys.argv[1]
    if mode == "daily":
        run_daily()
    elif mode == "weekly":
        run_weekly()
    elif mode == "sel":
        run_sel()
    else:
        print(f"[scheduler] 未知模式: {mode}", file=sys.stderr)
        print("用法: python scheduler.py [daily|weekly|sel]")
        sys.exit(1)
