"""
bot_v2_guardian.py — Bot v2 进程守护

每 5 分钟检查 bot 进程是否存活。
- 检查 STATE_FILE 的最后心跳时间
- 超时未更新 → 重启 run_feishu_bot_v2.bat
- 记录守护日志

由 Windows Task Scheduler 每 5 分钟触发。
"""
import json
import logging
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
STATE_FILE = PROJECT_DIR / "bot_v2_state.json"
GUARDIAN_LOG = PROJECT_DIR / "bot_v2_guardian.log"
BAT_FILE = PROJECT_DIR / "run_feishu_bot_v2.bat"

# 心跳超时: 如果 10 分钟未更新心跳 → 判定为死亡
HEARTBEAT_TIMEOUT_MINUTES = 10

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(GUARDIAN_LOG, encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot_guardian")


def _read_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text("utf-8"))
    except Exception:
        pass
    return {}


def _is_bot_alive(state: dict) -> bool:
    """检查 bot 是否存活 (最近 10 分钟有心跳)。"""
    last_hb = state.get("last_heartbeat", "")
    if not last_hb:
        return False
    try:
        hb_time = datetime.strptime(last_hb, "%Y-%m-%d %H:%M:%S")
        return datetime.now() - hb_time < timedelta(minutes=HEARTBEAT_TIMEOUT_MINUTES)
    except ValueError:
        return False


def _check_process_running() -> bool:
    """通过 tasklist 检查是否有 feishu_bot_v2.py 进程。"""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq python.exe", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=10
        )
        # 不精确但足够: 只要有 python 进程就假设 bot 可能活着
        # 实际判断依赖心跳时间
        return "python.exe" in result.stdout
    except Exception:
        return True  # 无法检查时不误杀


def _restart_bot() -> bool:
    """启动 bat 文件重启 bot。"""
    try:
        subprocess.Popen(
            ["cmd", "/c", str(BAT_FILE)],
            creationflags=subprocess.CREATE_NEW_CONSOLE,
            cwd=str(PROJECT_DIR),
        )
        logger.info("Bot restart command issued: %s", BAT_FILE)
        return True
    except Exception as e:
        logger.error("Failed to restart bot: %s", e)
        return False


def main():
    state = _read_state()

    if not state:
        logger.info("No state file found, starting bot for the first time...")
        _restart_bot()
        sys.exit(0)

    alive = _is_bot_alive(state)
    process_running = _check_process_running()

    logger.info(
        "Guardian check: alive=%s process_running=%s start_time=%s last_hb=%s reconnect=%s",
        alive, process_running,
        state.get("start_time", "?"),
        state.get("last_heartbeat", "?"),
        state.get("reconnect_count", "?"),
    )

    if alive:
        logger.info("Bot is alive, no action needed.")
        sys.exit(0)

    if not process_running:
        logger.warning("Bot process not found and heartbeat stale, restarting...")
        _restart_bot()
    elif not alive:
        logger.warning("Bot heartbeat stale but python process exists (may be stuck). Restarting...")
        _restart_bot()

    sys.exit(0)


if __name__ == "__main__":
    main()
