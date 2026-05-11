"""
第3轮20次 — 刻意注入崩溃，验证 zombie 清理机制
每3轮: 创建一个 session → 报错 → 不关 (模拟崩溃)
下一轮: start_session 应自动清理 zombie
"""
import sys
import time
import sqlite3
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from session_tracker import (
    init_session_tracker, start_session, end_session,
    record_error, get_active_session, session_stats
)

DB_PATH = "D:/1989n/stock_data/stock.db"
RUNS = 20

metrics = {
    "crashes_simulated": 0,
    "zombie_cleanups": 0,
    "zombie_misses": 0,
    "anomalies": [],
}

init_session_tracker()
conn = sqlite3.connect(DB_PATH)
conn.execute("DELETE FROM session_log")
conn.commit()
conn.close()

print(f"=== 第3轮20次 (崩溃恢复) === {datetime.now().strftime('%H:%M:%S')}\n")

for run in range(1, RUNS + 1):
    # 每3轮模拟一次崩溃: 创建 session → 报错 → 不调用 end
    if run % 3 == 1 and run > 1:
        crash_sid = start_session()
        record_error(f"崩溃测试-第{run}轮")
        record_error(f"崩溃测试2-第{run}轮")
        # 不调 end_session — 模拟崩溃
        metrics["crashes_simulated"] += 1
        print(f"  [崩溃注入] sid={crash_sid[:20]}... 未关闭 (模拟进程崩溃)")

        # 验证 zombie 存在
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        zombie = conn.execute(
            "SELECT session_id, status FROM session_log WHERE status='active' LIMIT 1"
        ).fetchone()
        conn.close()
        if zombie:
            print(f"    僵尸确认: {zombie['session_id'][:20]}... status={zombie['status']}")
        else:
            metrics["anomalies"].append(f"崩溃注入{run}: 未检测到僵尸!")
            print(f"    警告: 僵尸未生成!")

    # 正常轮: start → 报错 → end
    sid = start_session()

    # 检查: start_session 是否自动清理了上轮的僵尸
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    zombies = conn.execute(
        "SELECT COUNT(*) as n FROM session_log WHERE status='zombie'"
    ).fetchone()["n"]
    conn.close()

    expected_zombies = metrics["crashes_simulated"]
    if zombies == expected_zombies:
        metrics["zombie_cleanups"] += 1
        if run % 5 == 0:
            print(f"  [{run:02d}/20] zombie数={zombies} (符合预期) total={session_stats()['total_sessions']}")
    elif zombies > expected_zombies:
        metrics["anomalies"].append(f"R{run}: zombie={zombies} > 预期{expected_zombies}")
        print(f"  [{run:02d}/20] 多余zombie! actual={zombies} expected={expected_zombies}")
    else:
        metrics["zombie_misses"] += 1
        # 可以容忍: 如果还没有崩溃注入
        if expected_zombies > 0:
            metrics["anomalies"].append(f"R{run}: zombie={zombies} < 预期{expected_zombies}")

    record_error(f"正常轮-{run}")
    s = get_active_session()
    if s is None or s["session_id"] != sid:
        metrics["anomalies"].append(f"R{run}: 僵尸干扰了正常session!")
    end_session(sid)

# === 报告 ===
print(f"\n{'='*50}")
print(f"第3轮结果 (崩溃恢复)")
print(f"{'='*50}")
print(f"模拟崩溃: {metrics['crashes_simulated']}次")
print(f"Zombie清理成功: {metrics['zombie_cleanups']}次")
print(f"Zombie遗漏: {metrics['zombie_misses']}次")
print(f"异常: {len(metrics['anomalies'])}")

if metrics["anomalies"]:
    for a in metrics["anomalies"]:
        print(f"  - {a}")
else:
    print("  零异常")

print(f"\n最终: {session_stats()}")

verdict = "PASS" if len(metrics['anomalies']) == 0 else "ISSUES"
print(f"判定: {verdict}")
