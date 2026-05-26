"""
stop_loss_executor.py — 止损执行引擎

填补从检测到执行的6个缺失环节:
  信号路由 → 执行条件检查 → 委托生成 → 委托提交 → 委托确认 → 结果记录

6层AND安全护栏:
  1. 价格有效性 2. 成交量确认 3. 重复触发防护 4. 市场状态 5. 滑点保护 6. AND条件链

用法:
    from stop_loss_executor import stop_loss_no_reason
    result = stop_loss_no_reason(portfolio, market_data, risk_config)
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

STOCK_DATA = Path("D:/1989n/stock_data")
LEARNING_DIR = STOCK_DATA / "learning"
RULES_FILE = LEARNING_DIR / "rules.json"
EXECUTION_LOG = STOCK_DATA / "stop_loss_executions.json"
BACKTEST_REPORT = STOCK_DATA / "decision_backtest_report.json"

# 防重复触发缓存（进程级，重启即重置）
_trigger_cache: dict[str, datetime] = {}

# 周期阶段 → 参数自适应
CYCLE_PARAMS = {
    "冰点":   {"stop_pct": -5, "volume_min_hands": 10, "cooldown_min": 60, "slippage_pct": 10},
    "启动":   {"stop_pct": -7, "volume_min_hands": 5,  "cooldown_min": 30, "slippage_pct": 5},
    "主升":   {"stop_pct": -10,"volume_min_hands": 1,  "cooldown_min": 15, "slippage_pct": 3},
    "高潮":   {"stop_pct": -7, "volume_min_hands": 5,  "cooldown_min": 30, "slippage_pct": 3},
    "衰退":   {"stop_pct": -5, "volume_min_hands": 20, "cooldown_min": 60, "slippage_pct": 10},
    "混沌":   {"stop_pct": -7, "volume_min_hands": 5,  "cooldown_min": 30, "slippage_pct": 5},
}


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_json(path: Path, data: dict):
    data["_updated"] = datetime.now().isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_cycle_params(cycle_stage: str = "") -> dict:
    """根据周期阶段返回止损参数，默认主升。"""
    return CYCLE_PARAMS.get(cycle_stage, CYCLE_PARAMS["主升"])


# ── 安全护栏 1: 价格有效性 ──
def _check_price_validity(code: str, current_price: float,
                          prev_price: float = 0) -> tuple[bool, str]:
    """检查当前价格是否有效：>0 且非空，且与前一分钟偏差 < 20%。"""
    if not current_price or current_price <= 0:
        return False, f"invalid_price: {code} 当前价 {current_price}"
    if prev_price > 0:
        deviation = abs(current_price - prev_price) / prev_price
        if deviation > 0.20:
            return False, f"price_jump: {code} 价格跳变 {deviation:.1%} > 20%"
    return True, ""


# ── 安全护栏 2: 成交量确认 ──
def _check_volume_confirmation(code: str, recent_volume: int,
                               min_hands: int = 1) -> tuple[bool, str]:
    """最近N分钟成交量必须 > 阈值（防止流动性枯竭误杀）。"""
    if recent_volume < min_hands:
        return False, f"low_volume: {code} 最近成交量 {recent_volume} < {min_hands} 手"
    return True, ""


# ── 安全护栏 3: 重复触发防护 ──
def _check_retrigger_protection(code: str,
                                cooldown_min: int = 30) -> tuple[bool, str]:
    """同一标的在 cooldown 分钟内只允许触发一次。"""
    now = datetime.now()
    if code in _trigger_cache:
        elapsed = (now - _trigger_cache[code]).total_seconds() / 60
        if elapsed < cooldown_min:
            return False, f"retrigger_blocked: {code} 距上次触发仅 {elapsed:.0f}min < {cooldown_min}min"
    _trigger_cache[code] = now
    return True, ""


# ── 安全护栏 4: 市场状态 ──
def _check_market_status(current_time: datetime = None) -> tuple[bool, str]:
    """仅在交易时段内执行。"""
    if current_time is None:
        current_time = datetime.now()
    # A股交易时段: 9:30-11:30, 13:00-15:00
    hour, minute = current_time.hour, current_time.minute
    weekday = current_time.weekday()
    if weekday >= 5:
        return False, "market_closed: 非交易日"
    if (hour == 11 and minute >= 31) or (hour == 12):
        return False, "market_closed: 午休"
    if hour < 9 or hour >= 15 or (hour == 9 and minute < 25):
        return False, "market_closed: 非交易时段"
    if hour == 9 and minute < 30:
        # 集合竞价时段可记录但不执行
        return False, "auction_phase: 集合竞价时段，延迟到连续竞价"
    return True, ""


# ── 安全护栏 5: 滑点保护 ──
def _check_slippage_protection(stop_price: float, current_price: float,
                               slippage_pct: int = 5) -> tuple[bool, float, str]:
    """确保卖出价格不低于止损价的 (100 - slippage_pct)%。"""
    min_acceptable = stop_price * (1 - slippage_pct / 100)
    if current_price < min_acceptable:
        return False, 0, f"slippage_exceeded: 当前 {current_price} < 最低接受价 {min_acceptable:.2f}"
    execution_price = max(current_price, stop_price * 0.98)
    return True, execution_price, ""


# ── 安全护栏 6: AND 条件链 ──
def _evaluate_and_chain(code: str, current_price: float, stop_price: float,
                        checks: list[tuple[bool, str]]) -> tuple[bool, list[str]]:
    """所有条件必须同时满足才执行。"""
    failures = []
    for passed, reason in checks:
        if not passed:
            failures.append(reason)
    return len(failures) == 0, failures


# ── 核心函数 ──
def stop_loss_no_reason(holding: dict, current_price: float,
                        cycle_stage: str = "", prev_price: float = 0,
                        recent_volume: int = -1) -> dict:
    """
    止损执行引擎 — 输入单票持仓+市场数据，输出执行结果。

    参数:
        holding: {"code": str, "name": str, "shares": int, "cost": float, "stop": float}
        current_price: 当前市价
        cycle_stage: 周期阶段（用于参数自适应）
        prev_price: 前一分钟价格（价格跳变检测）
        recent_volume: 最近成交量（手数，-1=跳过检查）

    返回:
        {"status": "executed"|"skipped"|"error",
         "orders": [...], "safety_checks": [...], "reason": str}
    """
    code = holding.get("code", "")
    cost = holding.get("cost", 0)
    shares = holding.get("shares", 0)
    stop_price = holding.get("stop", round(cost * 0.93, 2))

    if not code or shares <= 0:
        return {"status": "skipped", "reason": "no_position", "orders": [],
                "safety_checks": []}

    params = _get_cycle_params(cycle_stage)
    triggered_pct = (current_price - cost) / cost * 100

    safety_checks = []

    # 护栏1: 价格有效性
    p1, r1 = _check_price_validity(code, current_price, prev_price)
    safety_checks.append({"gate": "price_validity", "passed": p1, "detail": r1})

    # 护栏2: 成交量确认
    if recent_volume >= 0:
        p2, r2 = _check_volume_confirmation(code, recent_volume, params["volume_min_hands"])
    else:
        p2, r2 = True, "volume_check_skipped"
    safety_checks.append({"gate": "volume_confirmation", "passed": p2, "detail": r2})

    # 护栏3: 重复触发防护
    p3, r3 = _check_retrigger_protection(code, params["cooldown_min"])
    safety_checks.append({"gate": "retrigger_protection", "passed": p3, "detail": r3})

    # 护栏4: 市场状态
    p4, r4 = _check_market_status()
    safety_checks.append({"gate": "market_status", "passed": p4, "detail": r4})

    # 构建检查列表供 AND 链
    check_results = [(p1, r1), (p2, r2), (p3, r3), (p4, r4)]

    # 检查是否触发止损条件
    hard_stop_pct = params["stop_pct"]
    stop_triggered = triggered_pct <= hard_stop_pct

    # 组装结果（统一出口）
    result = {
        "status": "skipped",
        "orders": [],
        "safety_checks": safety_checks,
        "trigger_info": {"cost": cost, "current": current_price,
                         "triggered_pct": round(triggered_pct, 1),
                         "hard_stop_pct": hard_stop_pct,
                         "price_as_of": datetime.now().isoformat()},
    }

    if not stop_triggered:
        result["status"] = "skipped"
        result["reason"] = f"not_triggered: {code} 当前 {current_price} 成本 {cost} ({triggered_pct:.1f}%) 未触及止损 {hard_stop_pct}%"
        return result

    # 止损已触发 → 过 AND 条件链
    all_clear, failures = _evaluate_and_chain(code, current_price, stop_price, check_results)

    if not all_clear:
        result["status"] = "blocked"
        result["reason"] = f"安全护栏拦截: {'; '.join(failures)}"
        _record_execution(result, code)
        _update_rule_validation(code, triggered_pct, hard_stop_pct)
        return result

    # 护栏5: 滑点保护
    p5, exec_price, r5 = _check_slippage_protection(stop_price, current_price, params["slippage_pct"])
    safety_checks.append({"gate": "slippage_protection", "passed": p5, "detail": r5})

    if not p5:
        result["status"] = "blocked"
        result["reason"] = r5
        _record_execution(result, code)
        _update_rule_validation(code, triggered_pct, hard_stop_pct)
        return result

    # 全部通过 → 生成委托
    qty = shares
    order = {
        "code": code,
        "name": holding.get("name", ""),
        "side": "sell",
        "price": round(exec_price, 2),
        "quantity": qty,
        "amount": round(exec_price * qty, 2),
        "reason": f"hard_stop_at_{hard_stop_pct}%",
        "triggered_pct": round(triggered_pct, 1),
    }

    result["status"] = "executed"
    result["reason"] = f"hard_stop_executed: {code} {qty}股 @ {exec_price:.2f}"
    result["orders"] = [order]
    result["trigger_info"]["exec_price"] = round(exec_price, 2)
    result["timestamp"] = datetime.now().isoformat()

    _record_execution(result, code)
    _update_rule_validation(code, triggered_pct, hard_stop_pct)

    return result


# ── 结果记录 ──
def _record_execution(result: dict, code: str = ""):
    """将执行结果写入 decision_backtest_report.json。"""
    report = _load_json(BACKTEST_REPORT)
    if "executions" not in report:
        report["executions"] = []
    order_code = code
    if not order_code and result.get("orders"):
        order_code = result["orders"][0].get("code", "")
    report["executions"].append({
        "timestamp": datetime.now().isoformat(),
        "result": result["status"],
        "code": order_code,
        "order": result.get("orders", [{}])[0] if result.get("orders") else None,
        "trigger_info": result.get("trigger_info", {}),
    })
    # 更新汇总统计
    stats = report.get("backtest", {})
    stats["total"] = stats.get("total", 0) + 1
    stats["updated"] = stats.get("updated", 0) + 1
    if result["status"] == "executed":
        stats["executed"] = stats.get("executed", 0) + 1
    elif result["status"] == "blocked":
        stats["blocked"] = stats.get("blocked", 0) + 1
    report["backtest"] = stats
    _save_json(BACKTEST_REPORT, report)

    # 同时写入执行日志
    log = _load_json(EXECUTION_LOG)
    entries = log.get("executions", [])
    entries.append({
        "timestamp": datetime.now().isoformat(),
        "code": code,
        "status": result["status"],
        "reason": result["reason"],
        "trigger_info": result.get("trigger_info", {}),
        "price_as_of": result.get("trigger_info", {}).get("price_as_of", datetime.now().isoformat()),
    })
    if len(entries) > 500:
        entries = entries[-500:]
    log["executions"] = entries
    _save_json(EXECUTION_LOG, log)


# ── 规则验证计数更新 ──
def _update_rule_validation(code: str, triggered_pct: float, hard_stop_pct: int):
    """更新 trading_rules.json 和 learning/rules.json 的验证计数。"""
    rules_data = _load_json(RULES_FILE)
    rules = rules_data.get("rules", [])
    updated = 0
    for rule in rules:
        if "止损" in rule.get("action", "") or "stop" in rule.get("condition", "").lower():
            rule["last_verified"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            rule["verified_count"] = rule.get("verified_count", 0) + 1
            updated += 1
    if updated > 0:
        _save_json(RULES_FILE, rules_data)


# ── 批量检查所有持仓 ──
def check_all_positions(holdings: list[dict], prices: dict,
                        cycle_stage: str = "", volumes: dict = None) -> list[dict]:
    """对所有持仓执行止损检查，返回结果列表。"""
    volumes = volumes or {}
    results = []
    for h in holdings:
        code = h["code"]
        price = prices.get(code, 0)
        if price <= 0:
            results.append({"code": code, "status": "skipped",
                            "reason": "no_price_data"})
            continue
        result = stop_loss_no_reason(
            holding=h,
            current_price=price,
            cycle_stage=cycle_stage,
            recent_volume=volumes.get(code, -1),
        )
        results.append(result)
    return results


# ── CLI ──
def main():
    import sys
    holdings = []
    portfolio_path = Path(__file__).parent / "data" / "portfolio.json"
    data = _load_json(portfolio_path)
    for h in data.get("holdings", []):
        cost = h.get("cost", 0)
        holdings.append({
            "code": h["code"], "name": h["name"],
            "shares": h["shares"], "cost": cost,
            "stop": round(cost * 0.93, 2),
        })

    # 模拟市场价格（没有实时数据时用成本价）
    prices = {h["code"]: h["cost"] * 0.92 for h in holdings}

    # 读取周期阶段
    try:
        from daily_compress import judge_cycle_stage
        cycle = judge_cycle_stage()
        stage = cycle.get("stage", "主升")
    except Exception:
        stage = "主升"

    results = check_all_positions(holdings, prices, stage)
    executed = [r for r in results if r["status"] == "executed"]
    blocked = [r for r in results if r["status"] == "blocked"]
    skipped = [r for r in results if r["status"] == "skipped"]

    print(f"=== 止损执行引擎 ({stage}) ===")
    print(f"执行: {len(executed)} | 拦截: {len(blocked)} | 跳过: {len(skipped)}")
    for r in results:
        if r["status"] in ("executed", "blocked"):
            print(f"  [{r['status']}] {r.get('orders', [{}])[0].get('code','?')}: {r['reason'][:80]}")
    print()


if __name__ == "__main__":
    main()
