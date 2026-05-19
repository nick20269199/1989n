"""
Error auto-capture — wraps any script so the LAST error is always saved
to a known file. Claude reads that file instead of asking you to paste English.

Usage:
    from error_capture import trap
    trap()  # call once at script start

Or as decorator:
    from error_capture import capture_errors
    @capture_errors
    def main(): ...

After any crash, Claude reads:  D:/1989n/stock_data/last_error.txt
"""
import sys
import traceback
from datetime import datetime
from pathlib import Path

# 非交互运行时自动隐藏控制台窗口（定时任务触发时）
if sys.platform == "win32" and not sys.stdin.isatty():
    try:
        import ctypes
        ctypes.windll.user32.ShowWindow(
            ctypes.windll.kernel32.GetConsoleWindow(), 0  # SW_HIDE
        )
    except Exception:
        pass

ERROR_FILE = Path("D:/1989n/stock_data/last_error.txt")


def _save_error(exc_type, exc_value, exc_tb) -> None:
    """Save the full traceback to last_error.txt, then fire the KB hook."""
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    tb_text = "".join(tb_lines)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    script = Path(sys.argv[0]).name if sys.argv else "unknown"

    ERROR_FILE.parent.mkdir(parents=True, exist_ok=True)
    ERROR_FILE.write_text(
        f"=== LAST ERROR [{now}] ===\n"
        f"Script: {script}\n"
        f"Command: {' '.join(sys.argv)}\n\n"
        f"{tb_text}",
        encoding="utf-8",
    )

    # 同时写入会话追踪
    try:
        from session_tracker import record_error
        error_msg = tb_lines[-1].strip() if tb_lines else str(exc_value)
        record_error(f"{script}: {error_msg}")
    except Exception:
        pass

    # 错误→知识钩子：计算签名→匹配索引→写匹配报告
    try:
        from error_kb_hook import run_hook
        run_hook(exc_type, exc_value, script)
    except Exception:
        pass  # hook 失败不影响主流程


def trap() -> None:
    """Install global exception hook. Call once at script start."""
    sys.excepthook = _save_error


def capture_errors(func):
    """Decorator: wraps a function so exceptions are auto-logged."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            _save_error(exc_type, exc_value, exc_tb)
            raise
    return wrapper
