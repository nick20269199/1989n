"""
20轮统计分析 — 每轮: start → 并发报错×3 → 查询验证 → end → 一致性检查
收集: 耗时分布 / 错误率 / zombie率 / 一致性异常
"""
import sys
import time
import json
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))
from session_tracker import (
    init_session_tracker, start_session, end_session,
    record_error, get_active_session, list_sessions, session_stats
)

DB_PATH = "D:/1989n/stock_data/stock.db"
RUNS = 20
CONCURRENT_ERRORS = 3  # 每轮并发报错数

metrics = {
    "start_ms": [],
    "error_ms": [],
    "end_ms": [],
    "errors_per_run": [],
    "anomalies": [],
    "zombies_detected": [],
}

def timed(op_name, func, *args):
    t0 = time.perf_counter()
    result = func(*args)
    elapsed = (time.perf_counter() - t0) * 1000
    metrics[f"{op_name}_ms"].append(elapsed)
    return result, elapsed

print(f"=== 20轮统计分析 === {datetime.now().strftime('%H:%M:%S')}")
print(f"DB: {DB_PATH}")
print(f"每轮并发报错: {CONCURRENT_ERRORS}\n")

init_session_tracker()

# 清理旧数据
conn = sqlite3.connect(DB_PATH)
conn.execute("DELETE FROM session_log")
conn.commit()
conn.close()

for run in range(1, RUNS + 1):
    print(f"--- 第{run:02d}轮 ---", end=" ")

    # 1. start
    sid, t_start = timed("start", start_session)
    print(f"start={sid[:20]}... {t_start:.1f}ms", end=" | ")

    # 2. 并发报错 (子进程模拟)
    t_err_total = 0
    procs = []
    for eid in range(CONCURRENT_ERRORS):
        code = f"""
import sys; sys.path.insert(0, r'{Path(__file__).parent}')
from session_tracker import record_error
record_error("第{run}轮-并发错误{eid}", "time={datetime.now()}")
"""
        p = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        procs.append(p)

    t0 = time.perf_counter()
    for p in procs:
        out, err = p.communicate(timeout=10)
        if p.returncode != 0:
            metrics["anomalies"].append(f"第{run}轮 并发进程{eid} 失败: {err.decode()[:100]}")
    t_err_total = (time.perf_counter() - t0) * 1000
    metrics["error_ms"].append(t_err_total / CONCURRENT_ERRORS)
    print(f"报错×{CONCURRENT_ERRORS} {t_err_total:.1f}ms", end=" | ")

    # 3. 验证
    session = get_active_session()
    if session is None:
        metrics["anomalies"].append(f"第{run}轮: get_active_session 返回 None!")
        print("NO_SESSION!", end=" | ")
        metrics["errors_per_run"].append(0)
    elif session["session_id"] != sid:
        metrics["anomalies"].append(
            f"第{run}轮: session_id 不匹配! 期望={sid[:20]}, 实际={session['session_id'][:20]}"
        )
        print("ID_MISMATCH!", end=" | ")
        metrics["errors_per_run"].append(session.get("error_count", 0))
    else:
        actual_errors = session.get("error_count", 0)
        metrics["errors_per_run"].append(actual_errors)
        if actual_errors != CONCURRENT_ERRORS:
            metrics["anomalies"].append(
                f"第{run}轮: error_count={actual_errors}, 期望{CONCURRENT_ERRORS} (并发丢记录)"
            )
            print(f"LOSS={CONCURRENT_ERRORS - actual_errors}!", end=" | ")
        else:
            print(f"OK errors={actual_errors}", end=" | ")

    # 4. end
    _, t_end = timed("end", end_session, sid)
    print(f"end {t_end:.1f}ms")

    # 5. 每5轮检查 zombie
    if run % 5 == 0:
        stats = session_stats()
        z = stats.get("zombie_sessions", 0)
        metrics["zombies_detected"].append(z)
        print(f"  [中期检查] total={stats['total_sessions']} active={stats['active_sessions']} zombie={z} errors_total={stats['total_errors_logged']}")

# === 统计分析 ===
print("\n" + "=" * 60)
print("20轮统计分析报告")
print("=" * 60)

def stats(nums, unit="ms"):
    if not nums:
        return "无数据"
    nums_sorted = sorted(nums)
    return {
        "count": len(nums),
        "min": min(nums),
        "max": max(nums),
        "mean": sum(nums) / len(nums),
        "p50": nums_sorted[len(nums_sorted)//2],
        "p95": nums_sorted[int(len(nums_sorted)*0.95)],
        "p99": nums_sorted[int(len(nums_sorted)*0.99)],
    }

print("\n--- 耗时分析 (ms) ---")
for op in ["start", "error", "end"]:
    s = stats(metrics[f"{op}_ms"])
    if isinstance(s, dict):
        print(f"  {op}: mean={s['mean']:.1f} p50={s['p50']:.1f} p95={s['p95']:.1f} p99={s['p99']:.1f} min={s['min']:.1f} max={s['max']:.1f}")

print("\n--- 报错完整性 ---")
err_counts = metrics["errors_per_run"]
loss_runs = [i+1 for i, c in enumerate(err_counts) if c != CONCURRENT_ERRORS]
if loss_runs:
    print(f"  丢记录轮次: {loss_runs} (共{len(loss_runs)}/{RUNS}轮)")
    print(f"  丢记录率: {len(loss_runs)/RUNS*100:.1f}%")
else:
    print(f"  全部完整: {RUNS}轮每轮{CONCURRENT_ERRORS}条错误无丢失")

print("\n--- 一致性异常 ---")
anomalies = metrics["anomalies"]
if anomalies:
    print(f"  异常数: {len(anomalies)}")
    for a in anomalies:
        print(f"  - {a}")
else:
    print("  零异常")

print("\n--- Zombie 统计 ---")
zombies = metrics["zombies_detected"]
if zombies:
    print(f"  各检查点: {zombies}")
    print(f"  平均zombie/检查: {sum(zombies)/len(zombies):.1f}")
else:
    print("  无zombie")

print("\n--- 总体判定 ---")
total_anomalies = len(anomalies) + len(loss_runs)
if total_anomalies == 0 and all(z == 0 for z in zombies):
    print("  PASS: 20轮零异常，数据完整，无zombie")
else:
    print(f"  ISSUES: {total_anomalies}个异常需要处理")

# 最终状态
print(f"\n最终DB状态: {session_stats()}")
print(f"20轮测试完成, 耗时数据已收集")
