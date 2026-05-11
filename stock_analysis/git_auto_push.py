"""
自动推送 — 将每日产出推送到 GitHub
运行时机: 每天收盘后 (15:45) + 隔夜分析后 (23:45)
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_DIR = Path("D:/1989n")
LOG_FILE = Path("D:/1989n/stock_data/git_push.log")

def run(cmd: list[str], timeout: int = 60) -> tuple[int, str, str]:
    r = subprocess.run(cmd, cwd=REPO_DIR, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def main():
    now = datetime.now()
    log = LOG_FILE.open("a", encoding="utf-8")
    log.write(f"\n{'='*40}\n{now:%Y-%m-%d %H:%M} auto_push start\n")

    # 1. 拉取远程更新（防止冲突）
    code, out, err = run(["git", "pull", "--rebase"], timeout=30)
    if code != 0:
        log.write(f"PULL FAIL: {err}\n")
    else:
        log.write(f"PULL OK: {out}\n")

    # 2. 暂存所有变更（gitignore 已排除缓存/锁文件/密钥）
    code, out, err = run(["git", "add", "--all"], timeout=30)
    log.write(f"ADD: {out} {err}\n")

    # 3. 检查是否有变更
    code, out, err = run(["git", "diff", "--cached", "--quiet"])
    if code == 0:
        log.write("NOTHING TO COMMIT\n")
        log.close()
        return

    # 4. 提交
    msg = f"auto: {now:%Y-%m-%d %H:%M} daily outputs"
    code, out, err = run(["git", "commit", "-m", msg], timeout=30)
    if code != 0:
        log.write(f"COMMIT FAIL: {err}\n")
        log.close()
        return
    log.write(f"COMMIT OK: {out}\n")

    # 5. 推送
    code, out, err = run(["git", "push"], timeout=60)
    if code != 0:
        log.write(f"PUSH FAIL: {err}\n")
    else:
        log.write(f"PUSH OK: {out}\n")

    log.close()

if __name__ == "__main__":
    main()
