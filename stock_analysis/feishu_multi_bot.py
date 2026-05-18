"""
飞书多 Bot 启动器 — 同时运行 3 个 Bot 实例
每个 Bot 作为独立子进程运行，互不干扰
"""
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
PYTHON = r"D:\Python314\python.exe"

# 三个 Bot 配置
# 注：这些凭证来自用户截图的飞书开发者后台，用于多 Bot 并行接收消息
BOTS = [
    {
        "name": "街溜子",
        "env": {
            "FEISHU_APP_ID": "cli_a952c17c65f85cb2",
            "FEISHU_APP_SECRET": "weklMoClfUCJprDC1wNZUgbfiFRSDmin",
            "FEISHU_ENCRYPT_KEY": "",
            "FEISHU_BOT_CHAT_ID": "oc_983693a765e4284d1dc7bbeaf56cf1a9",
        },
    },
    {
        "name": "海盗船长",
        "env": {
            "FEISHU_APP_ID": "cli_a935549489381bc4",
            "FEISHU_APP_SECRET": "vaSeTzmLgyuDo5VlRIxvmcaehuqv6dHJ",
            "FEISHU_ENCRYPT_KEY": "",
            "FEISHU_BOT_CHAT_ID": "oc_983693a765e4284d1dc7bbeaf56cf1a9",
        },
    },
    {
        "name": "当前Bot",
        "env": {
            # 从 .env 读取默认值，这里留空触发 config.py 的逻辑
            "FEISHU_BOT_CHAT_ID": "oc_983693a765e4284d1dc7bbeaf56cf1a9",
        },
    },
]


def main():
    processes = []

    for bot in BOTS:
        name = bot["name"]
        bot_env = os.environ.copy()

        # Load .env file values first
        try:
            from dotenv import load_dotenv
            load_dotenv(PROJECT_DIR / ".env")
        except Exception:
            pass

        # Override with bot-specific env vars
        bot_env.update(bot["env"])

        # Ensure FEISHU_SEND_ENABLED is true
        bot_env["FEISHU_SEND_ENABLED"] = "true"

        # Set bot identity
        bot_env["BOT_NAME"] = name
        bot_env["BOT_LOG_FILE"] = str(PROJECT_DIR / f"bot_{name}.log")

        # 多 Bot 模式：街溜子主动回复，其他静默
        if name == "街溜子":
            bot_env["BOT_MODE"] = "primary"
        else:
            bot_env["BOT_MODE"] = "passive"

        print(f"[{name}] Starting...")
        proc = subprocess.Popen(
            [PYTHON, str(PROJECT_DIR / "feishu_bot.py")],
            env=bot_env,
            cwd=str(PROJECT_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append((name, proc))
        print(f"[{name}] PID {proc.pid}")
        time.sleep(2)  # 错开启动，避免同时连接

    print(f"\n=== {len(processes)} 个 Bot 已启动 ===")
    print("按 Ctrl+C 停止所有 Bot")

    try:
        # 等待所有子进程
        for name, proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        print("\n正在停止所有 Bot...")
        for name, proc in processes:
            proc.terminate()
        for name, proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        print("所有 Bot 已停止")


if __name__ == "__main__":
    main()
