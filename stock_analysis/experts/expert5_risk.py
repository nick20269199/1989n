"""Expert 5: 风控专家 — 规则驱动，不调 LLM

输入：当前持仓 + K线数据 + 规则库
输出：持仓风险评分 + 是否需要行动

规则来源：rule_miner_mine.py 从 3,605 笔历史交易挖掘
检查维度：
1. 持仓标的止损检查
2. 大盘下跌 + 持仓关联风险
3. 仓位集中度
4. 持仓天数超过历史最佳窗口
"""

import json, os, logging
from pathlib import Path

logger = logging.getLogger("experts.expert5_risk")

EXPERT_ID = "expert5_risk"
DATA_DIR = Path("D:/1989n/stock_data")
ML_DIR = DATA_DIR / "ml"
RULES_PATH = ML_DIR / "rules.json"

# ============================================================
# Config
# ============================================================
HARD_STOP_LOSS = -7.0       # 硬止损
SOFT_STOP_LOSS = -3.0       # 软止损
CONCENTRATION_LIMIT = 0.4   # 单标的上限
MAX_HOLD_DAYS = 7           # 超过此天数进入危险区


# ============================================================
# Load rules
# ============================================================
_rules_cache = None

def _load_rules():
    global _rules_cache
    if _rules_cache is None:
        if RULES_PATH.exists():
            with open(RULES_PATH) as f:
                _rules_cache = json.load(f)
        else:
            _rules_cache = {"rules": {"exit": {}}}
    return _rules_cache


# ============================================================
# Risk checks
# ============================================================

def check_stop_loss(position: dict, latest_price: float) -> dict:
    """Check if position is near or at stop loss."""
    cost = position.get("cost", 0)
    if cost <= 0 or latest_price <= 0:
        return {"level": "normal", "drawdown_pct": 0, "note": "无价格数据"}

    drawdown = (latest_price - cost) / cost * 100
    if drawdown <= HARD_STOP_LOSS:
        return {"level": "hard_stop", "drawdown_pct": round(drawdown, 1),
                "note": f"触发硬止损({HARD_STOP_LOSS}%), 差值{round(drawdown - HARD_STOP_LOSS, 1)}%"}
    elif drawdown <= SOFT_STOP_LOSS:
        return {"level": "soft_stop", "drawdown_pct": round(drawdown, 1),
                "note": f"触发软止损({SOFT_STOP_LOSS}%), 差{round(SOFT_STOP_LOSS - drawdown, 1)}%到硬止损"}
    elif drawdown < 0 and drawdown > SOFT_STOP_LOSS:
        return {"level": "warning", "drawdown_pct": round(drawdown, 1),
                "note": f"亏损中({round(drawdown,1)}%), 未触止损"}
    else:
        return {"level": "normal", "drawdown_pct": round(drawdown, 1),
                "note": f"盈利{round(drawdown,1)}%或持平"}


def check_hold_days(hold_days: int) -> dict:
    """Check if hold duration exceeds optimal window based on rules."""
    rules = _load_rules()
    exit_rules = rules.get("rules", {}).get("exit", {}).get("hold_duration", [])

    # Find the win rate for this hold duration
    matched_wr = None
    for r in exit_rules:
        if "hold_days" in r.get("condition", ""):
            matched_wr = r.get("win_rate", 50)

    if hold_days > MAX_HOLD_DAYS:
        return {"level": "danger", "hold_days": hold_days,
                "note": f"持仓{hold_days}天，超过最佳窗口{MAX_HOLD_DAYS}天"}
    elif hold_days >= 5:
        return {"level": "warning", "hold_days": hold_days,
                "note": f"持仓{hold_days}天，接近危险区"}

    return {"level": "normal", "hold_days": hold_days, "note": "持仓天数合理"}


def check_concentration(holdings: list, current_code: str) -> dict:
    """Check if a single position is too concentrated."""
    total_value = sum(
        h.get("shares", 0) * h.get("cost", 0) for h in holdings
    )
    if total_value <= 0:
        return {"level": "normal", "concentration_pct": 0, "note": "无持仓数据"}

    for h in holdings:
        if h.get("code") == current_code:
            pos_value = h.get("shares", 0) * h.get("cost", 0)
            conc_pct = pos_value / total_value
            if conc_pct > CONCENTRATION_LIMIT:
                return {"level": "warning", "concentration_pct": round(conc_pct * 100, 1),
                        "note": f"单标占比{conc_pct*100:.0f}%，超过{CONCENTRATION_LIMIT*100}%上限"}
            return {"level": "normal", "concentration_pct": round(conc_pct * 100, 1),
                    "note": f"占比{conc_pct*100:.0f}%，合理"}
    return {"level": "normal", "concentration_pct": 0, "note": "未找到标的"}


def check_market_downdraft(market_summary: dict) -> dict:
    """Check if market is in a dangerous state."""
    if not isinstance(market_summary, dict):
        return {"level": "unknown", "note": "无市场数据"}

    sentiment = market_summary.get("sentiment", "")
    trend = market_summary.get("trend", "")
    pct_chg = market_summary.get("pct_chg", 0)

    warnings = []
    if sentiment in ("恐慌", "弱势"):
        warnings.append(f"市场情绪{sentiment}")
    if trend in ("空头排列", "短期偏空"):
        warnings.append(f"趋势{trend}")
    if isinstance(pct_chg, (int, float)) and pct_chg < -2:
        warnings.append(f"当日跌幅{pct_chg}%")

    if len(warnings) >= 2:
        return {"level": "danger", "warnings": warnings,
                "note": "; ".join(warnings) + " — 建议减仓"}
    elif len(warnings) == 1:
        return {"level": "warning", "warnings": warnings,
                "note": warnings[0] + " — 注意风险"}
    return {"level": "normal", "warnings": [], "note": "市场环境正常"}


def check_loss_streak(decision_log: list) -> dict:
    """Check for consecutive losing trades."""
    if not decision_log:
        return {"level": "normal", "streak": 0, "note": "无历史交易记录"}

    streak = 0
    for entry in reversed(decision_log):
        pnl = entry.get("net_profit", 0) if isinstance(entry, dict) else 0
        if pnl < 0:
            streak += 1
        else:
            break

    if streak >= 3:
        return {"level": "danger", "streak": streak,
                "note": f"连续{streak}笔亏损 — 建议暂停交易"}
    elif streak >= 2:
        return {"level": "warning", "streak": streak,
                "note": f"连续{streak}笔亏损 — 注意"}
    return {"level": "normal", "streak": streak, "note": "无连续亏损"}


# ============================================================
# Main entry
# ============================================================

def analyze(symbol: str, name: str, data_context: dict,
            market_state: str = "unknown", mode: str = "full") -> dict:
    """Risk analysis — check all risk dimensions for a position."""

    # Get latest price from kline data
    kline = data_context.get("kline", {})
    latest_price = kline.get("latest_price", 0)

    # Get holdings from data_context or portfolio
    holdings = data_context.get("holdings", [])

    # Current position
    current_pos = None
    for h in holdings:
        if h.get("code") == symbol:
            current_pos = h
            break
    if current_pos is None:
        current_pos = {"code": symbol, "name": name, "cost": 0, "shares": 0}

    # Calculate approximate hold days
    from datetime import datetime
    hold_days = 0
    first_buy = current_pos.get("first_buy", "")
    if first_buy:
        try:
            bd = datetime.strptime(first_buy[:10], "%Y-%m-%d")
            hold_days = (datetime.now() - bd).days
        except ValueError:
            pass

    # Run all checks
    stop_loss_check = check_stop_loss(current_pos, latest_price)
    hold_check = check_hold_days(hold_days)
    conc_check = check_concentration(holdings, symbol)
    market_check = check_market_downdraft(data_context.get("market_summary", {}))

    # Composite risk score: 0 (safe) to 1 (danger)
    risk_scores = {
        "hard_stop": 1.0, "soft_stop": 0.8, "warning": 0.5, "normal": 0.1, "danger": 0.9, "unknown": 0.3
    }
    r1 = risk_scores.get(stop_loss_check.get("level", "normal"), 0.2)
    r2 = risk_scores.get(hold_check.get("level", "normal"), 0.2)
    r3 = risk_scores.get(conc_check.get("level", "normal"), 0.2)
    r4 = risk_scores.get(market_check.get("level", "normal"), 0.2)

    composite_risk = round((r1 * 0.4 + r2 * 0.2 + r3 * 0.2 + r4 * 0.2), 2)

    if composite_risk >= 0.6:
        overall = "高风险 — 建议减仓或止损"
        action = "减仓"
    elif composite_risk >= 0.3:
        overall = "中等风险 — 持仓观察"
        action = "持仓"
    else:
        overall = "低风险 — 正常持仓"
        action = "持仓"

    return {
        "expert_id": EXPERT_ID,
        "status": "done",
        "symbol": symbol,
        "name": name,
        "risk_assessment": {
            "composite_risk": composite_risk,
            "overall": overall,
            "action": action,
            "checks": {
                "stop_loss": stop_loss_check,
                "hold_duration": hold_check,
                "concentration": conc_check,
                "market_environment": market_check,
            },
        },
    }


if __name__ == "__main__":
    # Quick test
    test_pos = {"kline": {"latest_price": 42.0}, "holdings": [{"code": "002156", "cost": 44.85, "shares": 1000, "first_buy": "2026-04-27"}]}
    r = analyze("002156", "通富微电", test_pos)
    print(json.dumps(r, ensure_ascii=False, indent=2))
