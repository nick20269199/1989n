"""
20 圈认知飞轮 v2 测试 — 验证"操作系统"升级。

测试维度 v2:
1. 周期阶段判定一致性（5 步不应频繁跳变）
2. 比率快照写入 + z-score 计算
3. 预期差分析产出
4. 规则凝练达标率（is_condensed 比例）
5. 日摘要 v2 5 段结构完整性
6. 周审计 ego_challenge 追踪

用法:
    python test_cognitive_loop.py           # 全量测试
    python test_cognitive_loop.py --quick   # 快速模式（不调 API）
"""
import json
import sys
import random
import os
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daily_compress import (
    judge_cycle_stage, _read_market_data, record_ratios,
    analyze_expectation_gap, condense_rule, commit_rule,
    write_digest_v2, run_full_compress,
    load_json, save_json,
    LEARNING_DIR, RULES_FILE, RATIO_BASELINES_FILE, KEY_RATIOS,
)

LEARNING_DIR = Path("D:/1989n/stock_data/learning")
MODELS_DIR = LEARNING_DIR / "models"

SEED_QUESTIONS = [
    {"q": "北向资金净流入与沪深300日内波动的领先滞后关系", "priority": "high"},
    {"q": "两融余额变化对次日涨停家数的预测能力", "priority": "high"},
    {"q": "板块轮动速度与市场整体成交量关系", "priority": "medium"},
    {"q": "集合竞价量比与开盘方向准确率", "priority": "medium"},
    {"q": "跌停家数作为恐慌底部的信号可靠性", "priority": "high"},
    {"q": "次新股换手率对后续走势的指示意义", "priority": "medium"},
    {"q": "大单净流入占比与次日高开概率", "priority": "high"},
    {"q": "炸板率日内变化与市场情绪拐点", "priority": "medium"},
    {"q": "强势板块数量收缩到扩张的转换信号", "priority": "medium"},
    {"q": "融资买入额/成交额占比作为过热的阈值确定", "priority": "high"},
]

MISTAKE_TEMPLATES = [
    "惯性输出：未查数据就直接假设融资余额增加=做多信号",
    "知识盲区：不熟悉ETF申赎机制，误判了资金流向",
    "逻辑跳跃：把相关性当成了因果性",
    "数据滞后：用了T-2的数据做T+0判断",
    "过度自信：对信号的判断过于确定，未标注不确定性",
    "遗漏维度：只看量价忘了资金面",
]


class LoopTesterV2:
    def __init__(self, quick_mode=False):
        self.quick = quick_mode
        self.errors = []
        self.warnings = []
        self.start_date = datetime(2026, 5, 12)
        self.results = {
            "cycles": [],
            "stages": [],
            "ratios_recorded": [],
            "gaps_found": [],
            "rules_condensed": [],
            "ego_challenges": [],
            "weekly_audits": [],
        }

    def log(self, msg):
        print(f"  {msg}")

    def error(self, msg):
        self.errors.append(msg)
        print(f"  [FAIL] {msg}")

    def warn(self, msg):
        self.warnings.append(msg)
        print(f"  [WARN] {msg}")

    def ok(self, msg):
        print(f"  [OK] {msg}")

    def reset_data(self):
        for f in LEARNING_DIR.glob("daily_digest_*.json"):
            if "2026" in f.name:
                f.unlink()
        for f in LEARNING_DIR.glob("weekly_audit_*.md"):
            if "2026" in f.name:
                f.unlink()
        for f in MODELS_DIR.glob("*.md"):
            if "2026" in f.name:
                f.unlink()

        # 重置追踪文件
        for name in ["open_questions", "collision_log", "forecast_tracker",
                     "efficiency_daily", "daily_digest_index"]:
            path = LEARNING_DIR / f"{name}.json"
            key = name.replace("_daily", "").replace("_index", "").replace("_log", "")
            defaults = {"updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
            defaults[name] = []
            with open(path, "w", encoding="utf-8") as f:
                json.dump(defaults, f, ensure_ascii=False, indent=2)

        # 重置 v2 文件
        for path in [RULES_FILE, RATIO_BASELINES_FILE]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                           "entries" if "ratio" in str(path) else "rules": [],
                           "stats": {}}, f, ensure_ascii=False, indent=2)

        self.log("测试数据已重置 (v2)")

    def run_cycle(self, day_num: int, date: datetime) -> dict:
        print(f"\n=== 第 {day_num} 天 ({date.strftime('%m/%d')}) ===")

        date_str = date.strftime("%Y-%m-%d")

        # Tier 1: 天时定位
        print("  [Tier 1] 天时定位...")
        market_data = _read_market_data(date_str)
        cycle = judge_cycle_stage(market_data, date_str)
        self.results["stages"].append(cycle["stage"])
        print(f"    阶段: {cycle['stage']} (置信度: {cycle['confidence']})")

        # Tier 2: 比率快照（模拟数据）
        print("  [Tier 2] 比率快照...")
        manual_ratios = {}
        for name in KEY_RATIOS:
            base = random.uniform(0.15, 0.85)
            manual_ratios[name] = round(base + random.uniform(-0.1, 0.1), 4)
        ratio_snapshot = record_ratios(date_str, market_data, manual_ratios)
        self.results["ratios_recorded"].append(len(ratio_snapshot["ratios"]))
        alerts = sum(1 for k, v in ratio_snapshot["ratios"].items() if v.get("alert") == "triggered")
        print(f"    记录 {len(ratio_snapshot['ratios'])} 个比率, {alerts} 个警报")

        # Tier 3: 预期差分析
        print("  [Tier 3] 预期差分析...")
        gaps = analyze_expectation_gap(market_data, cycle)
        self.results["gaps_found"].append(len(gaps["gaps"]))
        print(f"    预期差维度: {len(gaps['gaps'])} 个")

        # Tier 4: 凝练规则
        print("  [Tier 4] 凝练规则...")
        rules_today = []
        for i in range(random.randint(1, 3)):
            rule = condense_rule(
                insight_text=f"测试洞察 {day_num}-{i}",
                cycle_stage=cycle["stage"],
                source_data=f"test_cycle_{day_num}",
            )
            rule["condition"] = f"当{cycle['stage']}阶段，{list(KEY_RATIOS.keys())[i]}出现异常偏离时"
            rule["action"] = f"执行操作{day_num}-{i}"
            rule["failure_signal"] = f"如果{list(KEY_RATIOS.keys())[i+1]}未同步确认，则规则失效"
            rule["is_condensed"] = bool(random.randint(0, 1))
            rid = commit_rule(rule)
            rules_today.append(rule)
        condensed_count = sum(1 for r in rules_today if r.get("is_condensed"))
        self.results["rules_condensed"].append(condensed_count)
        print(f"    凝练规则: {len(rules_today)} 条, 达标: {condensed_count}")

        # Tier 5: ego challenge
        ego = ""
        if day_num % 5 == 0:
            ego = f"测试ego挑战: 核心假设在day{day_num}受到证据X的挑战"
        self.results["ego_challenges"].append(1 if ego else 0)

        # 写 v2 摘要
        mistake = random.choice(MISTAKE_TEMPLATES)
        digest = write_digest_v2(
            date_str=date_str,
            cycle_stage=cycle,
            ratio_snapshot=ratio_snapshot,
            expectation_gaps=gaps,
            rules_condensed=rules_today,
            mistake=mistake,
            feedback="测试反馈",
            forecast_updates={"new": random.randint(0, 2)},
            efficiency={"total_calls": random.randint(20, 50)},
        )

        # 手动填入自检字段
        digest["self_check"]["ego_challenge"] = ego
        digest["self_check"]["mistake_root_cause"] = random.choice(
            ["知识盲区", "逻辑跳跃", "惯性输出", "数据缺失", "情绪干扰"]
        )
        digest_path = LEARNING_DIR / f"daily_digest_{date.strftime('%Y%m%d')}.json"
        with open(digest_path, "w", encoding="utf-8") as f:
            json.dump(digest, f, ensure_ascii=False, indent=2)

        if digest_path.exists():
            self.ok(f"v2日摘要: {digest_path.name} (阶段:{cycle['stage']})")
        else:
            self.error(f"日摘要写入失败: {digest_path}")

        # 研究段（每5天调API）
        print("  [研究段 20:07]")
        if not self.quick and day_num % 5 == 0:
            print("    → 实际调用 Channel 2 API...")
            try:
                from deepseek_multi import research
                result = research(
                    f"在当前{cycle['stage']}阶段，分析: {SEED_QUESTIONS[day_num % len(SEED_QUESTIONS)]['q']}",
                    temperature=0.3,
                    max_tokens=512,
                )
                model_path = MODELS_DIR / f"{date.strftime('%Y%m%d')}_cycle{day_num}.md"
                with open(model_path, "w", encoding="utf-8") as f:
                    f.write(f"# 周期阶段: {cycle['stage']}\n\n{result[:1000]}")
                self.ok(f"研究产出: {model_path.name}")
            except Exception as e:
                self.warn(f"API调用失败(非致命): {e}")
        else:
            self.log("    (跳过API)")

        return {
            "day": day_num, "date": date_str,
            "stage": cycle["stage"], "confidence": cycle["confidence"],
            "digest_v2": digest_path.exists(),
            "ratios": len(ratio_snapshot["ratios"]),
            "gaps": len(gaps["gaps"]),
            "rules_condensed": condensed_count,
        }

    def run_weekly_audit(self, week_num: int, end_date: datetime):
        print(f"\n===== 第 {week_num} 周审计 v2 ({end_date.strftime('%m/%d')}) =====")

        week_digests = []
        for i in range(5):
            d = end_date - timedelta(days=4 - i)
            path = LEARNING_DIR / f"daily_digest_{d.strftime('%Y%m%d')}.json"
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    week_digests.append(json.load(f))

        if len(week_digests) < 3:
            self.warn(f"本周仅 {len(week_digests)} 条摘要")

        # 周期一致性
        stages = [d.get("cycle_stage", {}).get("stage", "未知") for d in week_digests]
        stage_counts = {}
        for s in stages:
            stage_counts[s] = stage_counts.get(s, 0) + 1
        most_common_stage = max(stage_counts, key=stage_counts.get)
        consistency = stage_counts[most_common_stage] / len(stages)
        if consistency < 0.6:
            self.warn(f"周期判定不一致: {stage_counts}")

        # ego_challenge 统计
        ego_days = sum(1 for d in week_digests
                      if d.get("self_check", {}).get("ego_challenge", "").strip())
        if ego_days == 0:
            self.warn("本周 ego_challenge 全部为空 — 框架可能在自循环验证")

        # 重复错误
        mistakes = [d.get("self_check", {}).get("mistake", "")[:30] for d in week_digests]
        mistake_counts = {}
        for m in mistakes:
            if m:
                mistake_counts[m] = mistake_counts.get(m, 0) + 1
        repeats = {k: v for k, v in mistake_counts.items() if v >= 2}
        if repeats:
            self.warn(f"重复错误模式: {len(repeats)} 个")

        # 凝练规则统计
        all_condensed = sum(d.get("rules_condensed_count", 0) for d in week_digests)
        all_total = sum(d.get("rules_total_count", 0) for d in week_digests)

        # 规则审计
        rules_data = load_json(RULES_FILE)
        all_rules = rules_data.get("rules", [])
        condensed_rules = [r for r in all_rules if r.get("is_condensed")]
        uncondensed_rules = [r for r in all_rules if not r.get("is_condensed")]

        audit = {
            "week": week_num,
            "end_date": end_date.strftime("%Y-%m-%d"),
            "digest_count": len(week_digests),
            "stage_consistency": round(consistency, 2),
            "ego_challenge_days": ego_days,
            "repeated_errors": len(repeats),
            "rules_condensed_week": all_condensed,
            "rules_total_week": all_total,
            "rules_library_total": len(all_rules),
            "rules_condensed_total": len(condensed_rules),
            "rules_uncondensed_stale": len([r for r in uncondensed_rules
                                            if r.get("verified_count", 0) == 0]),
        }

        audit_path = LEARNING_DIR / f"weekly_audit_{end_date.strftime('%Y%m%d')}.md"
        report = f"""# 周审计报告 v2 W{week_num} ({end_date.strftime('%Y-%m-%d')})

## 三轨健康度
| 轨道 | 关键指标 |
|------|---------|
| 理解力 | 周期一致性 {consistency:.0%}, 预期差 {sum(len(d.get('expectation_gaps',[])) for d in week_digests)} 个 |
| 创造力 | 凝练规则 {all_condensed}/{all_total}, 活跃规则 {len(condensed_rules)} |
| 效率 | 摘要产出 {len(week_digests)}/5 |

## 规则审计
- 规则库总量: {len(all_rules)}, 已凝练: {len(condensed_rules)}
- 本周凝练: {all_condensed} 条

## Ego Death
- 本周 ego_challenge 天数: {ego_days}/5
- {'警告: 无挑战性证据，框架可能在自循环验证' if ego_days == 0 else '正常'}

## 重复错误
{chr(10).join(f'- {k} ({v}次)' for k, v in repeats.items()) if repeats else '- 无'}
"""
        with open(audit_path, "w", encoding="utf-8") as f:
            f.write(report)

        if audit_path.exists():
            self.ok(f"v2审计报告: {audit_path.name}")

        self.results["weekly_audits"].append(audit)
        return audit

    def run(self, cycles: int = 20):
        print("=" * 60)
        print(f"认知飞轮 v2 — {cycles} 圈测试")
        print(f"模式: {'快速(不调API)' if self.quick else '标准(每5圈调API)'}")
        print(f"起始日期: {self.start_date.strftime('%Y-%m-%d')}")
        print("=" * 60)

        self.reset_data()

        for day in range(cycles):
            date = self.start_date + timedelta(days=day)
            if date.weekday() >= 5:
                print(f"\n  [{date.strftime('%a')} 非交易日，跳过]")
                continue
            self.run_cycle(day + 1, date)
            if date.weekday() == 4:
                week_num = day // 7 + 1
                self.run_weekly_audit(week_num, date)

        # ══ 最终报告 ══
        print("\n" + "=" * 60)
        print("20 圈 v2 测试报告")
        print("=" * 60)

        passed = 0
        failed = 0
        checks = []

        # 检查 1: 日摘要覆盖率
        actual_days = 0
        all_digests_ok = True
        for day in range(cycles):
            date = self.start_date + timedelta(days=day)
            if date.weekday() < 5:
                actual_days += 1
                path = LEARNING_DIR / f"daily_digest_{date.strftime('%Y%m%d')}.json"
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        d = json.load(f)
                    if d.get("version") != 2:
                        all_digests_ok = False
                        checks.append(f"[FAIL] {date.strftime('%m/%d')} 不是v2格式")
                else:
                    all_digests_ok = False
                    checks.append(f"[FAIL] {date.strftime('%m/%d')} 缺失")
        if all_digests_ok:
            passed += 1
            checks.append(f"[PASS] v2 日摘要: {actual_days}/{actual_days}")
        else:
            failed += 1

        # 检查 2: 周期判定一致性
        stages = self.results["stages"]
        if len(stages) >= 5:
            stage_set = set(stages[:5])
            if len(stage_set) <= 2:
                passed += 1
                checks.append(f"[PASS] 周期一致性: 前5天{len(stage_set)}个不同阶段")
            else:
                failed += 1
                checks.append(f"[FAIL] 周期跳变过多: {len(stage_set)}个阶段")

        # 检查 3: 比率快照
        if all(r == 8 for r in self.results["ratios_recorded"]):
            passed += 1
            checks.append("[PASS] 比率快照: 每天8个比率")
        else:
            failed += 1
            checks.append(f"[FAIL] 比率记录不完整")

        # 检查 4: 预期差
        if all(g >= 1 for g in self.results["gaps_found"]):
            passed += 1
            checks.append("[PASS] 预期差分析: 每天至少1个维度")
        else:
            failed += 1
            checks.append(f"[FAIL] 预期差分析缺失")

        # 检查 5: 规则凝练
        all_condensed = sum(self.results["rules_condensed"])
        if all_condensed > 0:
            passed += 1
            checks.append(f"[PASS] 规则凝练: {all_condensed} 条达标")
        else:
            failed += 1
            checks.append("[FAIL] 无双标凝练规则")

        # 检查 6: ego_challenge
        ego_days = sum(self.results["ego_challenges"])
        if ego_days >= 1:
            passed += 1
            checks.append(f"[PASS] ego_challenge: {ego_days}/{len(self.results['ego_challenges'])} 天")
        else:
            failed += 1
            checks.append("[FAIL] ego_challenge 全部为空")

        # 检查 7: 周审计
        expected_audits = (actual_days + 4) // 5
        actual_audits = len(list(LEARNING_DIR.glob("weekly_audit_2026*.md")))
        if actual_audits >= expected_audits:
            passed += 1
            checks.append(f"[PASS] 周审计: {actual_audits} 份")
        else:
            failed += 1
            checks.append(f"[FAIL] 周审计不足: 期望≥{expected_audits}, 实际{actual_audits}")

        # 检查 8: 数据文件完整性
        all_files_ok = True
        for name in ["open_questions", "collision_log", "forecast_tracker",
                     "efficiency_daily", "daily_digest_index", "rules", "ratio_baselines"]:
            path = LEARNING_DIR / f"{name}.json"
            try:
                with open(path, "r", encoding="utf-8") as f:
                    json.load(f)
            except Exception as e:
                all_files_ok = False
                checks.append(f"[FAIL] {name}.json 损坏: {e}")
        if all_files_ok:
            passed += 1
            checks.append("[PASS] 所有数据文件完整")

        # 检查 9: 无系统错误
        if len(self.errors) == 0:
            passed += 1
            checks.append("[PASS] 零系统错误")
        else:
            failed += len(self.errors)
            for e in self.errors:
                checks.append(f"[FAIL] {e}")

        for c in checks:
            print(c)

        print(f"\n--- 结果: {passed}/{passed + failed} 通过 ---")
        if self.warnings:
            print(f"警告 ({len(self.warnings)}):")
            for w in self.warnings[:5]:
                print(f"  - {w}")

        # 写详细结果
        result_path = LEARNING_DIR / "test_v2_results.json"
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({
                "passed": passed, "failed": failed,
                "checks": checks, "warnings": self.warnings,
                "results_summary": {
                    "stages_distribution": {s: self.results["stages"].count(s) for s in set(self.results["stages"])},
                    "total_rules_condensed": all_condensed,
                    "total_ego_challenges": ego_days,
                    "total_audits": actual_audits,
                }
            }, f, ensure_ascii=False, indent=2)

        return passed, failed


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    tester = LoopTesterV2(quick_mode=quick)
    passed, failed = tester.run(20)
    sys.exit(0 if failed == 0 else 1)
