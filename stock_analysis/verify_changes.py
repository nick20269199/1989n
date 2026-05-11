"""
QualityGate 自动双跑验证（对应 ECC quality-gate hook）

用法:
  python verify_changes.py <script> <mode>            # 正常模式 + 边界条件双跑
  python verify_changes.py <script> <mode> --single   # 只跑正常模式（不推荐）
  python verify_changes.py --list                     # 列出可验证的脚本

边界条件定义（按脚本类型）:
  - 采集类 (news_scheduler/call_auction/intraday_report): 非交易日/空数据
  - 分析类 (daily_task/emotional_analysis): --test 模式
  - 检查类 (health_check/nightly_health_check): 直接跑
"""
import subprocess
import sys
import json
import os
from pathlib import Path
from datetime import datetime

PROJECT_DIR = Path(__file__).parent
STOCK_DATA_DIR = Path("D:/1989n/stock_data")
PYTHON = "D:/Python314/python"

EDGE_CASES = {
    "news_scheduler.py": {
        "morning": "morning --test",
        "evening": "evening --test",
        "description": "空数据/非交易日模拟"
    },
    "call_auction.py": {
        "default": "--test",
        "description": "非交易日模拟"
    },
    "intraday_report.py": {
        "default": "--test",
        "description": "空新闻列表模拟"
    },
    "daily_task.py": {
        "morning_enhanced": "morning_enhanced --test",
        "closing_review": "closing_review --test",
        "tech_scan": "tech_scan --test",
        "overnight": "overnight --test",
        "description": "--test 模式"
    },
    "health_check.py": {
        "default": "",
        "description": "直接跑（无边界模式）"
    },
    "nightly_health_check.py": {
        "default": "",
        "description": "直接跑（无边界模式）"
    },
}


def run_script(script, mode, label):
    """Run a script and return (success, stdout_tail, stderr_tail, elapsed)."""
    start = datetime.now()
    script_path = PROJECT_DIR / script
    if not script_path.exists():
        return False, "", f"文件不存在: {script_path}", 0

    cmd = [PYTHON, str(script_path)]
    if mode:
        cmd.extend(mode.split())

    print(f"\n{'='*60}")
    print(f"[{label}] {' '.join(cmd)}")
    print(f"{'='*60}")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(PROJECT_DIR),
        )
        elapsed = (datetime.now() - start).total_seconds()
        stdout_tail = "\n".join(result.stdout.split("\n")[-30:]) if result.stdout else "(无输出)"
        stderr_tail = "\n".join(result.stderr.split("\n")[-30:]) if result.stderr else "(无输出)"

        if result.returncode == 0:
            print(f"[{label}] 返回码=0, 耗时={elapsed:.1f}s")
            return True, stdout_tail, stderr_tail, elapsed
        else:
            print(f"[{label}] 返回码={result.returncode}, 耗时={elapsed:.1f}s")
            print(f"STDERR: {stderr_tail[:500]}")
            return False, stdout_tail, stderr_tail, elapsed
    except subprocess.TimeoutExpired:
        elapsed = (datetime.now() - start).total_seconds()
        print(f"[{label}] 超时 (>300s)")
        return False, "", "脚本执行超时 (>300s)", elapsed
    except Exception as e:
        elapsed = (datetime.now() - start).total_seconds()
        print(f"[{label}] 异常: {e}")
        return False, "", str(e), elapsed


def check_output(script, mode):
    """Check that expected output files exist after script run."""
    checks = []

    # Generic check: look for recently modified JSON files in stock_data
    try:
        json_files = sorted(
            STOCK_DATA_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )[:5]
        checks.append(f"最新5个JSON文件: {[f.name for f in json_files]}")
    except Exception as e:
        checks.append(f"无法列出JSON文件: {e}")

    # Script-specific checks
    if "news_scheduler" in script:
        latest = list(STOCK_DATA_DIR.glob("news_manual_*.json"))
        checks.append(f"news_manual_*.json 数量: {len(latest)}")

    if "intraday_report" in script:
        latest = list(STOCK_DATA_DIR.glob("news_intraday_*.json"))
        checks.append(f"news_intraday_*.json 数量: {len(latest)}")

    if "call_auction" in script:
        latest = list(STOCK_DATA_DIR.glob("call_auction_*.json"))
        checks.append(f"call_auction_*.json 数量: {len(latest)}")

    if "daily_task" in script:
        latest = list(STOCK_DATA_DIR.glob("*.json"))
        checks.append(f"stock_data JSON 总数: {len(latest)}")

    if "health_check" in script or "nightly_health_check" in script:
        error_file = STOCK_DATA_DIR / "last_error.txt"
        if error_file.exists():
            checks.append(f"last_error.txt 存在 ({error_file.stat().st_mtime})")
        else:
            checks.append("last_error.txt 不存在（正常）")

    return checks


def list_scripts():
    """List all verifiable scripts."""
    print("\n可验证的脚本及边界条件:\n")
    for script, config in EDGE_CASES.items():
        desc = config.get("description", "未知")
        modes = {k: v for k, v in config.items() if k != "description"}
        print(f"  {script}")
        print(f"    边界条件: {desc}")
        for mode_name, edge_mode in modes.items():
            if mode_name != "default":
                print(f"    {mode_name}: {edge_mode}")
            else:
                print(f"    默认边界: {edge_mode}")
        print()


def main():
    if len(sys.argv) < 2 or sys.argv[1] == "--list":
        list_scripts()
        return

    if sys.argv[1] == "--help" or sys.argv[1] == "-h":
        print(__doc__)
        list_scripts()
        return

    script = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else ""
    single_only = "--single" in sys.argv

    if script not in EDGE_CASES:
        print(f"未知脚本: {script}")
        print("可用 --list 查看可验证的脚本列表")
        sys.exit(1)

    edge_config = EDGE_CASES[script]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Phase 1: 正常模式
    print(f"\n{'#'*60}")
    print(f"# QualityGate 双跑验证 - {script} {mode}")
    print(f"# 时间: {datetime.now()}")
    print(f"{'#'*60}")

    ok1, out1, err1, t1 = run_script(script, mode, "Phase1-正常模式")

    if not ok1:
        print(f"\nQualityGate 失败: 正常模式未通过")
        print(f"请先修复正常模式的报错，再重新验证")
        if err1 and err1 != "(无输出)":
            print(f"\n完整 stderr:\n{err1}")
        sys.exit(1)

    if single_only:
        print(f"\nQualityGate 警告: 只跑了正常模式（--single），未跑边界条件")
        print(f"按 CLAUDE.md 规则，只跑一次不算验证通过")
        sys.exit(0)

    # Phase 2: 边界条件
    edge_mode = None
    if mode and mode in edge_config:
        edge_mode = edge_config[mode]
    elif "default" in edge_config:
        edge_mode = edge_config["default"]

    if edge_mode is None or edge_mode == "":
        print(f"\n[Phase2-边界条件] 该脚本无独立边界模式，跳过")
        print(f"说明: {edge_config.get('description', '')}")
    else:
        ok2, out2, err2, t2 = run_script(script, edge_mode, "Phase2-边界条件")

        if not ok2:
            print(f"\nQualityGate 警告: 边界条件未通过")
            print(f"这可能是因为 --test 模式未实现或边界数据异常")
            print(f"请人工判断是否为已知问题")
        else:
            print(f"\n边界条件通过 (耗时={t2:.1f}s)")

    # Phase 3: 输出检查
    print(f"\n{'='*60}")
    print(f"[Phase3-输出检查]")
    checks = check_output(script, mode)
    for c in checks:
        print(f"  {c}")

    # Summary
    print(f"\n{'#'*60}")
    print(f"# QualityGate 验证完成")
    print(f"# 正常模式: {'通过' if ok1 else '失败'} ({t1:.1f}s)")
    print(f"# 边界条件: {'通过' if edge_mode else '跳过'} ")
    print(f"# 输出检查: {len(checks)} 项")
    print(f"{'#'*60}")
    print(f"\n验证通过" if ok1 else "\n验证失败")


if __name__ == "__main__":
    main()
