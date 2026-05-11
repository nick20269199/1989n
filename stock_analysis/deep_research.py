"""
Deep research runner v2 — 周期感知 + 比率上下文注入。

Cron 20:07 触发。走 Channel 2/3，不碰主会话配额。

v2 新增:
  - 研究前自动加载当前周期阶段和活跃比率警报
  - 系统提示中注入"当前处于XX阶段，研究应该在什么策略背景下"
  - 研究产出标注周期阶段依赖

用法:
    python deep_research.py                        # 自动取优先级最高问题
    python deep_research.py --question "..."       # 手动指定
    python deep_research.py --list                 # 列出问题队列
    python deep_research.py --from-alerts          # 先从比率警报生成问题，再研究
"""
import json
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from deepseek_multi import research, dual_research, channel_health
from daily_compress import (
    load_json, judge_cycle_stage, _read_market_data, RATIO_BASELINES_FILE,
)

LEARNING_DIR = Path("D:/1989n/stock_data/learning")
QUESTIONS_FILE = LEARNING_DIR / "open_questions.json"
MODELS_DIR = LEARNING_DIR / "models"


def get_cycle_context() -> dict:
    """获取当前周期阶段上下文。"""
    try:
        market = _read_market_data()
        cycle = judge_cycle_stage(market)
        return cycle
    except Exception:
        return {"stage": "未知", "confidence": 0, "strategy_hint": ""}


def get_ratio_alerts() -> list:
    """获取最新比率快照中的活跃警报。"""
    try:
        data = load_json(RATIO_BASELINES_FILE)
        entries = data.get("entries", [])
        if not entries:
            return []
        latest = entries[-1]
        alerts = []
        for name, info in latest.get("ratios", {}).items():
            if info.get("alert") == "triggered":
                alerts.append({
                    "ratio": name,
                    "z_score": info.get("z_score", 0),
                    "value": info.get("value", 0),
                    "mean": info.get("mean", 0),
                })
        return alerts
    except Exception:
        return []


def build_system_prompt(cycle: dict, alerts: list, question: str) -> str:
    """构建注入周期+比率上下文的系统提示。"""
    stage = cycle.get("stage", "未知")
    strategy = cycle.get("strategy_hint", "")
    next_risk = cycle.get("next_stage_risk", "")
    collision_focus = cycle.get("collision_focus", "")

    prompt = f"""你是一位A股市场深度研究员。

## 当前市场环境（关键上下文）

**周期阶段**: {stage}
**当前策略**: {strategy}
**下一阶段风险**: {next_risk}
**需关注的变量关系**: {collision_focus}

"""

    if alerts:
        prompt += "**活跃比率警报**:\n"
        for a in alerts:
            direction = "↑" if a["z_score"] > 0 else "↓"
            prompt += f"- {a['ratio']}: z={a['z_score']:.1f} {direction} (当前:{a['value']:.3f}, 均值:{a['mean']:.3f})\n"
        prompt += "\n这些比率异常应该在你的分析中被重点考虑。\n"
    else:
        prompt += "当前无活跃比率警报。\n"

    prompt += f"""
## 研究问题
{question}

## 分析要求
1. **周期阶段约束**：你的分析必须在"{stage}"阶段的背景下进行。如果这个问题在别的阶段会有不同答案，请明确标注。
2. **比率交叉验证**：如果有活跃警报，请检查这些警报与你的研究问题之间是否存在因果或相关关系。
3. **预期差识别**：对这个问题，市场当前的共识是什么？与你分析得出的结论之间是否存在偏差？
4. **第一性原理**：从最基本的事实出发推导，不依赖二手结论。
5. **可验证预测**：提出1-3个可在未来N天验证的具体预测。
6. **不确定性标注**：每个结论标注 [确认]/[推断]/[假设]

## 输出格式
### 核心机制（≤200字）

### 证据链
- 支持: [来源/数据]
- 反面: [如果有]

### 周期阶段影响
- 在{stage}阶段，这个问题的结论是什么？
- 如果进入{next_risk}阶段，结论会如何变化？

### 可验证预测
1. [具体预测 + 验证时间]
2. ...

### 认知更新
- 推翻: [之前的什么认知被修正]
- 新增: [什么新认知]
- 不确定: [什么还需要验证]

用中文回答。简洁，不写套话。"""
    return prompt


def load_questions() -> list:
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("questions", [])


def save_questions(questions: list):
    with open(QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
                   "questions": questions}, f, ensure_ascii=False, indent=2)


def pick_question(questions: list) -> dict | None:
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    active = [q for q in questions if q.get("status") not in ("closed", "invalid")]
    if not active:
        return None
    active.sort(key=lambda q: priority_order.get(q.get("priority", "low"), 99))
    return active[0]


def run_research(question_text: str, question_id: str = "", use_dual: bool = True):
    """执行深度研究（v2 周期感知）。"""
    cycle = get_cycle_context()
    alerts = get_ratio_alerts()
    system_prompt = build_system_prompt(cycle, alerts, question_text)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 周期: {cycle.get('stage')}, 警报: {len(alerts)}")
    print(f"  研究: {question_text[:80]}...")

    prompt = question_text  # 用户消息简洁

    if use_dual:
        print("  使用双通道 (Ch2+Ch3)...")
        results = dual_research(prompt, system=system_prompt)
        ch2 = results.get("research", "")
        ch3 = results.get("parallel", "")
        merged = f"## 主研究 (Ch2)\n\n{ch2}\n\n## 交叉验证 (Ch3)\n\n{ch3}"
        return merged
    else:
        print("  使用 Ch2 单通道...")
        return research(prompt, system=system_prompt)


def main():
    if "--list" in sys.argv:
        questions = load_questions()
        if not questions:
            print("问题队列为空")
            return
        cycle = get_cycle_context()
        alerts = get_ratio_alerts()
        print(f"当前周期: {cycle.get('stage')} (置信度: {cycle.get('confidence')})")
        print(f"活跃警报: {len(alerts)} 个")
        print(f"\n问题队列 ({len(questions)} 个):")
        for q in questions:
            status = q.get("status", "open")
            priority = q.get("priority", "low")
            source = q.get("source", "")
            print(f"  [{priority:8s}] [{status:10s}] [{source:12s}] {q['question'][:100]}")
        return

    # --from-alerts: 先从警报生成问题
    if "--from-alerts" in sys.argv:
        print("从比率警报自动生成研究问题...")
        from alert_bridge import bridge as alert_bridge
        generated = alert_bridge(dry_run=False)
        if not generated:
            print("无新问题生成。")
        else:
            print(f"已生成 {len(generated)} 个问题。")

    if "--question" in sys.argv:
        idx = sys.argv.index("--question")
        question_text = sys.argv[idx + 1]
        question_id = datetime.now().strftime("%Y%m%d_%H%M")
        print(f"手动指定问题: {question_text[:80]}...")
    else:
        questions = load_questions()
        q = pick_question(questions)
        if not q:
            print("没有待研究的问题，退出。")
            return
        question_text = q["question"]
        question_id = q.get("id", datetime.now().strftime("%Y%m%d_%H%M"))
        print(f"自动选择: [{q.get('priority', 'low')}] {question_text[:80]}...")

    # 检查通道
    health = channel_health()
    use_dual = all(v["ok"] for v in health.values())
    if not health.get("research", {}).get("ok"):
        print("Ch2 (研究通道) 不可用。")
        return

    # 获取上下文用于文件头
    cycle = get_cycle_context()
    alerts = get_ratio_alerts()

    # 执行研究
    result = run_research(question_text, question_id, use_dual=use_dual)

    # 保存
    date_str = datetime.now().strftime("%Y%m%d")
    output_path = MODELS_DIR / f"{date_str}_{question_id}.md"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(f"# 深度研究: {question_text}\n\n")
        f.write(f"日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"周期阶段: {cycle.get('stage')} (置信度: {cycle.get('confidence')})\n")
        f.write(f"通道: {'Ch2+Ch3 双通道' if use_dual else 'Ch2'}\n")
        if alerts:
            f.write(f"活跃警报: {', '.join(a['ratio'] for a in alerts)}\n")
        f.write("\n---\n\n")
        f.write(result)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 研究完成 → {output_path}")

    # 更新问题状态
    questions = load_questions()
    updated = False
    for q in questions:
        if q.get("id") == question_id or q.get("question") == question_text:
            q["status"] = q.get("status", "open")
            q["last_researched"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            q["output_file"] = str(output_path)
            q["evidence_count"] = q.get("evidence_count", 0) + 1
            if q.get("evidence_count", 0) >= 3:
                q["status"] = "verified"
            # 记录研究时的周期阶段
            q["researched_in_stage"] = cycle.get("stage", "")
            updated = True
            break
    if updated:
        save_questions(questions)
        print("  问题状态已更新。")

    # 自动提取预测并加入追踪
    try:
        from forecast_closer import extract_predictions_from_text, commit_predictions
        predictions = extract_predictions_from_text(result)
        if predictions:
            for p in predictions:
                p["source_file"] = output_path.name
                p["source_date"] = date_str
            committed = commit_predictions(predictions)
            print(f"  预测追踪: 已提取 {len(committed)} 条可验证预测")
    except Exception:
        pass  # 非关键路径


if __name__ == "__main__":
    main()
