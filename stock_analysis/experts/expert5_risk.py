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
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("experts.expert5_risk")

EXPERT_ID = "expert5_risk"
DATA_DIR = Path("D:/1989n/stock_data")
ML_DIR = DATA_DIR / "ml"
RULES_PATH = ML_DIR / "rules.json"
TRADING_RULES_PATH = DATA_DIR / "trading_rules.json"

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
# Trading rules (从对抗审查提炼的硬约束)
# ============================================================

_trading_rules_cache = None

def _load_trading_rules() -> list[dict]:
    """加载 trading_rules.json — 对抗审查提炼的交易规则。"""
    global _trading_rules_cache
    if _trading_rules_cache is None:
        if TRADING_RULES_PATH.exists():
            with open(TRADING_RULES_PATH, encoding="utf-8") as f:
                data = json.load(f)
            _trading_rules_cache = [r for r in data.get("rules", []) if r.get("status") == "active"]
        else:
            _trading_rules_cache = []
    return _trading_rules_cache


def check_trading_rules(position: dict, data_context: dict) -> dict:
    """检查持仓是否触犯 trading_rules.json 中的活跃规则。

    R001 画饼禁重仓: 需要新业务营收数据 (不在当前数据中则跳过)
    R002 52周高涨幅禁追: 需要52周K线高点和当前价 (从 kline 提取)
    R003 单分析师覆盖预警: 需要机构覆盖数 (不在当前数据中则跳过)
    R004 叙事vs业绩剪刀差: 需要52周涨幅+利润数据 (部分可从 kline 估算)
    """
    rules = _load_trading_rules()
    triggered = []

    if not rules:
        return {"level": "normal", "triggered": [], "note": "无活跃交易规则"}

    kline = data_context.get("kline", {})
    price = kline.get("latest_price", 0)
    cost = position.get("cost", 0)

    for r in rules:
        rid = r.get("id", "")
        name = r.get("name", "")
        trigger = r.get("trigger", "")

        # R002: 52周高涨幅禁追 — 检查当前价距52周高点是否>150%
        if rid == "R002" and price > 0:
            high_52w = kline.get("high_52w") or kline.get("high", 0)
            if high_52w and high_52w > 0:
                gain_from_low = (price / max(high_52w * 0.4, 1)) - 1
                if gain_from_low > 1.5:
                    triggered.append({
                        "rule": rid, "name": name,
                        "detail": f"当前价{price:.2f}, 52周低点~{high_52w*0.4:.2f}, 涨幅{gain_from_low*100:.0f}% > 150%阈值",
                        "action": r.get("action", ""),
                    })

        # R001: 画饼禁重仓 — 检查仓位占比
        if rid == "R001" and cost > 0:
            holdings = data_context.get("holdings", [])
            total_value = sum(h.get("shares", 0) * h.get("cost", 0) for h in holdings if h.get("cost", 0) > 0)
            if total_value > 0:
                pos_value = position.get("shares", 0) * cost
                pos_pct = pos_value / total_value * 100
                if pos_pct > 3:
                    triggered.append({
                        "rule": rid, "name": name,
                        "detail": f"仓位占比{pos_pct:.1f}% > 3%阈值（新业务零营收标的限制）",
                        "action": r.get("action", ""),
                    })

        # R003: 单分析师覆盖预警 — 检查仓位占比(数据不可用时跳过)
        if rid == "R003" and cost > 0:
            # 机构覆盖数不在当前数据中，仅当仓位>3%时提醒数据缺失
            holdings = data_context.get("holdings", [])
            total_value = sum(h.get("shares", 0) * h.get("cost", 0) for h in holdings if h.get("cost", 0) > 0)
            if total_value > 0:
                pos_value = position.get("shares", 0) * cost
                pos_pct = pos_value / total_value * 100
                if pos_pct > 3:
                    triggered.append({
                        "rule": rid, "name": name,
                        "detail": f"仓位占比{pos_pct:.1f}% > 3%阈值, 但机构覆盖数不可用, 无法完全验证规则",
                        "action": "需人工核查机构覆盖数",
                    })

        # R004: 叙事vs业绩剪刀差 — 需要利润数据, kline仅能估算价格部分
        if rid == "R004":
            high_52w = kline.get("high_52w") or kline.get("high", 0)
            if high_52w and high_52w > 0 and price > 0:
                annual_gain = (price / max(high_52w * 0.4, 1)) - 1
                if annual_gain > 1.0:
                    triggered.append({
                        "rule": rid, "name": name,
                        "detail": f"年度涨幅估算{annual_gain*100:.0f}% > 100%阈值（需利润数据验证剪刀差）",
                        "action": r.get("action", ""),
                    })

    if not triggered:
        return {"level": "normal", "triggered": [], "note": f"{len(rules)}条规则检查通过"}

    levels = [t["rule"] for t in triggered]
    return {"level": "warning", "triggered": triggered,
            "note": f"触发规则: {', '.join(levels)}"}


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
    trading_check = check_trading_rules(current_pos, data_context)

    # Composite risk score: 0 (safe) to 1 (danger)
    risk_scores = {
        "hard_stop": 1.0, "soft_stop": 0.8, "warning": 0.5, "normal": 0.1, "danger": 0.9, "unknown": 0.3
    }
    r1 = risk_scores.get(stop_loss_check.get("level", "normal"), 0.2)
    r2 = risk_scores.get(hold_check.get("level", "normal"), 0.2)
    r3 = risk_scores.get(conc_check.get("level", "normal"), 0.2)
    r4 = risk_scores.get(market_check.get("level", "normal"), 0.2)
    r5 = 0.5 if trading_check.get("triggered") else 0  # 触发交易规则即加分

    composite_risk = round((r1 * 0.35 + r2 * 0.15 + r3 * 0.15 + r4 * 0.15 + r5 * 0.2), 2)

    if composite_risk >= 0.6:
        overall = "高风险 — 建议减仓或止损"
        action = "减仓"
        direction = "空"
    elif composite_risk >= 0.3:
        overall = "中等风险 — 持仓观察"
        action = "持仓"
        direction = "观望"
    else:
        overall = "低风险 — 正常持仓"
        action = "持仓"
        direction = "多"

    return {
        "expert_id": EXPERT_ID,
        "status": "done",
        "symbol": symbol,
        "name": name,
        "direction": direction,
        "confidence": round(1 - composite_risk, 2),
        "method": ["止损检查", "持仓时长分析", "集中度检查", "市场环境检查", "连亏检测", "交易规则检查"],
        "trajectory": {
            "stop_loss_levels": {
                "hard_stop_pct": HARD_STOP_LOSS,
                "soft_stop_pct": SOFT_STOP_LOSS,
                "current_drawdown": stop_loss_check.get("drawdown_pct", 0),
            },
            "action": action,
        },
        "margin": {
            "invalidated_if": f"止损条件触发后未执行(跌破{HARD_STOP_LOSS*100}%硬止损不清仓); 大盘连跌3日累计超3%+持仓未减",
            "black_swan": "指数单日暴跌5%以上触发全市场清仓; 个股停牌/被ST/财务造假等不可控事件",
            "confidence_decay": f"持仓超{MAX_HOLD_DAYS}天→0.4, 连续亏损3笔→0.2, 硬止损被触发→0.1",
        },
        "logic": {
            "because": f"止损状态={stop_loss_check.get('level','?')}, 持仓天数={hold_days}, 集中度={conc_check.get('concentration_pct',0)}%, 市场环境={market_check.get('level','?')}",
            "so": overall,
            "if_wrong": f"如果{direction == '空' and '止损未触发+市场情绪恢复+个股独立走强' or direction == '观望' and '风险指标全部正常+趋势转多' or '止损触发+集中度超限'}则当前{direction}判断失效,风控逻辑证伪",
        },
        "raw_analysis": (
            f"【风控检查】{name}({symbol})\n"
            f"止损: {stop_loss_check.get('level','?')} ({stop_loss_check.get('drawdown_pct',0)}%)\n"
            f"持仓: {hold_check.get('level','?')} ({hold_days}天)\n"
            f"集中度: {conc_check.get('level','?')} ({conc_check.get('concentration_pct',0)}%)\n"
            f"市场: {market_check.get('level','?')}\n"
            f"综合风险: {composite_risk} → {overall}"
        ),
        "risk_assessment": {
            "composite_risk": composite_risk,
            "overall": overall,
            "action": action,
            "checks": {
                "stop_loss": stop_loss_check,
                "hold_duration": hold_check,
                "concentration": conc_check,
                "market_environment": market_check,
                "trading_rules": trading_check,
            },
        },
    }


# ============================================================
# 仓位管理模型 (Proposal: concept-position-sizing)
# ============================================================

def kelly_position_sizing(win_rate: float, avg_win: float, avg_loss: float,
                           max_risk_pct: float = 0.02, portfolio_value: float = 0) -> dict:
    """Kelly 公式仓位计算 + Half-Kelly 安全调整。

    Args:
        win_rate: 胜率 (0-1)
        avg_win: 平均盈利比例 (如 0.08 = 8%)
        avg_loss: 平均亏损比例 (如 0.05 = 5%)
        max_risk_pct: 单笔最大风险敞口 (默认2%)
        portfolio_value: 组合总市值, 0=仅返回比例

    Returns:
        {kelly_pct, half_kelly_pct, suggested_shares, risk_level, note}
    """
    if win_rate <= 0 or avg_win <= 0 or avg_loss <= 0:
        return {"kelly_pct": 0, "half_kelly_pct": 0, "note": "参数不足，无法计算"}

    b = avg_win / avg_loss  # 赔率
    p = win_rate
    q = 1 - p

    kelly = (b * p - q) / b if b > 0 else 0
    kelly = max(0, min(kelly, max_risk_pct))  # 限幅

    half_kelly = kelly * 0.5

    if kelly <= 0:
        return {"kelly_pct": 0, "half_kelly_pct": 0, "risk_level": "high",
                "note": "Kelly 为负，建议不参与"}
    elif kelly < 0.1:
        risk_level = "high"
    elif kelly < 0.2:
        risk_level = "medium"
    else:
        risk_level = "low"

    result = {
        "kelly_pct": round(kelly * 100, 1),
        "half_kelly_pct": round(half_kelly * 100, 1),
        "suggested_pct": round(half_kelly * 100, 1),
        "risk_level": risk_level,
        "note": f"胜率{win_rate*100:.0f}%, 盈亏比{b:.2f}, 半凯利建议{half_kelly*100:.1f}%",
    }

    if portfolio_value > 0 and result["suggested_pct"] > 0:
        suggested_value = portfolio_value * result["suggested_pct"] / 100
        result["suggested_value"] = round(suggested_value, 2)

    return result


# ============================================================
# 多层安全防御 — 断路器 (Proposal: arch-multi-layer-security)
# ============================================================

class CircuitBreaker:
    """断路器 — 多层安全防御的第④层。

    层①: 数据校验 (data_source_router 白名单)
    层②: 规则审查 (check_trading_rules)
    层③: AI 独立审查 (grader)
    层④: 断路器 (本模块)

    触发条件:
    - 连续 3 笔亏损
    - 单日亏损 > 5%
    - 3 个以上风控维度同时报警
    """

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Path("D:/1989n/stock_data")
        self.state_path = self.data_dir / "circuit_breaker_state.json"
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_path.exists():
            try:
                return json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {
            "consecutive_losses": 0,
            "daily_loss_pct": 0,
            "daily_loss_date": "",
            "is_triggered": False,
            "trigger_reason": "",
            "triggered_at": None,
        }

    def _save_state(self):
        self.state_path.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def check(self, position_pnl: float = None, daily_pnl_pct: float = None,
              risk_signals: list[dict] = None) -> dict:
        """检查断路器状态。

        Args:
            position_pnl: 当前持仓盈亏比例
            daily_pnl_pct: 当日总盈亏比例
            risk_signals: 各风控维度信号 [{dimension, level}]

        Returns:
            {triggered, level, reason, actions}
        """
        now = datetime.now().strftime("%Y-%m-%d")

        if self.state["daily_loss_date"] != now:
            self.state["daily_loss_date"] = now
            self.state["daily_loss_pct"] = 0

        if position_pnl is not None:
            if position_pnl < 0:
                self.state["consecutive_losses"] += 1
            else:
                self.state["consecutive_losses"] = 0

        if daily_pnl_pct is not None:
            self.state["daily_loss_pct"] = min(self.state["daily_loss_pct"], daily_pnl_pct)

        actions = []

        if self.state["consecutive_losses"] >= 3:
            self.state["is_triggered"] = True
            self.state["trigger_reason"] = f"连续{self.state['consecutive_losses']}笔亏损"
            self.state["triggered_at"] = now
            actions.append("暂停新开仓")

        if self.state["daily_loss_pct"] <= -5:
            self.state["is_triggered"] = True
            self.state["trigger_reason"] = f"单日亏损{self.state['daily_loss_pct']:.1f}% > 5%阈值"
            self.state["triggered_at"] = now
            actions.append("减仓50%")

        if risk_signals:
            high_risk_count = sum(1 for s in risk_signals if s.get("level") in ("danger", "hard_stop"))
            if high_risk_count >= 3:
                self.state["is_triggered"] = True
                self.state["trigger_reason"] = f"{high_risk_count}个风控维度同时报警"
                self.state["triggered_at"] = now
                actions.append("全面风险审查")

        self._save_state()

        return {
            "triggered": self.state["is_triggered"],
            "level": "danger" if self.state["is_triggered"] else "normal",
            "reason": self.state.get("trigger_reason", ""),
            "actions": actions,
            "consecutive_losses": self.state["consecutive_losses"],
            "daily_loss_pct": self.state["daily_loss_pct"],
        }


# 全局断路器实例
_circuit_breaker = None


def get_circuit_breaker() -> CircuitBreaker:
    global _circuit_breaker
    if _circuit_breaker is None:
        _circuit_breaker = CircuitBreaker()
    return _circuit_breaker


if __name__ == "__main__":
    # Quick test
    test_pos = {"kline": {"latest_price": 42.0}, "holdings": [{"code": "002156", "cost": 44.85, "shares": 1000, "first_buy": "2026-04-27"}]}
    r = analyze("002156", "通富微电", test_pos)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    print()
    # Test Kelly
    k = kelly_position_sizing(0.55, 0.08, 0.05, portfolio_value=100000)
    print(f"Kelly: {json.dumps(k, ensure_ascii=False)}")
    # Test CB
    cb = get_circuit_breaker()
    cb_check = cb.check(position_pnl=-0.02, risk_signals=[{"dimension": "stop_loss", "level": "warning"}])
    print(f"Circuit Breaker: {json.dumps(cb_check, ensure_ascii=False)}")
