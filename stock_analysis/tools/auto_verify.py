"""
auto_verify.py — 交付自验门禁

改代码后自动跑关联测试。通过文件→测试映射表确定跑哪些测试。
由 PostToolUse hook 在 import_gate 之后调用。
"""
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
PYTHON = "D:/Python314/python"

# 文件 → 测试文件映射表
# key: 项目相对路径, value: 对应的测试文件列表
TEST_MAP: dict[str, list[str]] = {
    "experts/grader.py": ["tests/test_grader.py"],
    "data_quality_gate.py": ["tests/test_data_quality_gate.py"],
    "feishu_sender.py": ["tests/test_feishu_router.py"],
    "conversation_miner.py": ["tests/test_conversation_miner.py"],
    "daily_task.py": [
        "tests/test_portfolio_loader.py",
        "tests/test_hot_stocks_pipeline.py",
    ],
    # 影响面大的模块 — 全量测试
    "database.py": ["tests/"],
    # 工程部门禁工具 — 真实数据冒烟覆盖校验
    "tools/schema_gate.py": ["tests/test_real_data.py"],
    "tools/consistency_gate.py": ["tests/test_real_data.py"],
    "tools/import_gate.py": ["tests/"],
    "tools/failure_analyzer.py": ["tests/"],
    "tools/bug_pattern_miner.py": ["tests/"],
    "tools/auto_verify.py": ["tests/"],
    "tools/_trade_analysis.py": [
        "tests/test_portfolio_loader.py",
        "tests/test_real_data.py",
    ],
    "health_check.py": ["tests/test_real_data.py"],
    "nightly_health_check.py": ["tests/test_real_data.py"],
}


def find_matching_tests(changed_file: str) -> list[str]:
    """根据变更文件找到关联测试。"""
    # 精确匹配
    if changed_file in TEST_MAP:
        return TEST_MAP[changed_file]

    # 后缀匹配 (如 tools/xxx.py 没有专门测试)
    return []


def get_changed_files_from_git() -> list[str]:
    """从 git diff 获取变更的文件列表。"""
    files = []
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, cwd=BASE_DIR, timeout=10,
    )
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            files.append(line)

    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=BASE_DIR, timeout=10,
    )
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            files.append(line)

    return list(set(files))


def run_tests(test_paths: list[str]) -> list[dict]:
    """运行指定测试，返回每个的结果。"""
    results = []
    for tp in test_paths:
        full_path = str(BASE_DIR / tp) if not tp.startswith(str(BASE_DIR)) else tp
        try:
            proc = subprocess.run(
                [PYTHON, "-m", "pytest", full_path, "-x", "-q"],
                capture_output=True, text=True, timeout=120, cwd=BASE_DIR,
            )
            passed = proc.returncode == 0
            # 提取关键信息
            output_lines = proc.stdout.strip().splitlines()
            summary = [l for l in output_lines if "passed" in l or "failed" in l or "error" in l]
            results.append({
                "test": tp,
                "passed": passed,
                "summary": summary[-1] if summary else ("通过" if passed else "失败"),
                "returncode": proc.returncode,
            })
        except subprocess.TimeoutExpired:
            results.append({
                "test": tp,
                "passed": False,
                "summary": "超时 (>120s)",
                "returncode": -1,
            })
    return results


def main():
    import json

    changed_file = ""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--changed-file" and i + 1 < len(args):
            changed_file = args[i + 1]

    # 如果没指定文件，从 git diff 检测
    if not changed_file:
        all_changed = get_changed_files_from_git()
    else:
        all_changed = [changed_file]

    # 收集所有需跑的测试
    tests_to_run = []
    for f in all_changed:
        tests_to_run.extend(find_matching_tests(f))
    tests_to_run = list(set(tests_to_run))

    if not tests_to_run:
        print(json.dumps({
            "gate": "auto_verify",
            "triggered": False,
            "changed_files": all_changed,
            "tests_run": 0,
            "message": "无关联测试，跳过",
        }, ensure_ascii=False))
        return

    results = run_tests(tests_to_run)
    all_passed = all(r["passed"] for r in results)

    # 输出结构
    report = {
        "gate": "auto_verify",
        "triggered": True,
        "changed_files": all_changed,
        "tests_run": len(results),
        "all_passed": all_passed,
        "results": results,
    }

    if all_passed:
        report["message"] = f"全部 {len(results)} 个测试通过"
    else:
        failed = [r for r in results if not r["passed"]]
        report["message"] = f"{len(failed)}/{len(results)} 个测试失败"
        report["details"] = [r for r in results if not r["passed"]]

    print(json.dumps(report, ensure_ascii=False))
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
