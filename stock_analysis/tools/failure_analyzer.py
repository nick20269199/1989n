"""
failure_analyzer.py — 命令失败根因分析

PostToolUseFailure hook 调用，分析 Bash 命令失败的原因。
输出结构化诊断到 stderr 和 last_error.txt。
"""
import re
import sys
from datetime import datetime
from pathlib import Path

ERROR_LOG = Path("D:/1989n/stock_data/last_error.txt")


def analyze(stderr: str, command: str = "") -> dict:
    """分析失败命令的 stderr，返回结构化根因。"""
    result = {
        "category": "unknown",
        "confidence": "low",
        "detail": "",
        "file": "",
        "line": 0,
    }

    # 类型 1: 语法错误 — 取 SyntaxError: 到行尾的全部文字
    m = re.search(r'SyntaxError:\s*(.+?)$', stderr, re.MULTILINE)
    if m:
        result["category"] = "syntax_error"
        result["confidence"] = "high"
        detail = m.group(1).strip()
        # 从 traceback 中找文件名和行号
        fm = re.search(r'File\s+\"(.+?)\",\s*line\s*(\d+)', stderr)
        if fm:
            result["file"] = fm.group(1).strip()
            result["line"] = int(fm.group(2))
        result["detail"] = detail
        return result

    # 类型 3: ImportError / ModuleNotFoundError
    m = re.search(r'ModuleNotFoundError:\s*No module named [\'"](.+?)[\'"]', stderr)
    if m:
        result["category"] = "missing_module"
        result["confidence"] = "high"
        result["detail"] = f"缺少模块: {m.group(1)}"
        return result

    # 类型 4: ImportError (其他)
    m = re.search(r'ImportError:\s*(.+?)(?:\n|$)', stderr)
    if m:
        result["category"] = "import_error"
        result["confidence"] = "high"
        result["detail"] = m.group(1).strip()
        return result

    # 类型 5: FileNotFoundError
    m = re.search(r'FileNotFoundError:\s*(.+?)(?:\n|$)', stderr)
    if m:
        result["category"] = "file_not_found"
        result["confidence"] = "high"
        result["detail"] = m.group(1).strip()
        return result

    # 类型 6: KeyError / AttributeError / TypeError
    m = re.search(r'(KeyError|AttributeError|TypeError|ValueError):\s*(.+?)(?:\n|$)', stderr)
    if m:
        result["category"] = "runtime_error"
        result["confidence"] = "high"
        result["detail"] = f"{m.group(1)}: {m.group(2).strip()}"
        return result

    # 类型 7: 命令未找到
    if re.search(r'command not found|not recognized', stderr, re.IGNORECASE):
        result["category"] = "command_not_found"
        result["confidence"] = "high"
        result["detail"] = f"命令不存在: {command[:100]}"
        return result

    # 类型 8: 超时
    if "Timeout" in stderr:
        result["category"] = "timeout"
        result["confidence"] = "medium"
        result["detail"] = "命令执行超时"
        return result

    return result


def write_error_log(analysis: dict, command: str):
    """将分析结果写入 last_error.txt。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ERROR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"\n{'='*60}\n")
        f.write(f"[{timestamp}] failure_analyzer 诊断\n")
        f.write(f"命令: {command[:200]}\n")
        f.write(f"根因类别: {analysis['category']}\n")
        f.write(f"置信度: {analysis['confidence']}\n")
        if analysis["detail"]:
            f.write(f"详情: {analysis['detail']}\n")
        if analysis["file"]:
            f.write(f"文件: {analysis['file']}:{analysis['line']}\n")
        f.write(f"{'='*60}\n")


def main():
    import json

    stderr = ""
    command = ""
    from_file = False

    # 从参数解析
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--stderr" and i + 1 < len(args):
            stderr = args[i + 1]
            i += 2
        elif args[i] == "--cmd" and i + 1 < len(args):
            command = args[i + 1]
            i += 2
        elif args[i] == "--from-file":
            from_file = True
            i += 1
        else:
            i += 1

    if from_file:
        # 从 last_error.txt 读最近一条错误
        if ERROR_LOG.exists():
            content = ERROR_LOG.read_text(encoding="utf-8")
            # 取最后一段错误 (以 === 分隔)
            parts = content.split("=" * 60)
            if parts:
                stderr = parts[-1].strip()
        if not stderr:
            print(json.dumps({
                "systemMessage": "命令失败了。先读 last_error.txt 追踪调用链找到根因，再修。不要跳过查因直接改代码。",
            }, ensure_ascii=False))
            return

    # 如果没传 --stderr，从 stdin 读
    if not stderr and not sys.stdin.isatty():
        stderr = sys.stdin.read()

    analysis = analyze(stderr, command)

    print(json.dumps({
        "systemMessage": (
            f"命令失败了。failure_analyzer 诊断: [{analysis['category']}] "
            f"{analysis['detail']}。"
            f"先读 last_error.txt 追踪调用链找到根因，再修。"
        ),
        "diagnosis": analysis,
    }, ensure_ascii=False))

    write_error_log(analysis, command)
    sys.exit(0)


if __name__ == "__main__":
    main()
