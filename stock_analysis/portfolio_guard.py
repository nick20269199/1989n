"""
持仓守卫 v1 — 认知环 → 投资组合的桥梁。

功能:
  1. 加载当前持仓 + 周期阶段 + 比率警报
  2. 逐票评估：周期适配性 / 警报相关性 / 止损距离
  3. 输出组合级风险评估和具体建议
  4. 可集成到盘前简报和对抗审查中

用法:
    python portfolio_guard.py                    # 完整组合检查
    python portfolio_guard.py --brief            # 简洁模式（适合拼入报告）
    python portfolio_guard.py --code 000062      # 单票检查
"""

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from daily_compress import (
    judge_cycle_stage, load_json,
    RATIO_BASELINES_FILE, KEY_RATIOS,
)

# 从 portfolio.json 动态加载持仓（唯一信源）
PROJECT_DIR = Path(__file__).parent
PORTFOLIO_FILE = PROJECT_DIR / "data" / "portfolio.json"

# 简单持仓类型映射（成本价越高越接近成长，越低越接近题材）
def _classify_type(sector: str, cost: float) -> str:
    sector_lower = sector.lower()
    if any(k in sector_lower for k in ["银行", "保险", "电力", "公用", "交通", "高速"]):
        return "价值"
    if any(k in sector_lower for k in ["半导体", "芯片", "软件", "生物", "医疗", "新能源"]):
        return "成长"
    if any(k in sector_lower for k in ["地产", "化工", "有色", "钢铁", "煤炭", "基建"]):
        return "周期"
    return "题材"

def _load_portfolio() -> list[dict]:
    """从 portfolio.json 加载持仓，自动计算止损价（-7%）。"""
    if not PORTFOLIO_FILE.exists():
        print(f"[WARN] {PORTFOLIO_FILE} 不存在，使用空持仓")
        return []
    try:
        data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        holdings = data.get("holdings", [])
        portfolio = []
        for h in holdings:
            cost = h["cost"]
            stop = round(cost * 0.93, 2)  # -7% 硬止损
            portfolio.append({
                "code": h["code"],
                "name": h["name"],
                "shares": h["shares"],
                "cost": cost,
                "stop": stop,
                "sector": h.get("sector", ""),
                "type": _classify_type(h.get("sector", ""), cost),
            })
        return portfolio
    except Exception as e:
        print(f"[ERROR] 加载持仓失败: {e}")
        return []

PORTFOLIO = _load_portfolio()

# 各周期阶段的持仓策略
STAGE_PORTFOLIO_RULES = {
    "冰点": {
        "max_positions": 3,
        "max_single_pct": 10,
        "strategy": "极轻仓试探，单一票不超过10%，总仓位不超过30%",
        "preferred_types": ["价值", "防御"],
        "avoid_types": ["题材"],
        "action": "只保留被错杀的核心票，其余清仓",
    },
    "启动": {
        "max_positions": 5,
        "max_single_pct": 20,
        "strategy": "确认领头羊后逐步加仓，追强不追弱",
        "preferred_types": ["成长", "题材"],
        "avoid_types": [],
        "action": "加仓确认走强的龙头，淘汰弱势票",
    },
    "主升": {
        "max_positions": 8,
        "max_single_pct": 25,
        "strategy": "跟随主线，不做杂毛，可适度集中",
        "preferred_types": ["成长", "题材"],
        "avoid_types": ["防御"],
        "action": "持仓主线，汰弱留强",
    },
    "高潮": {
        "max_positions": 5,
        "max_single_pct": 15,
        "strategy": "只卖不买，逐步减仓锁定利润",
        "preferred_types": [],
        "avoid_types": ["题材"],
        "action": "每涨一天减一部分仓位，不追任何新仓",
    },
    "衰退": {
        "max_positions": 2,
        "max_single_pct": 10,
        "strategy": "空仓或极轻仓防御，不追任何模式",
        "preferred_types": ["防御"],
        "avoid_types": ["成长", "题材"],
        "action": "清掉所有题材和成长仓位，只留防御或空仓",
    },
    "混沌": {
        "max_positions": 3,
        "max_single_pct": 10,
        "strategy": "信号不明确，轻仓等待方向",
        "preferred_types": [],
        "avoid_types": [],
        "action": "维持现有仓位不操作，等待明确信号",
    },
}

# 比率警报 → 行业影响映射
RATIO_SECTOR_MAP = {
    "炸板率": {"affected": ["题材"], "meaning": "短线情绪恶化 → 题材股首当其冲"},
    "晋级率": {"affected": ["题材"], "meaning": "连板失效 → 题材接力资金不足"},
    "涨跌停比": {"affected": ["题材", "成长"], "meaning": "极端情绪 → 波动率上升"},
    "强势占比": {"affected": ["成长"], "meaning": "板块分散 → 成长股选股难度增加"},
    "北向强度": {"affected": ["价值", "成长"], "meaning": "外资流向变化 → 大盘价值影响最大"},
    "大单强度": {"affected": ["题材", "成长"], "meaning": "主力方向 → 跟随主力调整"},
    "红盘比": {"affected": ["所有"], "meaning": "整体赚钱效应 → 所有仓位受影响"},
    "融资变化比": {"affected": ["题材", "成长"], "meaning": "杠杆变动 → 高风险仓位需要关注"},
}


def get_alerts() -> list:
    """获取当前活跃比率警报。"""
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


def check_position(position: dict, cycle: dict, alerts: list,
                   current_prices: dict = None) -> dict:
    """逐票检查：周期适配 + 警报相关 + 止损距离。"""
    code = position["code"]
    name = position["name"]
    sector = position["sector"]
    ptype = position["type"]
    stage = cycle.get("stage", "混沌")

    checks = []
    risk_score = 0  # 0-10, 越高越危险

    # 1. 周期适配检查
    stage_rules = STAGE_PORTFOLIO_RULES.get(stage, STAGE_PORTFOLIO_RULES["混沌"])
    if ptype in stage_rules.get("avoid_types", []):
        checks.append({
            "level": "warning",
            "check": "周期适配",
            "detail": f"当前{stage}阶段应避开{ptype}类型，但{name}({code})属于{ptype}",
        })
        risk_score += 3

    # 2. 比率警报相关性
    relevant_alerts = []
    for alert in alerts:
        ratio_name = alert["ratio"]
        affected = RATIO_SECTOR_MAP.get(ratio_name, {}).get("affected", [])
        if ptype in affected or "所有" in affected:
            relevant_alerts.append(alert)

    if relevant_alerts:
        alert_names = [a["ratio"] for a in relevant_alerts]
        direction = "↑" if relevant_alerts[0]["z_score"] > 0 else "↓"
        checks.append({
            "level": "alert",
            "check": "比率警报",
            "detail": f"{', '.join(alert_names)} 警报{direction}与{ptype}类型相关",
        })
        risk_score += len(relevant_alerts) * 2

    # 3. 止损距离检查（如果有当前价）
    if current_prices and code in current_prices:
        current = current_prices[code]
        stop = position["stop"]
        distance_pct = (current - stop) / stop * 100
        if distance_pct <= 3:
            checks.append({
                "level": "critical",
                "check": "止损逼近",
                "detail": f"{name} 距止损仅{distance_pct:.1f}% (当前{current}, 止损{stop})",
            })
            risk_score += 5
        elif distance_pct <= 7:
            checks.append({
                "level": "warning",
                "check": "止损接近",
                "detail": f"{name} 距止损{distance_pct:.1f}%",
            })
            risk_score += 2

    # 4. 成本距止损检查（不依赖当前价）
    cost = position["cost"]
    stop = position["stop"]
    max_loss_pct = (cost - stop) / cost * 100
    if max_loss_pct > 10:
        checks.append({
            "level": "warning",
            "check": "止损过宽",
            "detail": f"{name} 成本{cost}→止损{stop}，跌幅{max_loss_pct:.1f}%超过10%",
        })
        risk_score += 2

    # 5. 仓位集中度检查
    # 估算总仓位价值（需要当前价，没有就用成本价）
    price = (current_prices or {}).get(code, position["cost"])
    position_value = position["shares"] * price
    total_value = sum(
        p["shares"] * (current_prices or {}).get(p["code"], p["cost"])
        for p in PORTFOLIO
    ) if current_prices else sum(p["shares"] * p["cost"] for p in PORTFOLIO)
    concentration = position_value / max(total_value, 1) * 100

    max_single = stage_rules.get("max_single_pct", 20)
    if concentration > max_single:
        checks.append({
            "level": "warning",
            "check": "仓位过重",
            "detail": f"{name} 占组合{concentration:.0f}%（超过{stage}阶段上限{max_single}%）",
        })
        risk_score += 2

    return {
        "code": code,
        "name": name,
        "sector": sector,
        "type": ptype,
        "risk_score": min(risk_score, 10),
        "risk_level": "high" if risk_score >= 7 else ("medium" if risk_score >= 4 else "low"),
        "checks": checks,
        "stage_compatible": ptype not in stage_rules.get("avoid_types", []),
        "relevant_alerts": len(relevant_alerts),
    }


def generate_brief(cycle: dict, alerts: list, results: list) -> str:
    """生成简洁组合简报。"""
    stage = cycle.get("stage", "未知")
    strategy = cycle.get("strategy_hint", "")
    next_risk = cycle.get("next_stage_risk", "")

    high_risk = [r for r in results if r["risk_level"] == "high"]
    medium_risk = [r for r in results if r["risk_level"] == "medium"]
    incompatible = [r for r in results if not r["stage_compatible"]]

    lines = [
        f"## 持仓守卫简报",
        f"**周期**: {stage} ({cycle.get('confidence', 0):.0%}) | **策略**: {strategy}",
        f"**下阶段风险**: {next_risk}",
        f"**活跃警报**: {len(alerts)} 个",
        "",
        "| 代码 | 名称 | 行业 | 风险 | 适配 | 关注点 |",
        "|------|------|------|------|------|--------|",
    ]

    for r in results:
        risk_emoji = "⬤" if r["risk_level"] == "high" else ("◐" if r["risk_level"] == "medium" else "○")
        compat = "Y" if r["stage_compatible"] else "N"
        concerns = "; ".join(c["check"] for c in r["checks"][:2]) or "-"
        lines.append(
            f"| {r['code']} | {r['name']} | {r['sector']} | {risk_emoji} | {compat} | {concerns} |"
        )

    lines.append("")

    if incompatible:
        names = [r["name"] for r in incompatible]
        lines.append(f"**周期不适配**: {', '.join(names)} — {stage}阶段应回避此类持仓")

    if high_risk:
        names = [r["name"] for r in high_risk]
        lines.append(f"**高风险**: {', '.join(names)} — 建议立即审查")

    if not incompatible and not high_risk:
        lines.append("**组合状态**: 无严重冲突，当前持仓与{stage}阶段基本适配")

    lines.append("")
    lines.append(f"**阶段操作建议**: {STAGE_PORTFOLIO_RULES.get(stage, {}).get('action', '等待信号')}")

    return "\n".join(lines)


def check_and_execute(cycle: dict) -> list[dict]:
    """检查所有持仓并执行止损（如果触发）。"""
    from stop_loss_executor import check_all_positions

    holdings = []
    for h in PORTFOLIO:
        holdings.append({
            "code": h["code"], "name": h["name"],
            "shares": h["shares"], "cost": h["cost"],
            "stop": h["stop"],
        })

    # 读取当前价格（优先从最新盘中分析）
    prices = {}
    reports = sorted(Path(__file__).parent.parent.glob("stock_data/analysis_30min_*.json"), reverse=True)
    if reports:
        try:
            data = json.loads(reports[0].read_text(encoding="utf-8"))
            for h in data.get("holdings", []):
                prices[h["code"]] = h.get("price", 0)
        except Exception:
            pass

    if not prices:
        for h in holdings:
            prices[h["code"]] = h["cost"]

    stage = cycle.get("stage", "主升")
    results = check_all_positions(holdings, prices, stage)

    executed = [r for r in results if r["status"] == "executed"]
    blocked = [r for r in results if r["status"] == "blocked"]
    if executed:
        print(f"  自动止损: {len(executed)} 单已执行")
        for r in executed:
            o = r.get("orders", [{}])[0]
            print(f"    {o.get('code','')} {o.get('quantity',0)}股@{o.get('price',0)}")
    if blocked:
        print(f"  止损拦截: {len(blocked)} 单被安全护栏拦截")
        for r in blocked:
            print(f"    {r['reason'][:60]}")
    return results


def main():
    cycle = judge_cycle_stage()
    alerts = get_alerts()

    print(f"持仓守卫 v1 ({datetime.now().strftime('%H:%M')})")
    print(f"周期: {cycle.get('stage')} (置信度: {cycle.get('confidence')})")
    print(f"策略: {cycle.get('strategy_hint')}")
    print(f"警报: {len(alerts)} 个")
    print()

    if "--code" in sys.argv:
        idx = sys.argv.index("--code")
        code = sys.argv[idx + 1]
        positions = [p for p in PORTFOLIO if p["code"] == code]
        if not positions:
            print(f"未找到代码: {code}")
            return
    else:
        positions = PORTFOLIO

    results = [check_position(p, cycle, alerts) for p in positions]

    if "--brief" in sys.argv:
        print(generate_brief(cycle, alerts, results))
        return

    for r in results:
        level_label = {"high": "高风险", "medium": "注意", "low": "正常"}
        print(f"[{r['code']}] {r['name']} ({r['sector']})")
        print(f"  风险: {level_label.get(r['risk_level'], '?')} (评分: {r['risk_score']}/10)")
        print(f"  周期适配: {'是' if r['stage_compatible'] else '否 — 当前阶段不适合此类持仓'}")
        print(f"  相关警报: {r['relevant_alerts']} 个")
        for c in r["checks"]:
            print(f"  [{c['level']}] {c['check']}: {c['detail']}")
        print()

    stage_rules = STAGE_PORTFOLIO_RULES.get(cycle.get("stage", "混沌"), {})
    print(f"=== 阶段建议 ===")
    print(f"最大持仓数: {stage_rules.get('max_positions', '?')} 只 (当前: {len(PORTFOLIO)} 只)")
    print(f"单票上限: {stage_rules.get('max_single_pct', '?')}%")
    print(f"策略: {stage_rules.get('strategy', '?')}")
    print(f"操作: {stage_rules.get('action', '?')}")


if __name__ == "__main__":
    main()
