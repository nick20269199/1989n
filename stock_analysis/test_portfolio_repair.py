"""
Portfolio-wide expert repair test — 全持仓多轮扫描，暴露修复循环的边界case
"""
import sys, json, time, logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.WARNING)

from experts.lead import run_single, load_portfolio

RUNS_PER_STOCK = 10

holdings = load_portfolio()
print(f"=== Portfolio 修复循环压力测试 === {datetime.now().strftime('%H:%M:%S')}")
print(f"持仓: {len(holdings)}只, 每只{RUNS_PER_STOCK}轮, 共{len(holdings)*RUNS_PER_STOCK}轮\n")

all_results = {}
summary = {}

for h in holdings:
    symbol = h["code"]
    name = h["name"]
    stock_results = []
    passed = 0
    failed = 0
    repair_0 = 0
    repair_ok = 0
    repair_fail = 0
    scores = []
    errors = []

    print(f"── {name}({symbol}) {'─'*30}")

    for i in range(1, RUNS_PER_STOCK + 1):
        t0 = time.time()
        try:
            packet = run_single(symbol, name, mode="full")
            elapsed = time.time() - t0
            passed_flag = packet.get("pipeline_status") == "passed"
            score = packet.get("grader", {}).get("score", 0)
            rr = packet.get("repair_rounds", 0)

            stock_results.append({
                "run": i, "passed": passed_flag, "score": score,
                "repair_rounds": rr, "elapsed": round(elapsed, 1),
            })

            if passed_flag:
                passed += 1
            else:
                failed += 1
            if rr == 0:
                repair_0 += 1
            elif passed_flag:
                repair_ok += 1
            else:
                repair_fail += 1
            scores.append(score)

            mark = "✅" if passed_flag else "❌"
            print(f"  [{i:02d}/{RUNS_PER_STOCK}] score={score:.2f} repair={rr} {'PASS' if passed_flag else 'FAIL'} ({elapsed:.0f}s) {mark}")

        except Exception as e:
            elapsed = time.time() - t0
            print(f"  [{i:02d}/{RUNS_PER_STOCK}] CRASH: {type(e).__name__}: {e} ({elapsed:.0f}s) 💥")
            errors.append({"run": i, "error": str(e)})
            stock_results.append({"run": i, "passed": False, "score": 0, "repair_rounds": -1, "error": str(e)})

    avg_score = sum(scores) / len(scores) if scores else 0
    summary[symbol] = {
        "name": name, "runs": RUNS_PER_STOCK,
        "passed": passed, "failed": failed,
        "repair_0": repair_0, "repair_ok": repair_ok, "repair_fail": repair_fail,
        "avg_score": round(avg_score, 3),
        "max_score": max(scores) if scores else 0,
        "min_score": min(scores) if scores else 0,
        "errors": len(errors),
    }
    all_results[symbol] = stock_results

    pass_rate = passed / RUNS_PER_STOCK * 100
    print(f"  → {name}: {passed}/{RUNS_PER_STOCK} = {pass_rate:.0f}%, avg={avg_score:.3f}\n")

# === Full Report ===
print(f"\n{'='*60}")
print(f"全持仓测试报告 ({len(holdings)}只 × {RUNS_PER_STOCK}轮)")
print(f"{'='*60}")

total = sum(s["runs"] for s in summary.values())
total_pass = sum(s["passed"] for s in summary.values())
total_fail = sum(s["failed"] for s in summary.values())
total_errors = sum(s["errors"] for s in summary.values())
all_scores = [r["score"] for sr in all_results.values() for r in sr]
avg_all = sum(all_scores) / len(all_scores) if all_scores else 0

print(f"总轮次:  {total}")
print(f"通过:    {total_pass} ({total_pass/total*100:.1f}%)")
print(f"失败:    {total_fail} ({total_fail/total*100:.1f}%)")
print(f"崩溃:    {total_errors}")
print(f"全局平均分: {avg_all:.3f}")
print(f"全局最高分: {max(all_scores):.3f}")
print(f"全局最低分: {min(all_scores):.3f}")
if total > 1:
    import statistics
    print(f"全局标准差: {statistics.stdev(all_scores):.4f}")

print(f"\n各标的明细:")
print(f"{'标的':<10} {'通过率':>6} {'平均分':>6} {'最高':>5} {'最低':>5} {'修复0':>5} {'修复OK':>6} {'修复败':>5} {'异常':>4}")
print("-"*60)
for symbol, s in summary.items():
    pass_rate = s["passed"]/s["runs"]*100
    print(f"{s['name']:<10} {pass_rate:>5.0f}% {s['avg_score']:>6.3f} {s['max_score']:>5.2f} {s['min_score']:>5.2f} {s['repair_0']:>5} {s['repair_ok']:>6} {s['repair_fail']:>5} {s['errors']:>4}")

# Save
out = {
    "timestamp": datetime.now().isoformat(),
    "runs_per_stock": RUNS_PER_STOCK,
    "summary": summary,
    "global_avg_score": avg_all,
    "global_pass_rate": total_pass/total*100,
    "stock_results": all_results,
}
out_path = Path(f"D:/1989n/stock_data/expert_outputs/portfolio_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n详细结果: {out_path}")
