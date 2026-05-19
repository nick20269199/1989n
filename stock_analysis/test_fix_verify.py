"""
快速验证修复 — 重点攻击之前失败率最高的标的
"""
import sys, json, time, logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.WARNING)

from experts.lead import run_single

# 之前失败率最高的标的
TARGETS = [
    ("000981", "山子高科"),  # 之前 3/10 pass
    ("300792", "壹网壹创"),  # 尚未测试
    ("300136", "信维通信"),  # 尚未测试
]
RUNS = 5

all_results = {}

for symbol, name in TARGETS:
    print(f"── {name}({symbol}) {'─'*30}")
    stock_results = []
    passes = 0
    scores = []
    repairs = []

    for i in range(1, RUNS + 1):
        t0 = time.time()
        try:
            packet = run_single(symbol, name, mode="full")
            elapsed = time.time() - t0
            passed = packet.get("pipeline_status") == "passed"
            score = packet.get("grader", {}).get("score", 0)
            rr = packet.get("repair_rounds", 0)

            stock_results.append({
                "run": i, "passed": passed, "score": score,
                "repair": rr, "elapsed": round(elapsed, 1),
            })
            if passed: passes += 1
            scores.append(score)
            repairs.append(rr)

            mark = "✅" if passed else "❌"
            print(f"  [{i:02d}/{RUNS}] score={score:.2f} repair={rr} {'PASS' if passed else 'FAIL'} ({elapsed:.0f}s) {mark}")

            # Log detailed failure if failed
            if not passed:
                dims = packet.get("grader", {}).get("scores", {})
                fails = packet.get("grader", {}).get("failures", [])
                print(f"         dims={dims} fail={fails[:2]}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  [{i:02d}/{RUNS}] CRASH: {e} ({elapsed:.0f}s) 💥")
            stock_results.append({"run": i, "passed": False, "score": 0, "repair": -1, "error": str(e)})

    rate = passes / RUNS * 100
    avg = sum(scores)/len(scores) if scores else 0
    avg_r = sum(repairs)/len(repairs) if repairs else 0
    print(f"  → {name}: {passes}/{RUNS}={rate:.0f}% avg={avg:.3f} avg_repair={avg_r:.2f}\n")
    all_results[symbol] = {"name": name, "passes": passes, "total": RUNS, "avg_score": avg, "avg_repair": avg_r}

# Summary
print(f"{'='*50}")
print(f"汇总: {sum(r['passes'] for r in all_results.values())}/{sum(r['total'] for r in all_results.values())} passed")
for s, r in all_results.items():
    print(f"  {r['name']}({s}): {r['passes']}/{r['total']} avg={r['avg_score']:.3f} repair={r['avg_repair']:.2f}")
