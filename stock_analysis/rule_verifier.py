"""
规则验证闭环 v1 — PDCA 的 C(检查) + A(行动) 阶段。

功能:
  1. 扫描规则库中所有待验证规则
  2. 对每条规则，回溯检查条件是否曾被触发
  3. 用实际后续数据判定规则是否正确
  4. 自动标记失效规则（连续N次验证失败）
  5. 输出规则审计报告

用法:
    python rule_verifier.py                     # 验证所有规则
    python rule_verifier.py --rule-id R2026...  # 验证指定规则
    python rule_verifier.py --auto-retire       # 自动退役失效规则
    python rule_verifier.py --report            # 输出规则有效性报告
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daily_compress import (
    load_json, save_json,
    LEARNING_DIR, RULES_FILE, RATIO_BASELINES_FILE, KEY_RATIOS,
)

RETIRE_THRESHOLD = 3       # 连续失败N次 → 标记退役
STALE_DAYS = 30            # N天未验证 → 标记过期


def load_rules() -> list:
    data = load_json(RULES_FILE)
    return data.get("rules", [])


def load_ratio_history() -> list:
    """加载比率历史（用于回测条件触发后的实际结果）。"""
    data = load_json(RATIO_BASELINES_FILE)
    return data.get("entries", [])


def extract_ratio_condition(rule: dict) -> dict | None:
    """从规则条件中提取涉及的比率和方向。"""
    condition = rule.get("condition", "")
    rule_ratios = {}

    for ratio_name in KEY_RATIOS:
        if ratio_name in condition:
            # 判断方向：高/升/↑ vs 低/降/↓
            if any(w in condition for w in ["升高", "上升", "偏高", "↑", "大于", "超过"]):
                rule_ratios[ratio_name] = "high"
            elif any(w in condition for w in ["降低", "下降", "偏低", "↓", "小于", "低于"]):
                rule_ratios[ratio_name] = "low"
            else:
                rule_ratios[ratio_name] = "any"
    return rule_ratios if rule_ratios else None


def check_condition_met(condition_ratios: dict, ratio_snapshot: dict) -> bool:
    """检查某天的比率快照是否满足了规则条件。"""
    ratios = ratio_snapshot.get("ratios", {})
    for name, direction in condition_ratios.items():
        info = ratios.get(name, {})
        z = info.get("z_score", 0)
        if direction == "high" and z <= 0:
            return False
        if direction == "low" and z >= 0:
            return False
    return True


def evaluate_outcome(rule: dict, trigger_dates: list,
                     ratio_entries: list) -> dict:
    """评估规则在触发后的实际表现。

    使用后续3天的比率变化来判断规则是否正确。
    规则 action 中如果包含做多意图 → 期望后续比率向正方向变化
    规则 action 中如果包含做空意图 → 期望后续比率向负方向变化
    """
    action = rule.get("action", "")
    is_bullish = any(w in action for w in ["买入", "做多", "开仓", "加仓", "持有",
                                            "增持", "追", "入场", "短线参与"])
    is_bearish = any(w in action for w in ["卖出", "做空", "减仓", "空仓", "清仓",
                                            "回避", "减", "撤退", "观望"])

    results = []
    for trigger_date in trigger_dates:
        # 找到触发日期在 entries 中的位置
        trigger_idx = None
        for i, entry in enumerate(ratio_entries):
            if entry.get("date") == trigger_date:
                trigger_idx = i
                break

        if trigger_idx is None:
            continue

        # 取后续最多3天的数据
        future_entries = ratio_entries[trigger_idx + 1:trigger_idx + 4]
        if not future_entries:
            continue

        # 计算后续的z-score平均变化
        triggered_ratios = list(extract_ratio_condition(rule).keys())

        z_changes = []
        for future in future_entries:
            for ratio_name in triggered_ratios:
                future_info = future.get("ratios", {}).get(ratio_name, {})
                current_info = ratio_entries[trigger_idx].get("ratios", {}).get(ratio_name, {})
                if future_info and current_info:
                    fz = future_info.get("z_score", 0)
                    cz = current_info.get("z_score", 0)
                    z_changes.append(fz - cz)

        if not z_changes:
            continue

        avg_z_change = sum(z_changes) / len(z_changes)

        # 判定：做多规则期望 z 回归正常（异常降低 → z 回到 (-2, 2)）
        # 简化：如果规则是做多方向，条件触发时z偏高 → 后续z应该下降
        correct = False
        if is_bullish or is_bearish:
            if is_bullish:
                # 触发时异常 → 期望后续回归正常
                correct = avg_z_change < 0.5  # z下降说明异常回归
            else:
                correct = avg_z_change > -0.5  # z企稳说明不继续恶化
        else:
            # 中性规则：期望后续波动减小
            correct = abs(avg_z_change) < 1.0

        results.append({
            "trigger_date": trigger_date,
            "avg_z_change": round(avg_z_change, 3),
            "correct": correct,
        })

    return {
        "total_triggers": len(trigger_dates),
        "evaluated": len(results),
        "correct_count": sum(1 for r in results if r["correct"]),
        "accuracy": round(sum(1 for r in results if r["correct"]) / max(len(results), 1), 2),
        "details": results,
    }


def verify_rule(rule: dict, ratio_entries: list) -> dict:
    """验证单条规则。"""
    condition_ratios = extract_ratio_condition(rule)
    if not condition_ratios:
        return {
            "verifiable": False,
            "reason": "规则条件中未匹配任何关键比率",
        }

    # 找到规则创建之后的日期
    created = rule.get("created", "")
    trigger_dates = []
    for entry in ratio_entries:
        entry_date = entry.get("date", "")
        if created and entry_date < created[:10]:
            continue
        if check_condition_met(condition_ratios, entry):
            trigger_dates.append(entry_date)

    if not trigger_dates:
        return {
            "verifiable": True,
            "triggered": False,
            "reason": "条件尚未被触发",
            "condition_ratios": list(condition_ratios.keys()),
        }

    outcome = evaluate_outcome(rule, trigger_dates, ratio_entries)

    return {
        "verifiable": True,
        "triggered": True,
        "trigger_dates": trigger_dates,
        "condition_ratios": list(condition_ratios.keys()),
        **outcome,
    }


def auto_retire_rules(rules: list, ratio_entries: list) -> list:
    """自动标记应退役的规则。

    退役条件:
    1. 已验证 >= RETIRE_THRESHOLD 次且准确率 = 0
    2. 超过 STALE_DAYS 天未验证
    """
    retired = []
    today = datetime.now().strftime("%Y-%m-%d")

    for rule in rules:
        if rule.get("status") == "retired":
            continue

        verified = rule.get("verified_count", 0)

        # 连续失败
        if verified >= RETIRE_THRESHOLD:
            result = verify_rule(rule, ratio_entries)
            if result.get("evaluated", 0) >= RETIRE_THRESHOLD and result.get("accuracy", 0) == 0:
                rule["status"] = "retired"
                rule["retired_reason"] = f"连续{result['evaluated']}次验证失败"
                rule["retired_at"] = today
                retired.append(rule["id"])

        # 过期
        last_verified = rule.get("last_verified", "")
        if last_verified:
            days_since = (datetime.now() - datetime.strptime(last_verified[:10], "%Y-%m-%d")).days
            if days_since > STALE_DAYS:
                rule["status"] = "stale"
                rule["retired_reason"] = f"超过{STALE_DAYS}天未验证"
                rule["retired_at"] = today
                retired.append(rule["id"])

    if retired:
        save_json(RULES_FILE, {"rules": rules})
        print(f"  已退役 {len(retired)} 条规则: {retired}")

    return retired


def generate_report(rules: list, ratio_entries: list) -> str:
    """生成规则库有效性报告。"""
    active = [r for r in rules if r.get("status") not in ("retired", "stale")]
    condensed = [r for r in active if r.get("is_condensed")]
    verified = [r for r in active if r.get("verified_count", 0) > 0]
    retired = [r for r in rules if r.get("status") in ("retired", "stale")]

    report = f"""# 规则库审计报告

**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
**规则总数**: {len(rules)}
**活跃**: {len(active)} (凝练: {len(condensed)}, 已验证: {len(verified)})
**退役/过期**: {len(retired)}

## 活跃规则

| ID | 条件 | 动作 | 凝练 | 验证 |
|----|------|------|------|------|
"""
    for r in active[:20]:
        report += f"| {r.get('id','')} | {r.get('condition','')[:40]} | {r.get('action','')[:30]} | {'Y' if r.get('is_condensed') else 'N'} | {r.get('verified_count',0)} |\n"

    if retired:
        report += "\n## 退役规则\n"
        for r in retired:
            report += f"- {r.get('id','')}: {r.get('retired_reason','')}\n"

    # 验证统计（如果数据充足）
    if ratio_entries:
        verified_results = []
        for r in active:
            vr = verify_rule(r, ratio_entries)
            if vr.get("triggered"):
                verified_results.append(vr)

        if verified_results:
            avg_accuracy = sum(v.get("accuracy", 0) for v in verified_results) / len(verified_results)
            report += f"\n## 验证统计\n\n"
            report += f"- 已触发规则: {len(verified_results)}\n"
            report += f"- 平均准确率: {avg_accuracy:.0%}\n"

    report += f"\n## 数据可用性\n"
    report += f"- 比率历史条目: {len(ratio_entries)} 条\n"
    report += f"- 最近数据日期: {ratio_entries[-1].get('date','N/A') if ratio_entries else 'N/A'}\n"

    return report


def main():
    rules = load_rules()
    ratio_entries = load_ratio_history()

    if "--report" in sys.argv:
        print(generate_report(rules, ratio_entries))
        return

    if "--auto-retire" in sys.argv:
        print("自动退役检查...")
        retired = auto_retire_rules(rules, ratio_entries)
        print(f"退役: {len(retired)} 条")
        return

    # 全量验证
    if "--rule-id" in sys.argv:
        idx = sys.argv.index("--rule-id")
        rid = sys.argv[idx + 1]
        rules = [r for r in rules if r.get("id") == rid]
        if not rules:
            print(f"规则未找到: {rid}")
            return

    print(f"规则验证 (共 {len(rules)} 条, 比率历史 {len(ratio_entries)} 条)\n")

    verifiable = 0
    triggered = 0
    stale_rules = []

    for rule in rules:
        if rule.get("status") in ("retired", "stale"):
            continue

        result = verify_rule(rule, ratio_entries)
        print(f"[{rule.get('id','unknown')}] {rule.get('condition','')[:60]}...")

        if not result.get("verifiable"):
            print(f"  → 不可验证: {result.get('reason')}")
            stale_rules.append(rule["id"])
            continue

        verifiable += 1

        if not result.get("triggered"):
            print(f"  → 条件未触发 (涉及比率: {result.get('condition_ratios',[])})")
            continue

        triggered += 1
        print(f"  触发 {result['total_triggers']} 次, 评估 {result['evaluated']} 次")
        print(f"  准确率: {result['accuracy']:.0%} ({result['correct_count']}/{result['evaluated']})")

        # 更新规则验证信息
        rule["last_verified"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        rule["verified_count"] = rule.get("verified_count", 0) + 1
        rule["verification_result"] = {
            "accuracy": result["accuracy"],
            "evaluated": result["evaluated"],
            "details": result["details"][-3:],  # 保留最近3次
        }

    # 保存更新
    save_json(RULES_FILE, {"rules": rules})

    print(f"\n--- 验证完成 ---")
    print(f"  可验证规则: {verifiable}/{len(rules)}")
    print(f"  已触发: {triggered}")
    print(f"  待验证(无数据): {len(stale_rules)}")

    # 退役检查
    auto_retire_rules(rules, ratio_entries)


if __name__ == "__main__":
    main()
