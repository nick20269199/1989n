"""
警报桥接模块 — 当比率偏离触发警报时，自动生成研究问题并加入队列。

这是比率异常检测 → 深度研究的自动化桥梁。

用法:
    python alert_bridge.py                    # 检查最新比率快照，触发的生成问题
    python alert_bridge.py --dry-run          # 仅显示会生成什么，不实际写入
    python alert_bridge.py --date 20260512    # 指定日期
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daily_compress import (
    load_json, save_json,
    LEARNING_DIR, RATIO_BASELINES_FILE, KEY_RATIOS,
)

QUESTIONS_FILE = LEARNING_DIR / "open_questions.json"

# 每种比率异常对应的研究问题模板
ALERT_QUESTION_TEMPLATES = {
    "炸板率": {
        "high": "炸板率异常升高(z={z})：封板失败率上升是短线资金撤离信号还是市场分歧加剧？当前周期阶段下这意味着什么？",
        "low": "炸板率异常降低(z={z})：封板成功率极高是否意味着短线情绪过度乐观？历史上类似情况出现后N天走势如何？",
    },
    "晋级率": {
        "high": "晋级率异常升高(z={z})：首板→连板转化率超预期，是否预示着新的主线正在形成？连板梯队结构是否完整？",
        "low": "晋级率异常降低(z={z})：涨停股次日无法连板，是市场缺乏持续性还是轮动过快？对短线策略有何影响？",
    },
    "涨跌停比": {
        "high": "涨跌停比异常升高(z={z})：极端做多情绪 vs 跌停数量极少的组合在历史上持续了多久？后续演化的典型路径是什么？",
        "low": "涨跌停比异常降低(z={z})：跌停数量相对涨停异常增多，是局部恐慌还是系统性风险信号？需要关注哪些确认指标？",
    },
    "强势占比": {
        "high": "强势板块占比异常升高(z={z})：板块普涨是否意味着资金分散、主线不清晰？还是全面牛市的前兆？",
        "low": "强势板块占比异常降低(z={z})：仅少数板块强势，是资金集中主升还是市场疲弱的前兆？强势板块内部的持续性如何？",
    },
    "北向强度": {
        "high": "北向资金相对强度异常升高(z={z})：外资加速流入的驱动因素是什么？历史上北向强度飙升后N天指数表现如何？",
        "low": "北向资金相对强度异常降低(z={z})：外资流出/缩量是否与人民币汇率、外围市场相关？是否是先行指标？",
    },
    "大单强度": {
        "high": "大单净买入占比异常升高(z={z})：主力资金加速流入哪些板块？大单强度与后续N日涨幅的相关性如何？",
        "low": "大单净买入占比异常降低(z={z})：主力资金撤退是调仓还是系统性减仓？大单流出的股票后续表现如何？",
    },
    "红盘比": {
        "high": "红盘比异常升高(z={z})：极度普涨后市场通常如何演化？普涨日的赚钱效应能否持续到次日？",
        "low": "红盘比异常降低(z={z})：极度普跌是恐慌末期的信号还是下跌中继？历史上类似红盘比出现后N天的反弹概率？",
    },
    "融资变化比": {
        "high": "融资余额相对指数异常升高(z={z})：杠杆资金加速入场是趋势确认还是过热信号？融资变化比的历史阈值是多少？",
        "low": "融资余额相对指数异常降低(z={z})：杠杆资金撤退是被动平仓还是主动降杠杆？对市场流动性的影响？",
    },
}


def find_alerts(date_str: str = "") -> list:
    """从最新比率快照中找到触发警报的比率。"""
    data = load_json(RATIO_BASELINES_FILE)
    entries = data.get("entries", [])
    if not entries:
        return []

    # 取最新快照
    if date_str:
        target = [e for e in entries if e["date"] == date_str]
        snapshot = target[0] if target else entries[-1]
    else:
        snapshot = entries[-1]

    alerts = []
    for ratio_name, info in snapshot.get("ratios", {}).items():
        if info.get("alert") == "triggered":
            z = info.get("z_score", 0)
            direction = "high" if z > 0 else "low"
            alerts.append({
                "ratio": ratio_name,
                "z_score": z,
                "direction": direction,
                "value": info.get("value", 0),
                "mean": info.get("mean", 0),
                "std": info.get("std", 0),
            })
    return alerts


def alert_to_question(alert: dict, cycle_stage: str = "") -> dict:
    """将警报转化为研究问题。"""
    ratio = alert["ratio"]
    direction = alert["direction"]
    z = alert["z_score"]
    templates = ALERT_QUESTION_TEMPLATES.get(ratio, {})
    template = templates.get(direction, f"{ratio}异常偏离(z={z})，需要深入分析原因和影响")

    question_text = template.format(z=z)
    if cycle_stage:
        question_text = f"[{cycle_stage}阶段] {question_text}"

    return {
        "question": question_text,
        "priority": "high" if abs(z) >= 3 else "medium",
        "source": "ratio_alert",
        "alert_detail": alert,
    }


def bridge(date_str: str = "", dry_run: bool = False,
           cycle_stage: str = "") -> list:
    """主桥接函数：警报 → 研究问题。"""
    alerts = find_alerts(date_str)
    if not alerts:
        print("无触发警报，无需生成研究问题。")
        return []

    print(f"发现 {len(alerts)} 个触发警报:")

    questions_generated = []
    for alert in alerts:
        q = alert_to_question(alert, cycle_stage)
        print(f"  [{alert['ratio']}] z={alert['z_score']:.1f} → {q['question'][:100]}...")

        if not dry_run:
            # 检查是否已有类似问题（去重）
            existing = load_json(QUESTIONS_FILE)
            existing_questions = existing.get("questions", [])
            duplicate = False
            for eq in existing_questions:
                if alert["ratio"] in eq.get("question", "") and eq.get("status") not in ("closed", "invalid"):
                    duplicate = True
                    break

            if duplicate:
                print(f"    → 跳过（已有类似未关闭问题）")
                continue

            # 添加新问题
            qid = datetime.now().strftime("%Y%m%d_%H%M%S") + f"_{alert['ratio']}"
            new_q = {
                "id": qid,
                "question": q["question"],
                "priority": q["priority"],
                "status": "open",
                "source": "ratio_alert",
                "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "last_researched": "",
                "evidence_count": 0,
                "output_file": "",
                "alert_context": alert,
            }
            existing_questions.append(new_q)
            save_json(QUESTIONS_FILE, {"questions": existing_questions})
            questions_generated.append(new_q)
            print(f"    → 已添加 (id: {qid})")

    print(f"\n生成 {len(questions_generated)} 个新研究问题 ({len(alerts)} 个警报, {'已去重' if not dry_run else 'dry-run'})")
    return questions_generated


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    date_str = ""
    for i, arg in enumerate(sys.argv):
        if arg == "--date" and i + 1 < len(sys.argv):
            date_str = sys.argv[i + 1]

    # 获取周期阶段
    cycle_stage = ""
    try:
        from daily_compress import judge_cycle_stage
        result = judge_cycle_stage(date_str=date_str)
        cycle_stage = result.get("stage", "")
    except Exception:
        pass

    bridge(date_str=date_str, dry_run=dry_run, cycle_stage=cycle_stage)
