"""
evolve_capture.py — 交易自进化引擎 · 捕获层
==========================================
4 个触发节点的事件检测 + 记录写入队列。
设计为轻量级：无网络调用，无重量导入，可嵌入任何现有脚本。

4 个触发节点:
  1. 止损失败 — last_error.txt 含止损相关错误 + 该票仍在持仓中
  2. 决策证伪 — 晨报/盘前方向判断 vs 当日收盘方向 背离 > 阈值
  3. 竞价异常 — 竞价量信号 + 当日实际走势背离
  4. 新票首亏 — 首次买入某票后第一次触发止损/出清

队列文件: stock_data/evolution_queue.json
  累积 5-15 条后触发蒸馏 (distill) 流程。
"""
import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

STOCK_DATA = Path("D:/1989n/stock_data")
QUEUE_PATH = STOCK_DATA / "evolution_queue.json"
ERROR_PATH = STOCK_DATA / "last_error.txt"
PORTFOLIO_PATH = Path("D:/1989n/stock_analysis/data/portfolio.json")

# ── 阈值 ──
DECISION_THRESHOLD = 3.0      # 决策证伪: 方向偏差 > 3%
AUCTION_DIVERGE_RATIO = 1.5   # 竞价背离: 量比 > 1.5x


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text("utf-8"))


def _save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def _load_queue() -> list[dict]:
    data = _load_json(QUEUE_PATH)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items", data.get("queue", []))
    return []


def _append_to_queue(record: dict):
    """写入捕获记录到蒸馏队列。"""
    queue = _load_queue()
    record["captured_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # 去重: 同 trigger + 同 stock + 同日期 不重复写入
    today = date.today().strftime("%Y-%m-%d")
    for existing in queue:
        if (existing.get("trigger") == record["trigger"] and
            existing.get("context", {}).get("stock") == record.get("context", {}).get("stock") and
            existing.get("captured_at", "").startswith(today)):
            return  # 今日已有同类记录
    queue.append(record)
    _save_json(QUEUE_PATH, {"items": queue, "updated": datetime.now().isoformat()})


def _current_portfolio() -> dict[str, dict]:
    """返回 {code: {name, shares, cost, ...}} 的当前持仓映射。"""
    pf = _load_json(PORTFOLIO_PATH)
    if isinstance(pf, dict):
        pf = pf.get("holdings", pf.get("data", []))
    if not isinstance(pf, list):
        return {}
    return {
        p.get("code", p.get("stock_code", "")): {
            "name": p.get("name", ""),
            "shares": p.get("shares", 0),
            "cost": p.get("cost", 0),
        }
        for p in pf if p.get("code") or p.get("stock_code")
    }


# ═══════════════════════════════════════════════════
# 触发节点 1: 止损失败
# ═══════════════════════════════════════════════════

_STOP_LOSS_KEYWORDS = ["止损", "stop_loss", "硬止损", "-7%", "止损单",
                       "止损未执行", "触及止损", "应止损"]


def check_stop_loss_miss() -> Optional[dict]:
    """
    检测止损失败: last_error.txt 中含止损相关错误 + 该票仍在持仓。
    调用时机: 盘后复盘 (daily_task.py closing_review) 或 健康检查 (health_check.py)
    """
    if not ERROR_PATH.exists():
        return None

    error_text = ERROR_PATH.read_text("utf-8", errors="replace")[:5000]
    if not any(kw in error_text for kw in _STOP_LOSS_KEYWORDS):
        return None

    portfolio = _current_portfolio()
    if not portfolio:
        return None

    # 从报错中提取可能涉及的股票代码
    import re
    codes_in_error = set(re.findall(r'\b(00\d{4}|30\d{4}|60\d{4}|68\d{4})\b', error_text))
    still_held = [c for c in codes_in_error if c in portfolio]

    if not still_held:
        return None

    return {
        "trigger": "stop_loss_miss",
        "context": {
            "stock": still_held[0],
            "position": portfolio[still_held[0]]["shares"],
            "cost": portfolio[still_held[0]]["cost"],
            "still_held_codes": still_held,
        },
        "error_snippet": error_text[:500],
    }


# ═══════════════════════════════════════════════════
# 触发节点 2: 决策证伪
# ═══════════════════════════════════════════════════

def check_decision_falsified(morning_direction: dict = None,
                              closing_data: dict = None,
                              brief_path: str = None) -> Optional[dict]:
    """
    检测决策证伪: 晨报方向判断 vs 收盘实际方向 背离 > DECISION_THRESHOLD。

    Args:
        morning_direction: {code: direction} — "看多"/"看空"/"中性"
        closing_data: {code: change_pct} — 当日涨跌幅
        brief_path: 晨报文件路径 (用于溯源)

    调用时机: 收盘复盘 (daily_task.py closing_review)
    """
    if not morning_direction or not closing_data:
        return None

    falsified = []
    for code, direction in morning_direction.items():
        if code not in closing_data:
            continue
        chg = closing_data[code]
        if direction == "看多" and chg < -DECISION_THRESHOLD:
            falsified.append({"code": code, "expected": "看多", "actual": f"{chg}%", "gap": abs(chg)})
        elif direction == "看空" and chg > DECISION_THRESHOLD:
            falsified.append({"code": code, "expected": "看空", "actual": f"+{chg}%", "gap": abs(chg)})
        elif direction == "中性" and abs(chg) > DECISION_THRESHOLD * 2:
            falsified.append({"code": code, "expected": "中性", "actual": f"{chg}%", "gap": abs(chg)})

    if not falsified:
        return None

    return {
        "trigger": "decision_falsified",
        "context": {
            "falsified_count": len(falsified),
            "details": falsified,
        },
        "related_artifacts": {"morning_brief": brief_path} if brief_path else {},
    }


# ═══════════════════════════════════════════════════
# 触发节点 3: 竞价异常
# ═══════════════════════════════════════════════════

def check_auction_divergence(auction_signal: dict = None,
                              intraday_data: dict = None) -> Optional[dict]:
    """
    检测竞价异常: 竞价量信号 + 当日实际走势背离。

    Args:
        auction_signal: {code: {signal, ratio, today_volume, avg_volume}}
        intraday_data: {code: change_pct} — 当日涨跌幅

    调用时机: 盘中/盘后均可，只要有 auction_signal + intraday_data
    """
    if not auction_signal or not intraday_data:
        return None

    diverged = []
    for code, sig in auction_signal.items():
        if code not in intraday_data:
            continue
        chg = intraday_data[code]
        signal_type = sig.get("signal", "")
        ratio = sig.get("ratio", 0)
        if signal_type == "放量" and ratio >= AUCTION_DIVERGE_RATIO and chg < -2:
            diverged.append({"code": code, "signal": "放量", "ratio": ratio,
                             "actual": f"{chg}%", "type": "放量下跌"})
        elif signal_type == "缩量" and ratio <= 1 / AUCTION_DIVERGE_RATIO and chg > 2:
            diverged.append({"code": code, "signal": "缩量", "ratio": ratio,
                             "actual": f"+{chg}%", "type": "缩量上涨"})

    if not diverged:
        return None

    return {
        "trigger": "auction_divergence",
        "context": {
            "diverged_count": len(diverged),
            "details": diverged,
        },
    }


# ═══════════════════════════════════════════════════
# 触发节点 4: 新票首亏
# ═══════════════════════════════════════════════════

def check_first_loss(sold_record: dict = None) -> Optional[dict]:
    """
    检测新票首亏: 首次买入某票后第一次止损/出清。

    Args:
        sold_record: {code, name, sold_price, cost, pnl, sold_date}

    调用时机: 出清记录写入时 (portfolio.json 更新后)
    """
    if not sold_record:
        return None

    pnl = sold_record.get("pnl", 0)
    if pnl >= 0:
        return None  # 盈利出清不算

    code = sold_record.get("code", "")
    # 检查已清仓历史: 如果该票之前出清过 → 不是"首亏"
    portfolio = _load_json(PORTFOLIO_PATH)
    if isinstance(portfolio, dict):
        closed = portfolio.get("closed", portfolio.get("history", []))
    else:
        closed = []

    prev_exits = [r for r in closed if r.get("code") == code]
    if len(prev_exits) > 1:
        return None  # 不是首次出清

    return {
        "trigger": "first_loss",
        "context": {
            "stock": code,
            "name": sold_record.get("name", ""),
            "sold_price": sold_record.get("sold_price"),
            "cost": sold_record.get("cost"),
            "pnl": pnl,
            "sold_date": sold_record.get("sold_date", ""),
        },
    }


# ═══════════════════════════════════════════════════
# 批量检查 + 队列状态
# ═══════════════════════════════════════════════════

def run_all_checks(morning_direction: dict = None,
                   closing_data: dict = None,
                   auction_signal: dict = None,
                   intraday_data: dict = None,
                   sold_record: dict = None) -> list[dict]:
    """
    运行全部 4 个触发检查，将命中的记录写入队列。
    返回本次新捕获的记录列表。
    """
    captured = []

    r = check_stop_loss_miss()
    if r:
        _append_to_queue(r)
        captured.append(r)

    r = check_decision_falsified(morning_direction, closing_data)
    if r:
        _append_to_queue(r)
        captured.append(r)

    r = check_auction_divergence(auction_signal, intraday_data)
    if r:
        _append_to_queue(r)
        captured.append(r)

    r = check_first_loss(sold_record)
    if r:
        _append_to_queue(r)
        captured.append(r)

    return captured


def queue_status() -> dict:
    """返回蒸馏队列的当前状态。"""
    queue = _load_queue()
    from collections import Counter
    trigger_counts = Counter(r.get("trigger") for r in queue)
    return {
        "total": len(queue),
        "by_trigger": dict(trigger_counts),
        "ready_for_distill": len(queue) >= 5,
        "path": str(QUEUE_PATH),
    }


# ═══════════════════════════════════════════════════
# 命令行
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    status = queue_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    if status["total"] > 0:
        print(f"\n队列已有 {status['total']} 条，{'达到' if status['ready_for_distill'] else '未达到'}蒸馏阈值(5条)")
