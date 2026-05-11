"""
Daily compress v2 — 认知操作系统核心。从"记录系统"升级为"操作系统"。

新能力:
  1. judge_cycle_stage()   — 天时定位：根据数据判定周期阶段
  2. record_ratios()       — 比率异常检测：记录关键比率，替代随机碰撞
  3. analyze_expectation_gap() — 预期差分析：共识 vs 现实的偏差
  4. condense_rule()       — 凝练：洞察必须含 适用条件+执行动作+失效信号
  5. write_digest_v2()     — 高维→低维 5 段日摘要

用法:
    python daily_compress.py --date 20260512
    python daily_compress.py gen-collision   # 生成碰撞对（保留旧接口）
    python daily_compress.py add-question "..."  # 添加问题
    python daily_compress.py ratios --date 20260512  # 记录今日比率
    python daily_compress.py cycle           # 判定当前周期阶段
"""

import json
import sys
import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path

LEARNING_DIR = Path("D:/1989n/stock_data/learning")
STOCK_DATA_DIR = Path("D:/1989n/stock_data")
RULES_FILE = LEARNING_DIR / "rules.json"
RATIO_BASELINES_FILE = LEARNING_DIR / "ratio_baselines.json"

# ── 关键比率定义 ──
KEY_RATIOS = {
    "炸板率": {"numerator": "炸板家数", "denominator": "触板家数", "description": "日内封板失败率，衡量短线情绪"},
    "晋级率": {"numerator": "今日连板数", "denominator": "昨日涨停数", "description": "首板→连板晋级率，衡量持续性"},
    "涨跌停比": {"numerator": "涨停家数", "denominator": "跌停家数(非ST)", "description": "极端情绪对比"},
    "强势占比": {"numerator": "强势板块数", "denominator": "全市场板块数", "description": "板块轮动广度"},
    "北向强度": {"numerator": "北向净流入", "denominator": "总成交额", "description": "外资相对参与度"},
    "大单强度": {"numerator": "大单净买入", "denominator": "总成交额", "description": "主力资金方向"},
    "红盘比": {"numerator": "上涨家数", "denominator": "全市场家数", "description": "赚钱效应广度"},
    "融资变化比": {"numerator": "融资余额变化", "denominator": "指数涨跌幅", "description": "杠杆资金弹性"},
}

# ── 周期阶段定义 ──
CYCLE_STAGES = {
    "冰点": {
        "index": 0,
        "description": "恐慌蔓延极致，物极必反前夜",
        "signals": {
            "limit_down_count": "高(≥15)",
            "red_ratio": "低(≤35%)",
            "volume_trend": "缩量或地量",
            "sentiment": "极度悲观",
        },
        "strategy": "极值反转，寻找错杀核心票",
        "collision_focus": "恐慌指标×资金流入方向",
    },
    "启动": {
        "index": 1,
        "description": "冰点后首现赚钱效应，新周期萌芽",
        "signals": {
            "limit_up_count": "从低位回升",
            "consecutive_up": "开始出现3板+",
            "volume_trend": "放量",
            "breadth": "涨跌比改善",
        },
        "strategy": "确认领头羊，追强不追弱",
        "collision_focus": "连板率×成交量变化率",
    },
    "主升": {
        "index": 2,
        "description": "赚钱效应扩散，模式内随便做",
        "signals": {
            "limit_up_count": "持续高位(≥40)",
            "consecutive_up": "连板梯队完整",
            "volume_trend": "持续放量",
            "breadth": "普涨",
        },
        "strategy": "跟随主线，不做杂毛",
        "collision_focus": "主线板块轮动速度×资金集中度",
    },
    "高潮": {
        "index": 3,
        "description": "情绪亢盛，最后的狂欢",
        "signals": {
            "炸板率": "开始上升(≥30%)",
            "limit_up_count": "高位但内部结构分化",
            "consecutive_up": "高位连板开始松动",
            "breadth": "指数涨但下跌家数增多",
        },
        "strategy": "减仓，警惕拐点",
        "collision_focus": "炸板率×连板率背离",
    },
    "衰退": {
        "index": 4,
        "description": "亏钱效应扩散，恐慌蔓延",
        "signals": {
            "limit_down_count": "上升",
            "consecutive_fail": "连板断裂率升高",
            "volume_trend": "缩量",
            "breadth": "普跌",
        },
        "strategy": "空仓或防御，不追任何模式",
        "collision_focus": "跌停家数×强势板块存活率",
    },
    "混沌": {
        "index": -1,
        "description": "无明确信号，多空交织",
        "strategy": "轻仓试探，等待方向明确",
        "collision_focus": "随机碰撞探索",
    },
}


# ═══════════════════════════════════════════
# 基础工具函数（保留旧接口兼容）
# ═══════════════════════════════════════════

def load_json(path: Path) -> dict:
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path: Path, data: dict):
    data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════
# 新核心功能 v2
# ═══════════════════════════════════════════

def _read_market_data(date_str: str = "") -> dict:
    """从现有数据文件中提取可用于周期判定的市场数据。"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    market = {
        "date": date_str,
        "limit_up": 0, "limit_down": 0,
        "consecutive_up_max": 0, "up_count": 0, "down_count": 0,
        "total_stocks": 5000, "volume_change_pct": 0,
        "northbound_net": 0, "large_order_net": 0,
        "strong_sectors": 0, "total_sectors": 60,
        "炸板_count": 0, "触板_count": 0,
        "margin_change_pct": 0, "index_change_pct": 0,
        "data_quality": "estimated",
    }

    # 尝试读取收盘复盘
    closing = STOCK_DATA_DIR / "closing_review.json"
    if closing.exists():
        try:
            data = json.loads(closing.read_text(encoding="utf-8"))
            market["limit_up"] = data.get("limit_up_count", 0)
            market["limit_down"] = data.get("limit_down_count", 0)
            market["up_count"] = data.get("up_count", 0)
            market["down_count"] = data.get("down_count", 0)
            market["consecutive_up_max"] = data.get("max_consecutive", 0)
            market["data_quality"] = "from_closing"
        except Exception:
            pass

    # 尝试读取盘中最后一份报告（获取更细的数据）
    reports = sorted(STOCK_DATA_DIR.glob("intel_report_*.json"), reverse=True)
    if reports:
        try:
            rpt = json.loads(reports[0].read_text(encoding="utf-8"))
            b = rpt.get("breadth", {})
            if b.get("limit_up", 0) > market["limit_up"]:
                market["limit_up"] = b.get("limit_up", 0)
                market["limit_down"] = b.get("limit_down", 0)
                market["up_count"] = b.get("up", 0)
                market["down_count"] = b.get("down", 0)
            market["data_quality"] = "from_intraday"
        except Exception:
            pass

    # 读取早间增强报告（获取新闻情绪）
    morning = STOCK_DATA_DIR / "morning_enhanced.json"
    if morning.exists():
        try:
            m = json.loads(morning.read_text(encoding="utf-8"))
            market["morning_available"] = True
        except Exception:
            market["morning_available"] = False

    return market


def judge_cycle_stage(market_data: dict = None, date_str: str = "") -> dict:
    """判定当前周期阶段（天时定位）。

    返回: {"stage": "主升|冰点|...", "confidence": 0.7, "signals": [...], "next_stage_risk": "..."}
    """
    if market_data is None:
        market_data = _read_market_data(date_str)

    lu = market_data.get("limit_up", 0)
    ld = market_data.get("limit_down", 0)
    up = market_data.get("up_count", 0)
    down = market_data.get("down_count", 0)
    total = max(market_data.get("total_stocks", 5000), 1)
    consecutive_max = market_data.get("consecutive_up_max", 0)
    quality = market_data.get("data_quality", "estimated")

    red_ratio = up / max(up + down, 1)
    limit_ratio = lu / max(ld, 1) if ld > 0 else (lu if lu > 0 else 1)
    lu_level = "高" if lu >= 40 else ("中" if lu >= 20 else "低")
    ld_level = "高" if ld >= 15 else ("中" if ld >= 5 else "低")

    signals = []
    scores = {stage: 0 for stage in CYCLE_STAGES}

    # 冰点信号
    if ld >= 15:
        scores["冰点"] += 3
        signals.append(f"跌停{ld}只(≥15)，恐慌信号")
    if red_ratio <= 0.35:
        scores["冰点"] += 2
        signals.append(f"红盘比{red_ratio:.0%}，极度低迷")
    if lu <= 10:
        scores["冰点"] += 1
    if consecutive_max <= 2:
        scores["冰点"] += 1

    # 启动信号
    if 10 <= lu <= 30 and consecutive_max >= 3:
        scores["启动"] += 3
        signals.append(f"涨停{lu}只+{consecutive_max}板，启动特征")
    if red_ratio >= 0.45 and ld <= 5:
        scores["启动"] += 2

    # 主升信号
    if lu >= 40 and consecutive_max >= 5:
        scores["主升"] += 4
        signals.append(f"涨停{lu}只，{consecutive_max}板龙头，主升确认")
    if red_ratio >= 0.55 and ld <= 3:
        scores["主升"] += 2

    # 高潮信号
    if lu >= 40 and consecutive_max >= 5:
        scores["高潮"] += 2
    zhaban_count = market_data.get("炸板_count", 0)
    if zhaban_count > 0:
        chuban_count = max(market_data.get("触板_count", 1), 1)
        zhaban_rate = zhaban_count / chuban_count
        if zhaban_rate >= 0.30:
            scores["高潮"] += 3
            signals.append(f"炸板率{zhaban_rate:.0%}，高潮分歧加剧")
    if red_ratio < 0.5 and lu >= 30:
        scores["高潮"] += 2
        signals.append(f"指数偏强但红盘比{red_ratio:.0%}，结构分化")

    # 衰退信号
    if ld >= 8 and lu <= 20:
        scores["衰退"] += 3
        signals.append(f"跌停{ld}只+涨停仅{lu}只，衰退特征")
    if consecutive_max <= 3 and red_ratio < 0.45:
        scores["衰退"] += 2

    # 混沌：当没有明确信号或多个信号打架
    top_score = max(scores.values())
    if top_score == 0:
        best_stage = "混沌"
        confidence = 0.3
    elif top_score <= 2:
        # 有微弱信号但不强
        candidates = [s for s, v in scores.items() if v == top_score]
        if len(candidates) > 1:
            best_stage = "混沌"
            confidence = 0.4
        else:
            best_stage = candidates[0]
            confidence = 0.5
    else:
        candidates = [s for s, v in scores.items() if v == top_score]
        best_stage = candidates[0]
        confidence = min(0.5 + 0.15 * top_score, 0.9)

    # 确定相邻风险
    stage_order = ["冰点", "启动", "主升", "高潮", "衰退"]
    next_risk = ""
    if best_stage in stage_order:
        idx = stage_order.index(best_stage)
        if best_stage == "主升":
            next_risk = "高潮"
        elif best_stage == "高潮":
            next_risk = "衰退"
        elif best_stage == "启动":
            next_risk = "主升（确认后）或 冰点（假突破）"
        elif best_stage == "冰点":
            next_risk = "启动（确认后）或 继续探底"
        elif best_stage == "衰退":
            next_risk = "冰点（极致恐慌后）"

    return {
        "stage": best_stage,
        "confidence": round(confidence, 2),
        "signals": signals,
        "next_stage_risk": next_risk,
        "data_quality": quality,
        "date": market_data.get("date", ""),
        "strategy_hint": CYCLE_STAGES.get(best_stage, {}).get("strategy", ""),
        "collision_focus": CYCLE_STAGES.get(best_stage, {}).get("collision_focus", ""),
    }


def record_ratios(date_str: str = "", market_data: dict = None,
                  manual_values: dict = None) -> dict:
    """记录今日关键比率快照。

    无实际数据时用 manual_values 或按 0 记录（标注为占位）。
    """
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    if market_data is None:
        market_data = _read_market_data(date_str)

    snapshot = {"date": date_str, "ratios": {}, "data_quality": market_data.get("data_quality", "estimated")}

    for ratio_name, definition in KEY_RATIOS.items():
        # 优先使用手动传入的值
        if manual_values and ratio_name in manual_values:
            raw = manual_values[ratio_name]
            snapshot["ratios"][ratio_name] = {
                "value": raw, "definition": definition["description"],
                "source": "manual",
            }
        else:
            # 从现有数据推算（不准确，标注）
            snapshot["ratios"][ratio_name] = {
                "value": 0, "definition": definition["description"],
                "source": "placeholder", "note": "需要实际市场数据填充",
            }

    # 追加到 baselines 文件
    baselines = load_json(RATIO_BASELINES_FILE)
    entries = baselines.get("entries", [])
    entries.append(snapshot)
    if len(entries) > 60:
        entries = entries[-60:]

    # 计算每个比率的滚动统计
    for ratio_name in KEY_RATIOS:
        values = [
            e["ratios"].get(ratio_name, {}).get("value", 0)
            for e in entries
            if e["ratios"].get(ratio_name, {}).get("source") != "placeholder"
        ]
        if len(values) >= 5:
            mean = sum(values) / len(values)
            variance = sum((v - mean) ** 2 for v in values) / len(values)
            std = variance ** 0.5
            current = snapshot["ratios"][ratio_name]["value"]
            z_score = (current - mean) / std if std > 0 else 0
            snapshot["ratios"][ratio_name]["mean"] = round(mean, 4)
            snapshot["ratios"][ratio_name]["std"] = round(std, 4)
            snapshot["ratios"][ratio_name]["z_score"] = round(z_score, 2)
            snapshot["ratios"][ratio_name]["alert"] = "triggered" if abs(z_score) >= 2 else "normal"

    baselines["entries"] = entries
    save_json(RATIO_BASELINES_FILE, baselines)

    return snapshot


def analyze_expectation_gap(market_data: dict = None,
                            cycle_stage: dict = None) -> dict:
    """预期差分析：市场共识 vs 真实情况。

    返回市场在哪些方向上可能存在错误定价。
    """
    if market_data is None:
        market_data = _read_market_data()
    if cycle_stage is None:
        cycle_stage = judge_cycle_stage(market_data)

    stage = cycle_stage.get("stage", "混沌")
    gaps = []

    # 不同阶段有不同的典型预期差
    if stage == "冰点":
        gaps.append({
            "dimension": "恐慌定价",
            "market_consensus": "市场认为风险会持续恶化",
            "reality_check": "利空是否已经充分反映在价格中？个股基本面是否受损？",
            "potential_gap": "如果利空未伤及个股基本面 → 正预期差 → 被错杀的黄金坑",
            "verify_by": "观察次日是否出现资金回流修复"
        })
    elif stage == "高潮":
        gaps.append({
            "dimension": "乐观定价",
            "market_consensus": "市场认为利好会持续推动上涨",
            "reality_check": "利好是否已被充分定价？连板结构是否开始松动？",
            "potential_gap": "如果利好已被透支 + 内部结构分化 → 负预期差 → 回调风险",
            "verify_by": "观察炸板率是否上升、高位连板是否开始断板"
        })
    elif stage == "主升":
        gaps.append({
            "dimension": "持续性定价",
            "market_consensus": "市场认为主线会持续扩散",
            "reality_check": "主线板块内是否出现高低切换？强势股集中度是在上升还是下降？",
            "potential_gap": "如果资金从高位向低位迁移 → 板块内轮动而非整体走弱",
            "verify_by": "观察主线内高位票和低位票的相对强度"
        })
    elif stage == "衰退":
        gaps.append({
            "dimension": "恐慌蔓延定价",
            "market_consensus": "市场认为所有板块都危险",
            "reality_check": "是否有板块逆势抗跌？是否有资金在悄悄吸筹？",
            "potential_gap": "如果某板块在衰退期逆势走强 → 可能是下一轮主线的先兆",
            "verify_by": "观察抗跌板块的持续性和资金流入"
        })

    # 通用：龙头 vs 跟风的预期差
    gaps.append({
        "dimension": "辨识度 vs 预期差",
        "market_consensus": "资金追逐辨识度最高的标的（龙头）",
        "reality_check": "龙头的定价是否已经充分反映了它的辨识度优势？是否有被忽视的二线标的？",
        "potential_gap": "如果龙头被过度定价 → 跟风中存在预期差 → 补涨机会",
        "verify_by": "对比龙头和跟风的涨幅差距、资金流向"
    })

    return {
        "date": market_data.get("date", ""),
        "cycle_stage": stage,
        "gaps": gaps,
        "action_required": len(gaps) > 0,
    }


def condense_rule(insight_text: str, cycle_stage: str = "",
                  source_data: str = "") -> dict:
    """把认知增益凝练为可执行规则。

    强制输出三元组：适用条件 + 执行动作 + 失效信号。
    如果不能同时填满三个字段 → 标记为"未凝练"。
    """
    rule = {
        "condition": "",       # 适用条件（含周期阶段）
        "action": "",          # 执行动作
        "failure_signal": "",  # 失效信号
        "cycle_stage": cycle_stage,
        "source": source_data,
        "is_condensed": False,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_verified": "",
        "verified_count": 0,
    }
    return rule


def commit_rule(rule: dict) -> str:
    """将凝练的规则写入规则库。"""
    data = load_json(RULES_FILE)
    rules = data.get("rules", [])
    rule["id"] = datetime.now().strftime("R%Y%m%d_%H%M%S")
    rules.append(rule)
    data["rules"] = rules
    save_json(RULES_FILE, data)
    return rule["id"]


def write_digest_v2(date_str: str, cycle_stage: dict, ratio_snapshot: dict,
                    expectation_gaps: dict, rules_condensed: list,
                    mistake: str = "", feedback: str = "",
                    forecast_updates: dict = None,
                    efficiency: dict = None) -> dict:
    """v2 日压缩摘要 — 高维→低维 5 段结构。

    Tier 1: 天时定位（周期阶段+置信度）
    Tier 2: 比率异常（触发的警报）
    Tier 3: 预期差发现
    Tier 4: 凝练规则（必须三元组填满）
    Tier 5: 自检（错误+心态+ego挑战）
    """
    # 提取触发警报的比率
    triggered = {}
    for name, data in ratio_snapshot.get("ratios", {}).items():
        if data.get("alert") == "triggered":
            triggered[name] = {
                "value": data.get("value", 0),
                "z_score": data.get("z_score", 0),
            }

    # 提取预期差方向
    gap_summary = []
    for g in expectation_gaps.get("gaps", []):
        gap_summary.append({
            "dimension": g["dimension"],
            "consensus": g["market_consensus"],
            "potential_gap": g["potential_gap"],
        })

    digest = {
        "version": 2,
        "date": date_str,

        # Tier 1: 天时
        "cycle_stage": {
            "stage": cycle_stage.get("stage", "未知"),
            "confidence": cycle_stage.get("confidence", 0),
            "signals": cycle_stage.get("signals", []),
            "strategy_hint": cycle_stage.get("strategy_hint", ""),
            "next_stage_risk": cycle_stage.get("next_stage_risk", ""),
        },

        # Tier 2: 比率异常
        "ratio_alerts": {
            "triggered": triggered,
            "collision_focus": cycle_stage.get("collision_focus", ""),
            "data_quality": ratio_snapshot.get("data_quality", "unknown"),
        },

        # Tier 3: 预期差
        "expectation_gaps": gap_summary,

        # Tier 4: 凝练
        "rules_today": [
            {"id": r.get("id", "pending"), "condition": r.get("condition", ""),
             "action": r.get("action", ""), "failure_signal": r.get("failure_signal", ""),
             "is_condensed": r.get("is_condensed", False)}
            for r in rules_condensed
        ],
        "rules_condensed_count": sum(1 for r in rules_condensed if r.get("is_condensed")),
        "rules_total_count": len(rules_condensed),

        # Tier 5: 自检
        "self_check": {
            "mistake": mistake,
            "mistake_root_cause": "",  # 知识盲区/逻辑跳跃/惯性输出/数据缺失/情绪干扰
            "ego_challenge": "",        # 今天有什么证据挑战了我的核心假设？
            "discipline_breach": "",    # 是否做了模式外操作？
            "feedback": feedback,
        },

        "forecast_updates": forecast_updates or {},
        "efficiency": efficiency or {},
        "compressed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    path = LEARNING_DIR / f"daily_digest_{date_str}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)

    # 更新索引
    index = load_json(LEARNING_DIR / "daily_digest_index.json")
    digests = index.get("digests", [])
    digests.append({
        "date": date_str,
        "version": 2,
        "stage": cycle_stage.get("stage", ""),
        "alerts": len(triggered),
        "rules_condensed": digest["rules_condensed_count"],
        "file": str(path),
    })
    if len(digests) > 60:
        digests = digests[-60:]
    index["digests"] = digests
    save_json(LEARNING_DIR / "daily_digest_index.json", index)

    return digest


def run_full_compress(date_str: str = "", mistake: str = "",
                      feedback: str = "", manual_ratios: dict = None,
                      condensed_rules: list = None) -> dict:
    """运行完整 v2 日压缩管道。"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    print(f"=== 日压缩 v2 ({date_str}) ===")

    # Step 1: 天时定位
    print("[Tier 1] 天时定位...")
    market_data = _read_market_data(date_str)
    cycle = judge_cycle_stage(market_data, date_str)
    print(f"  周期阶段: {cycle['stage']} (置信度: {cycle['confidence']})")
    print(f"  信号: {cycle['signals']}")

    # Step 2: 比率快照
    print("[Tier 2] 比率快照...")
    ratios = record_ratios(date_str, market_data, manual_ratios)
    triggered = sum(1 for k, v in ratios.get("ratios", {}).items() if v.get("alert") == "triggered")
    print(f"  记录 {len(ratios['ratios'])} 个比率, {triggered} 个触发警报")

    # Step 3: 预期差
    print("[Tier 3] 预期差分析...")
    gaps = analyze_expectation_gap(market_data, cycle)
    print(f"  发现 {len(gaps['gaps'])} 个预期差维度")

    # Step 4: 凝练规则
    print("[Tier 4] 凝练规则...")
    rules = condensed_rules or []
    for r in rules:
        if not r.get("id"):
            rule_entry = condense_rule(
                insight_text=r.get("insight", ""),
                cycle_stage=cycle.get("stage", ""),
                source_data=r.get("source", ""),
            )
            rule_entry.update(r)
            if rule_entry.get("condition") and rule_entry.get("action") and rule_entry.get("failure_signal"):
                rule_entry["is_condensed"] = True
        commit_rule(rule_entry)
    print(f"  规则: {len(rules)} 条, 凝练达标: {sum(1 for r in rules if r.get('is_condensed'))}")

    # Step 5: 写摘要
    print("[Tier 5] 写入摘要...")
    digest = write_digest_v2(
        date_str=date_str,
        cycle_stage=cycle,
        ratio_snapshot=ratios,
        expectation_gaps=gaps,
        rules_condensed=rules,
        mistake=mistake,
        feedback=feedback,
    )
    print(f"  摘要已写入: daily_digest_{date_str}.json")

    return digest


# ═══════════════════════════════════════════
# 保留旧接口（向后兼容）
# ═══════════════════════════════════════════

def add_question(question: str, priority: str = "medium", source: str = ""):
    data = load_json(LEARNING_DIR / "open_questions.json")
    questions = data.get("questions", [])
    qid = datetime.now().strftime("%Y%m%d_%H%M%S")
    questions.append({
        "id": qid, "question": question, "priority": priority,
        "status": "open", "source": source,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "last_researched": "", "evidence_count": 0, "output_file": "",
    })
    data["questions"] = questions
    save_json(LEARNING_DIR / "open_questions.json", data)
    return qid


def update_question(question_id: str, **kwargs):
    data = load_json(LEARNING_DIR / "open_questions.json")
    for q in data.get("questions", []):
        if q.get("id") == question_id:
            q.update(kwargs)
            break
    save_json(LEARNING_DIR / "open_questions.json", data)


def add_collision(variable_a: str, variable_b: str, observation: str = ""):
    data = load_json(LEARNING_DIR / "collision_log.json")
    entries = data.get("entries", [])
    entries.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "collision": [variable_a, variable_b],
        "observation": observation,
        "follow_up": "",
    })
    if len(entries) > 30:
        entries = entries[-30:]
    data["entries"] = entries
    save_json(LEARNING_DIR / "collision_log.json", data)


def add_forecast(prediction: str, verify_date: str, data_source: str = ""):
    data = load_json(LEARNING_DIR / "forecast_tracker.json")
    forecasts = data.get("forecasts", [])
    forecasts.append({
        "id": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "prediction": prediction,
        "made_date": datetime.now().strftime("%Y-%m-%d"),
        "verify_date": verify_date,
        "data_source": data_source,
        "status": "pending", "result": "",
    })
    data["forecasts"] = forecasts
    data["stats"]["total"] = len(forecasts)
    save_json(LEARNING_DIR / "forecast_tracker.json", data)


def verify_forecast(forecast_id: str, correct: bool, note: str = ""):
    data = load_json(LEARNING_DIR / "forecast_tracker.json")
    stats = data.get("stats", {"correct": 0, "wrong": 0, "verified": 0})
    for f in data.get("forecasts", []):
        if f.get("id") == forecast_id:
            f["status"] = "correct" if correct else "wrong"
            f["result"] = note
            if correct:
                stats["correct"] = stats.get("correct", 0) + 1
            else:
                stats["wrong"] = stats.get("wrong", 0) + 1
            stats["verified"] = stats.get("verified", 0) + 1
            break
    data["stats"] = stats
    save_json(LEARNING_DIR / "forecast_tracker.json", data)


def log_efficiency(total_calls: int, useful_calls: int, redundant_searches: int,
                   preload_misses: list | None = None):
    data = load_json(LEARNING_DIR / "efficiency_daily.json")
    days = data.get("days", [])
    days.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total_calls": total_calls,
        "useful_calls": useful_calls,
        "redundant_searches": redundant_searches,
        "preload_misses": preload_misses or [],
        "efficiency_rate": round(useful_calls / max(total_calls, 1), 3),
    })
    if len(days) > 30:
        days = days[-30:]
    data["days"] = days
    save_json(LEARNING_DIR / "efficiency_daily.json", data)


def generate_collision_pair() -> list:
    import random
    variables = [
        "融资余额变化率", "涨停家数", "连板率", "北向资金净流入", "成交量/前5日均量",
        "跌停家数", "炸板率", "强势板块数量", "全市场上涨比例", "大单净流入",
        "两融余额", "沪深300波动率", "板块轮动速度", "ST跌停家数", "次新股换手率",
    ]
    a, b = random.sample(variables, 2)
    return [a, b]


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Daily Compress v2 — 认知操作系统")
    parser.add_argument("--date", default=datetime.now().strftime("%Y%m%d"))
    parser.add_argument("--mistake", default="")
    parser.add_argument("--feedback", default="")
    parser.add_argument("--ego-challenge", default="")

    sub = parser.add_subparsers(dest="command")

    # v2 命令
    sub.add_parser("cycle", help="判定当前周期阶段")
    sub.add_parser("ratios", help="记录今日关键比率")
    sub.add_parser("gaps", help="预期差分析")
    sub.add_parser("full", help="运行完整 v2 日压缩管道")

    # 旧接口
    sub.add_parser("gen-collision", help="生成碰撞对")
    p = sub.add_parser("add-question")
    p.add_argument("text")
    sub.add_parser("list-questions", help="列出问题队列")

    args = parser.parse_args()

    if args.command == "cycle":
        result = judge_cycle_stage(date_str=args.date)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "ratios":
        result = record_ratios(date_str=args.date)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "gaps":
        market = _read_market_data(args.date)
        cycle = judge_cycle_stage(market, args.date)
        result = analyze_expectation_gap(market, cycle)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif args.command == "full":
        result = run_full_compress(
            date_str=args.date,
            mistake=args.mistake,
            feedback=args.feedback,
        )
        print(json.dumps({
            "date": result["date"],
            "stage": result["cycle_stage"]["stage"],
            "alerts": len(result["ratio_alerts"]["triggered"]),
            "gaps": len(result["expectation_gaps"]),
            "rules_condensed": result["rules_condensed_count"],
        }, ensure_ascii=False, indent=2))
    elif args.command == "gen-collision":
        pair = generate_collision_pair()
        print(json.dumps({"collision": pair}, ensure_ascii=False))
    elif args.command == "add-question":
        qid = add_question(args.text)
        print(f"问题已添加: {qid}")
    elif args.command == "list-questions":
        data = load_json(LEARNING_DIR / "open_questions.json")
        for q in data.get("questions", []):
            print(f"[{q.get('priority','low'):8s}] [{q.get('status','open'):10s}] {q['question'][:100]}")
    else:
        print(f"Daily Compress v2. Date: {args.date}")
        print("Commands: cycle | ratios | gaps | full | gen-collision | add-question | list-questions")


if __name__ == "__main__":
    main()
