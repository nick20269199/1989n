"""
Final validation — 全持仓7只各3轮
"""
import sys, json, time, logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.WARNING)

from experts.lead import run_single, load_portfolio

holdings = load_portfolio()
RUNS = 3
print(f"=== Final Validation === {datetime.now().strftime('%H:%M:%S')}")
print(f"{len(holdings)} stocks × {RUNS} rounds = {len(holdings)*RUNS} runs\n")

all_scores = []
total_pass = 0
total_run = 0

for h in holdings:
    symbol, name = h["code"], h["name"]
    passes = 0
    scores = []
    repairs = []

    print(f"── {name}({symbol}) {'─'*30}")
    for i in range(1, RUNS + 1):
        t0 = time.time()
        try:
            p = run_single(symbol, name, mode="full")
            elapsed = time.time() - t0
            passed = p.get("pipeline_status") == "passed"
            score = p.get("grader", {}).get("score", 0)
            rr = p.get("repair_rounds", 0)
            if passed: passes += 1
            scores.append(score)
            repairs.append(rr)
            mark = "✅" if passed else "❌"
            print(f"  [{i}] score={score:.2f} repair={rr} ({elapsed:.0f}s) {mark}")
            if not passed:
                dims = p.get("grader", {}).get("scores", {})
                fails = p.get("grader", {}).get("failures", [])
                low_dims = {k:v for k,v in dims.items() if v < 0.6}
                print(f"      low={low_dims} fail={fails[0][:120] if fails else '?'}")
        except Exception as e:
            elapsed = time.time() - t0
            print(f"  [{i}] CRASH: {e} ({elapsed:.0f}s) 💥")

    total_pass += passes
    total_run += RUNS
    all_scores.extend(scores)
    pct = passes / RUNS * 100
    avg = sum(scores)/len(scores)
    avg_r = sum(repairs)/len(repairs)
    print(f"  → {pct:.0f}% pass, avg={avg:.3f}, repair={avg_r:.2f}\n")

import statistics
s = statistics.stdev(all_scores) if len(all_scores) > 1 else 0
print(f"{'='*50}")
print(f"结果: {total_pass}/{total_run} = {total_pass/total_run*100:.1f}%")
print(f"平均分: {sum(all_scores)/len(all_scores):.3f}")
print(f"最高分: {max(all_scores):.3f}")
print(f"最低分: {min(all_scores):.3f}")
print(f"标准差: {s:.4f}")
print(f"{'='*50}")
