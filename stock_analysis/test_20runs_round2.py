"""
第2轮20次 — 增加压力: 报错同时做查询操作，模拟真实并发竞争
每轮: start → (并发报错×3 + 并发查询×2 同时进行) → 验证 → end
"""
import sys
import time
import sqlite3
import subprocess
import threading
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
    "anomalies": [],
    "data_loss": 0,
    "id_conflicts": 0,
    "zombies": [],
}

init_session_tracker()
conn = sqlite3.connect(DB_PATH)
conn.execute("DELETE FROM session_log")
conn.commit()
conn.close()

print(f"=== 第2轮20次 (并发竞争) === {datetime.now().strftime('%H:%M:%S')}\n")

for run in range(1, RUNS + 1):
    sid = start_session()
    results_lock = threading.Lock()
    errors_in_run = []

    def do_error(eid):
        code = f"""
import sys; sys.path.insert(0, r'{Path(__file__).parent}')
from session_tracker import record_error
record_error("R2-{run}-错误{eid}")
"""
        r = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, timeout=10)
        with results_lock:
            errors_in_run.append(r.returncode)

    def do_query():
        """在报错过程中查询 session 状态 (制造读/写竞争)"""
        from session_tracker import get_active_session as gas
        for _ in range(5):
            gas()  # 读操作
            time.sleep(0.001)

    # 并发: 3个报错 + 2个查询 同时跑
    threads = []
    for eid in range(3):
        t = threading.Thread(target=do_error, args=(eid,))
        threads.append(t)
    for _ in range(2):
        t = threading.Thread(target=do_query)
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    # 验证
    failed_errors = sum(1 for rc in errors_in_run if rc != 0)
    if failed_errors > 0:
        metrics["anomalies"].append(f"R{run}: {failed_errors}个报错子进程失败")

    session = get_active_session()
    if session is None:
        metrics["anomalies"].append(f"R{run}: get_active_session=None!")
        metrics["data_loss"] += 1
    elif session["session_id"] != sid:
        metrics["anomalies"].append(f"R{run}: ID不匹配")
        metrics["id_conflicts"] += 1
    elif session["error_count"] != 3:
        metrics["anomalies"].append(f"R{run}: error_count={session['error_count']} 期望3")
        metrics["data_loss"] += 1

    end_session(sid)

    if run % 5 == 0:
        stats = session_stats()
        metrics["zombies"].append(stats.get("zombie_sessions", 0))
        print(f"  [{run:02d}/20] total={stats['total_sessions']} zombie={stats['zombie_sessions']} errors={stats['total_errors_logged']}")

# === 报告 ===
print(f"\n{'='*50}")
print(f"第2轮结果")
print(f"{'='*50}")
print(f"异常: {len(metrics['anomalies'])}")

if metrics["anomalies"]:
    for a in metrics["anomalies"]:
        print(f"  - {a}")
else:
    print("  零异常")

print(f"数据丢失: {metrics['data_loss']}轮")
print(f"ID冲突: {metrics['id_conflicts']}轮")
print(f"Zombie: {metrics['zombies']}")
print(f"\n最终: {session_stats()}")

verdict = "PASS" if len(metrics['anomalies']) == 0 else "ISSUES"
print(f"\n判定: {verdict}")
