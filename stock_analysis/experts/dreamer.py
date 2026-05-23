"""
Dreamer — 从 decision_log outcome 计算每专家准确率，动态调整权重

流程:
  1. 读 decision_log 近 N 天有 outcome 的记录
  2. 解析 factors JSON → 按专家聚合准确率
  3. 更新 expert_weights.json
  4. 输出飞书报告
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from knowledge_db import get_db
from config import STOCK_DATA_DIR


EXPERT_IDS = ["expert1_tech", "expert2_money", "expert3_sentiment",
               "expert4_macro", "expert5_risk"]

WEIGHT_BASE = 1.0
WEIGHT_MAX = 2.0
WEIGHT_MIN = 0.3
ACCURACY_BASELINE = 0.50  # 50% 为基准
MIN_SAMPLES = 5            # 少于5次判断不调整权重

WEIGHT_FILE = Path("D:/1989n/stock_analysis/experts/expert_weights.json")


def load_expert_weights() -> dict:
    """加载当前权重"""
    if WEIGHT_FILE.exists():
        try:
            return json.loads(WEIGHT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {eid: WEIGHT_BASE for eid in EXPERT_IDS}


def save_expert_weights(weights: dict):
    """保存权重"""
    WEIGHT_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEIGHT_FILE.write_text(
        json.dumps(weights, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def aggregate_accuracy(days: int = 30) -> dict:
    """
    从 decision_log 聚合专家准确率。
    返回: {expert_id: {total, correct, wrong, accuracy}, merged: {...}}
    """
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d 00:00:00")

    stats = {eid: {"total": 0, "correct": 0, "wrong": 0}
             for eid in EXPERT_IDS}
    merged = {"total": 0, "correct": 0, "wrong": 0}

    with get_db() as db:
        rows = db.execute(
            """SELECT factors, outcome
               FROM decision_log
               WHERE outcome IS NOT NULL AND outcome NOT IN ('数据不足','待回测')
                 AND timestamp >= ?
               ORDER BY timestamp DESC""",
            (cutoff,),
        ).fetchall()

    for row in rows:
        outcome = row["outcome"]
        try:
            packet = json.loads(row["factors"])
        except (json.JSONDecodeError, TypeError):
            continue

        # 合并方向准确率
        grader = packet.get("grader", {})
        merged_dir = grader.get("merged_direction", "")
        if merged_dir and outcome in ("正确", "错误"):
            merged["total"] += 1
            if outcome == "正确":
                merged["correct"] += 1
            else:
                merged["wrong"] += 1

        # 逐专家
        experts = packet.get("expert_directions", packet.get("expert_outputs", []))
        for e in experts:
            eid = e.get("expert", e.get("expert_id", ""))
            if eid not in stats:
                continue
            # 用 factors 里的方向判定结果 — 与 outcome 一致则正确
            direction = e.get("direction", "")
            if not direction:
                continue
            stats[eid]["total"] += 1
            if outcome == "正确":
                stats[eid]["correct"] += 1
            else:
                stats[eid]["wrong"] += 1

    # 计算准确率
    for eid in EXPERT_IDS:
        t = stats[eid]["total"]
        stats[eid]["accuracy"] = round(stats[eid]["correct"] / t * 100, 1) if t > 0 else 0

    merged_accuracy = round(merged["correct"] / merged["total"] * 100, 1) if merged["total"] > 0 else 0

    return {
        "per_expert": stats,
        "merged": {**merged, "accuracy": merged_accuracy},
        "total_records": len(rows),
        "window_days": days,
    }


def compute_new_weights(accuracy_report: dict) -> dict:
    """
    根据准确率计算新权重:
      accuracy > 60% → 提升 (cap 2.0)
      accuracy 40-60% → 保持 1.0
      accuracy < 40% → 降低 (floor 0.3)
      samples < 5 → 保持 1.0
    """
    current = load_expert_weights()
    new_weights = dict(current)
    adjustments = []

    for eid in EXPERT_IDS:
        est = accuracy_report["per_expert"].get(eid, {})
        total = est.get("total", 0)
        accuracy = est.get("accuracy", 0)

        if total < MIN_SAMPLES:
            new_weights[eid] = WEIGHT_BASE
            adjustments.append(f"{eid}:样本不足({total}次),保持{WEIGHT_BASE}")
            continue

        acc_ratio = accuracy / 100 / ACCURACY_BASELINE
        raw_weight = WEIGHT_BASE * acc_ratio
        new_weight = max(WEIGHT_MIN, min(WEIGHT_MAX, raw_weight))
        new_weights[eid] = round(new_weight, 2)

        direction = "↑" if new_weight > current.get(eid, WEIGHT_BASE) else \
                    "↓" if new_weight < current.get(eid, WEIGHT_BASE) else "→"
        adjustments.append(
            f"{eid}:{current.get(eid, WEIGHT_BASE)}→{new_weight}{direction} "
            f"(准确率{accuracy}%,{total}次)"
        )

    return new_weights, adjustments


def run_dreamer(days: int = 30) -> dict:
    """执行 Dreamer 全流程: 聚合 → 调权重 → 报告"""
    print(f"Dreamer 启动 — 分析最近 {days} 天决策记录")

    report = aggregate_accuracy(days=days)
    print(f"共 {report['total_records']} 条有 outcome 的记录")
    print(f"合并方向准确率: {report['merged']['accuracy']}%")

    for eid in EXPERT_IDS:
        est = report["per_expert"][eid]
        if est["total"] > 0:
            print(f"  {eid}: {est['accuracy']}% ({est['correct']}/{est['total']})")

    new_weights, adjustments = compute_new_weights(report)
    save_expert_weights(new_weights)

    print("\n权重调整:")
    for adj in adjustments:
        print(f"  {adj}")

    # 写报告到 JSON
    result = {
        "timestamp": datetime.now().isoformat(),
        "window_days": days,
        "total_records": report["total_records"],
        "merged_accuracy": report["merged"]["accuracy"],
        "per_expert": report["per_expert"],
        "new_weights": new_weights,
        "adjustments": adjustments,
    }
    report_path = Path("D:/1989n/stock_data") / "dreamer_report.json"
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告写入: {report_path}")

    return result


if __name__ == "__main__":
    run_dreamer()
