"""
import_gate.py — 语法门禁

每次修改 .py 文件后自动 compile() 检查语法。
防止引号不匹配、缩进错误、非法语法等低级 bug 进入代码库。

用法:
    python tools/import_gate.py                    # 全量扫描所有 .py
    python tools/import_gate.py --changed-only      # 只扫描 git 变更的文件
    python tools/import_gate.py --json              # JSON 格式输出 (给 hook 用)
"""
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "venv", ".pytest_cache"}
EXCLUDE_PREFIXES = {".", "_"}  # 以 . 或 _ 开头的目录


def _should_skip(py_file: Path) -> bool:
    """判断是否应跳过该文件。"""
    for parent in py_file.parents:
        if parent.name in EXCLUDE_DIRS:
            return True
        if parent.name.startswith(tuple(EXCLUDE_PREFIXES)) and parent != BASE_DIR:
            return True
    return False


SCOPE_DIRS = [BASE_DIR]  # 限定扫描范围


def check_syntax(py_files: list[Path]) -> list[dict]:
    """对一组 .py 文件做 compile() 检查，返回失败列表。"""
    failures = []
    for f in sorted(py_files):
        if _should_skip(f):
            continue
        if not f.exists():
            continue
        # 只在限定范围内扫描
        if not any(f.is_relative_to(d) for d in SCOPE_DIRS):
            continue
        try:
            compile(f.read_text(encoding="utf-8"), str(f), "exec")
        except SyntaxError as e:
            rel = f.relative_to(BASE_DIR) if f.is_relative_to(BASE_DIR) else f
            failures.append({
                "file": str(rel).replace("\\", "/"),
                "line": e.lineno or 0,
                "msg": e.msg or "",
                "text": (e.text or "").strip(),
            })
    return failures


def get_changed_py_files() -> list[Path]:
    """通过 git diff 获取当前变更/未跟踪的 .py 文件。"""
    files = []
    # git 根目录
    git_root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, cwd=BASE_DIR, timeout=10,
    ).stdout.strip()
    git_root = Path(git_root)

    # 已暂存 + 未暂存的变更
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True, text=True, cwd=BASE_DIR, timeout=10,
    )
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line.endswith(".py"):
            files.append(git_root / line)

    # 未跟踪的文件
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True, text=True, cwd=BASE_DIR, timeout=10,
    )
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line.endswith(".py"):
            files.append(git_root / line)

    return list(set(files))


def get_all_py_files() -> list[Path]:
    """递归获取所有 .py 文件。"""
    return list(BASE_DIR.rglob("*.py"))


def scan_all() -> list[dict]:
    """全量扫描所有 .py 文件。"""
    return check_syntax(get_all_py_files())


def scan_changed() -> list[dict]:
    """只扫描 git 变更的 .py 文件。"""
    changed = get_changed_py_files()
    if not changed:
        return []
    return check_syntax(changed)


# ── 路径拼接检查 ──
# 只匹配文件系统路径 (排除 https:// 等 URL)
PATH_BUG_PATTERNS = [
    # os.path.join(base, "/absolute/path") — 第二个参数以 / 开头丢弃 base 目录
    (r'os\.path\.join\([^,]+,\s*["\']/', "os.path.join 第二参数以 / 开头 (绝对路径会丢弃基础目录)"),
    # Path(base) / "/absolute" — 同上
    (r'Path\([^)]+\)\s*/\s*["\']/', "Path / 操作符右侧以 / 开头 (路径拼接错误)"),
    # 数据文件写入到源码目录 (排除 stock_analysis/data/ 子目录，这是约定的配置数据目录)
    (r'["\'][Dd]:[/\\]1989n[/\\]stock_analysis[/\\](?!data[/\\])[^"\']*\.(?:json|csv|db|txt)', "数据文件写入到源码目录 (应写入 stock_data/)"),
    # 路径中明显的双分隔符 (如 D:/1989n//stock_data)，排除 URL
    (r'["\'][A-Za-z]:[/\\]{2,}[^"\']*\.(?:json|csv|db|txt|py|bat)', "文件路径含双分隔符"),
]


def scan_path_issues(py_files: list[Path]) -> list[dict]:
    """扫描 Python 文件中的路径拼接问题。"""
    import re
    issues = []
    for f in sorted(py_files):
        if _should_skip(f) or not f.exists():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for pattern, desc in PATH_BUG_PATTERNS:
                if re.search(pattern, line):
                    # 跳过明显的注释行和字符串定义行
                    stripped = line.strip()
                    if stripped.startswith("#") or stripped.startswith('"""') or stripped.startswith("'''"):
                        continue
                    if "PATH_BUG_PATTERNS" in stripped:  # 不检查自身定义
                        continue
                    rel = f.relative_to(BASE_DIR) if f.is_relative_to(BASE_DIR) else f
                    issues.append({
                        "file": str(rel).replace("\\", "/"),
                        "line": line_no,
                        "msg": desc,
                        "text": stripped[:120],
                    })
                    break  # 每行只报一次
    return issues


def scan_path_all() -> list[dict]:
    """全量路径扫描。"""
    return scan_path_issues(get_all_py_files())


def main():
    import json

    as_json = "--json" in sys.argv
    changed_only = "--changed-only" in sys.argv
    path_check = "--path" in sys.argv

    # 路径检查
    if path_check:
        path_issues = scan_path_all()
        if as_json:
            print(json.dumps({
                "gate": "import_path",
                "passed": len(path_issues) == 0,
                "failures": len(path_issues),
                "details": path_issues,
            }, ensure_ascii=False))
        else:
            if not path_issues:
                print(f"[IMPORT_GATE:PATH] 全部通过")
            else:
                print(f"[IMPORT_GATE:PATH] 发现 {len(path_issues)} 个路径问题:")
                for pi in path_issues:
                    print(f"  ✗ {pi['file']}:{pi['line']}  {pi['msg']}")
                    print(f"    -> {pi['text']}")
        sys.exit(0 if not path_issues else 1)

    if changed_only:
        failures = scan_changed()
    else:
        failures = scan_all()

    total_scanned = "N/A" if changed_only else len(list(BASE_DIR.rglob("*.py")))

    if as_json:
        print(json.dumps({
            "gate": "import_syntax",
            "passed": len(failures) == 0,
            "failures": len(failures),
            "details": failures,
        }, ensure_ascii=False))
    else:
        if not failures:
            print(f"[IMPORT_GATE] 全部通过 (scanned={total_scanned})")
        else:
            print(f"[IMPORT_GATE] 发现 {len(failures)} 个语法错误:")
            for f in failures:
                print(f"  ✗ {f['file']}:{f['line']}  {f['msg']}")
                if f['text']:
                    print(f"    -> {f['text']}")

    sys.exit(0 if not failures else 1)


if __name__ == "__main__":
    main()
