"""
Expert Repair Loop 实测 — 跑N轮，看修复前后通过率变化
"""
import sys, json, time, logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

from experts.lead import run_single

SYMBOL = "002156"
NAME = "通富微电"
RUNS = 20

results = []
repair_stats = {"total": 0, "passed_first": 0, "passed_after_repair": 0, "still_failed": 0}
score_history = []

print(f"=== Expert Pipeline 修复循环测试 === {datetime.now().strftime('%H:%M:%S')}")
print(f"标的: {NAME}({SYMBOL}), 运行{RUNS}轮\n")

for i in range(1, RUNS + 1):
    t0 = time.time()
    try:
        packet = run_single(SYMBOL, NAME, mode="full")
        elapsed = time.time() - t0
        passed = packet.get("pipeline_status") == "passed"
        score = packet.get("grader", {}).get("score", 0)
        repair_rounds = packet.get("repair_rounds", 0)

        results.append({
            "run": i, "passed": passed, "score": score,
            "repair_rounds": repair_rounds, "elapsed": round(elapsed, 1),
        })
        score_history.append(score)
        repair_stats["total"] += 1

        if repair_rounds == 0:
            repair_stats["passed_first"] += 1
        elif passed:
            repair_stats["passed_after_repair"] += 1
        else:
            repair_stats["still_failed"] += 1

        mark = "✅" if passed else "❌"
        print(f"  [{i:02d}/{RUNS}] score={score:.2f} repair={repair_rounds} "
              f"{'→ PASS' if passed else '→ FAIL'} ({elapsed:.0f}s) {mark}")

    except Exception as e:
        elapsed = time.time() - t0
        print(f"  [{i:02d}/{RUNS}] CRASH: {e} ({elapsed:.0f}s) 💥")
        results.append({"run": i, "passed": False, "score": 0, "repair_rounds": -1, "error": str(e)})

# === 报告 ===
passed = sum(1 for r in results if r["passed"])
total = len(results)
avg_score = sum(r["score"] for r in results) / total if total > 0 else 0
avg_repair = sum(r["repair_rounds"] for r in results) / total if total > 0 else 0

print(f"\n{'='*55}")
print(f"结果汇总 ({RUNS}轮)")
print(f"{'='*55}")
print(f"通过率:  {passed}/{total} = {passed/total*100:.1f}%")
print(f"平均分:  {avg_score:.3f}")
print(f"最高分:  {max(score_history):.3f}")
print(f"最低分:  {min(score_history):.3f}")
print(f"平均修复轮次: {avg_repair:.2f}")
print(f"一轮过:  {repair_stats['passed_first']}/{repair_stats['total']}")
print(f"修复后过: {repair_stats['passed_after_repair']}/{repair_stats['total']}")
print(f"修复仍败: {repair_stats['still_failed']}/{repair_stats['total']}")
print(f"标准差:  {__import__('statistics').stdev(score_history):.3f}" if len(score_history) > 1 else "")

# 高分段分布
buckets = {"0.9+": 0, "0.8-0.9": 0, "0.7-0.8": 0, "0.6-0.7": 0, "<0.6": 0}
for s in score_history:
    if s >= 0.9: buckets["0.9+"] += 1
    elif s >= 0.8: buckets["0.8-0.9"] += 1
    elif s >= 0.7: buckets["0.7-0.8"] += 1
    elif s >= 0.6: buckets["0.6-0.7"] += 1
    else: buckets["<0.6"] += 1
print(f"\n分数分布:")
for k, v in buckets.items():
    bar = "█" * v
    print(f"  {k}: {v:2d} {bar}")

# 保存
out_path = Path(f"D:/1989n/stock_data/expert_outputs/test_repair_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
out_path.write_text(json.dumps({"results": results, "stats": repair_stats, "scores": score_history}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n详细结果: {out_path}")
