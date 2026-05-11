"""
持仓管理系统 — 接入现有持仓，每日自动检查三层机制
可作为脚本手动跑，也可加入定时任务

当前持仓 (来自 CLAUDE.md，硬约束):
  000062 深圳华强  2000股 成本36.88 止损34.30
  002156 通富微电  2300股 成本49.79 止损46.30
  300480 光力科技   700股 成本36.29 止损33.75
  002407 多氟多     400股 成本35.60 止损33.11
  300342 天银机电   200股 成本64.50 止损59.99
"""
import json
import os
import sys
from datetime import datetime, date as date_type
from dataclasses import dataclass, field
from typing import List, Optional, Dict

DATA_DIR = "D:/1989n/stock_data"
STATE_FILE = os.path.join(DATA_DIR, "position_state.json")

# ============================================================
# 持仓数据 (来自 CLAUDE.md — 每次会话必须记住)
# ============================================================
# 最后更新: 2026-05-08 收盘 — 从东方财富交易记录反推核实
# 买入日期: 从原始交易数据FIFO匹配后剩余批次提取 (2026-05-11)
HOLDINGS = [
    {"code": "000062", "name": "深圳华强", "qty": 2000, "cost": 37.28, "stop": 34.67, "sector": "电子元器件分销",
     "first_buy": "2026-04-30", "latest_buy": "2026-05-06"},
    {"code": "002156", "name": "通富微电", "qty": 2200, "cost": 49.77, "stop": 46.29, "sector": "半导体封测",
     "first_buy": "2026-04-27", "latest_buy": "2026-04-29"},
    {"code": "300480", "name": "光力科技", "qty": 400,  "cost": 36.28, "stop": 33.74, "sector": "半导体划片设备",
     "first_buy": "2026-04-30", "latest_buy": "2026-04-30"},
    {"code": "002407", "name": "多氟多",   "qty": 600,  "cost": 36.25, "stop": 33.71, "sector": "锂电化工",
     "first_buy": "2026-05-06", "latest_buy": "2026-05-07"},
    {"code": "300342", "name": "天银机电", "qty": 200,  "cost": 64.56, "stop": 60.04, "sector": "商业航天/军工电子",
     "first_buy": "2026-05-08", "latest_buy": "2026-05-08"},
    {"code": "300739", "name": "明阳电路", "qty": 100,  "cost": 29.72, "stop": 27.64, "sector": "PCB/电子",
     "first_buy": "2026-04-23", "latest_buy": "2026-04-23"},
]

# ============================================================
# 三层机制规则
# ============================================================
RULES = {
    "hard_stop_pct": -7.0,       # 无条件砍
    "soft_stop_pct": -3.0,       # 减半仓
    "take_profit_half": 8.0,     # 止盈50%
    "take_profit_all": 15.0,     # 全部止盈
    "trail_activate": 5.0,       # 启动移动止损
    "trail_distance": 3.0,       # 回撤容忍
    "danger_zone": (3, 5),       # 危险持仓天数
    "max_hold": 10,              # 强制清仓天数
    "new_position": {
        "volume_ok": ["放量", "正常"],
        "trend_ok": ["多头排列", "短期偏多", "短期偏空", "震荡"],
        "sentiment_ok": ["强势", "偏强", "偏弱", "弱势"],
    },
    "account": {
        "max_single_pct": 0.30,  # 单票最高仓位
        "daily_loss_limit": 0.02,  # 日亏损2%熔断
        "max_consecutive_loss": 3,  # 连亏3笔停
    }
}


@dataclass
class Position:
    code: str
    name: str
    qty: int
    cost: float
    hard_stop: float
    soft_stop: float
    target_half: float
    target_all: float
    sector: str
    buy_date: str
    hold_days: int = 0
    last_price: float = 0.0
    market_value: float = 0.0
    pnl_pct: float = 0.0
    pnl_amount: float = 0.0
    status: str = "正常"       # 正常 / 止损 / 止盈 / 危险区 / 超时
    action: str = "持有"       # 持有 / 减半 / 清仓 / 已触发止损
    warnings: List[str] = field(default_factory=list)

    @classmethod
    def from_holding(cls, h: dict, buy_date: str = None):
        cost = h["cost"]
        # 优先用 first_buy (最早批次), 其次用传入的 buy_date
        effective_buy = h.get("first_buy") or buy_date or "未知"
        return cls(
            code=h["code"], name=h["name"], qty=h["qty"], cost=cost,
            hard_stop=round(cost * 0.93, 2),
            soft_stop=round(cost * 0.97, 2),
            target_half=round(cost * 1.08, 2),
            target_all=round(cost * 1.15, 2),
            sector=h["sector"],
            buy_date=effective_buy,
        )


class PositionManager:
    def __init__(self):
        self.holdings = HOLDINGS
        self.calendar = self._load_calendar()
        self.state = self._load_state()  # 持久化状态

    def _load_calendar(self):
        for fname in ["market_calendar_full.json", "market_calendar.json"]:
            path = os.path.join(DATA_DIR, fname)
            if os.path.exists(path):
                with open(path, "r") as f:
                    return json.load(f)
        return {}

    def _load_state(self):
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        return {
            "positions": {},
            "daily": {"date": "", "trades_today": 0, "loss_today": 0,
                       "consecutive_losses": 0, "circuit_breaker": False},
            "history": [],
        }

    def save_state(self):
        self.state["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def get_market(self, date_str=None):
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")
        if date_str in self.calendar:
            return self.calendar[date_str]
        for d in sorted(self.calendar.keys(), reverse=True):
            if d <= date_str:
                return self.calendar[d]
        return {}

    def update_positions(self, current_prices: Dict[str, float] = None,
                         buy_dates: Dict[str, str] = None):
        """更新持仓状态，检查三层规则"""
        today = datetime.now().strftime("%Y-%m-%d")
        mkt = self.get_market(today)
        positions = []

        for h in self.holdings:
            code = h["code"]
            # 优先用传入的buy_dates, 其次用holding自带的first_buy
            if buy_dates and code in buy_dates:
                buy_date = buy_dates[code]
            else:
                buy_date = h.get("first_buy") or today
            pos = Position.from_holding(h, buy_date)

            # 计算持仓天数
            try:
                bd = datetime.strptime(buy_date, "%Y-%m-%d")
                td = datetime.strptime(today, "%Y-%m-%d")
                pos.hold_days = (td - bd).days
            except Exception:
                pos.hold_days = 0

            # 如果有当前价格
            if current_prices and code in current_prices:
                pos.last_price = current_prices[code]
                pos.market_value = pos.qty * pos.last_price
                pos.pnl_pct = (pos.last_price - pos.cost) / pos.cost * 100
                pos.pnl_amount = (pos.last_price - pos.cost) * pos.qty

                # === 三层检查 ===

                # 第一层：硬止损
                if pos.pnl_pct <= RULES["hard_stop_pct"]:
                    pos.status = "止损"
                    pos.action = "清仓"
                    pos.warnings.append(f"⛔ 硬止损触发: {pos.pnl_pct:.1f}% ≤ -7%")

                # 第二层：软止损
                elif pos.pnl_pct <= RULES["soft_stop_pct"]:
                    pos.status = "预警"
                    pos.action = "减半"
                    pos.warnings.append(f"⚠ 软止损: {pos.pnl_pct:.1f}%, 减半仓")

                # 第三层：危险区
                elif RULES["danger_zone"][0] <= pos.hold_days <= RULES["danger_zone"][1]:
                    if pos.pnl_pct < 0:
                        pos.status = "危险区"
                        pos.action = "清仓"
                        pos.warnings.append(f"⛔ 危险区第{pos.hold_days}天+浮亏{pos.pnl_pct:.1f}%")
                    elif pos.pnl_pct <= 2:
                        pos.status = "危险区"
                        pos.action = "止盈"
                        pos.warnings.append(f"⚠ 危险区第{pos.hold_days}天+微利{pos.pnl_pct:+.1f}%")

                # 止盈
                if pos.pnl_pct >= RULES["take_profit_all"]:
                    pos.status = "止盈"
                    pos.action = "清仓"
                    pos.warnings.append(f"💰 +15%止盈: {pos.pnl_pct:.1f}%")
                elif pos.pnl_pct >= RULES["take_profit_half"]:
                    pos.status = "止盈"
                    pos.action = "减半"
                    pos.warnings.append(f"💰 +8%止盈一半: {pos.pnl_pct:.1f}%")

                # 移动止损
                if pos.pnl_pct >= RULES["trail_activate"] and pos.action == "持有":
                    trail = RULES["trail_activate"] - RULES["trail_distance"]
                    pos.warnings.append(f"📈 移动止损激活: 浮盈{pos.pnl_pct:.1f}%, 保护线+{trail}%")

                # 超时
                if pos.hold_days > RULES["max_hold"] and pos.action == "持有":
                    pos.status = "超时"
                    pos.action = "清仓"
                    pos.warnings.append(f"⏰ 超时{pos.hold_days}天")

            else:
                pos.warnings.append("无实时价格数据")

            positions.append(pos)

        return positions

    def can_open_new(self) -> tuple:
        """检查能否开新仓"""
        mkt = self.get_market()
        reasons = []

        vol = mkt.get("volume_state", "")
        trend = mkt.get("trend", "")
        sent = mkt.get("sentiment", "")

        if vol == "缩量":
            reasons.append(("NOGO", f"缩量环境(5年均盈亏-0.68%)"))
        if trend == "空头排列":
            reasons.append(("NOGO", f"空头排列(5年均盈亏-1.31%)"))
        if sent == "恐慌":
            reasons.append(("NOGO", f"恐慌情绪"))

        # 账户状态
        cb = self.state["daily"].get("circuit_breaker", False)
        if cb:
            reasons.append(("NOGO", "熔断中: 连亏3笔"))

        can_open = not any(r[0] == "NOGO" for r in reasons)
        return can_open, reasons


def report(positions: List[Position], manager: PositionManager):
    """生成持仓报告"""
    total_value = sum(p.market_value for p in positions if p.last_price > 0)
    total_pnl = sum(p.pnl_amount for p in positions if p.last_price > 0)
    total_cost = sum(p.cost * p.qty for p in positions)

    today = datetime.now().strftime("%Y-%m-%d")
    mkt = manager.get_market()
    can_open, open_reasons = manager.can_open_new()

    print(f"\n{'='*65}")
    print(f"  持仓管理报告 — {today}")
    print(f"{'='*65}")

    # 市场状态
    print(f"\n  ── 市场环境 ──")
    print(f"  趋势: {mkt.get('trend','?')}  |  量能: {mkt.get('volume_state','?')}  |  情绪: {mkt.get('sentiment','?')}")

    # 开仓权限
    if can_open:
        print(f"  ✅ 可以开新仓")
    else:
        print(f"  ⛔ 不建议开新仓:")
        for _, reason in open_reasons:
            print(f"     - {reason}")

    # 组合总览
    print(f"\n  ── 组合总览 ──")
    print(f"  总成本: {total_cost:,.0f}  总市值: {total_value:,.0f}  总盈亏: {total_pnl:+,.0f} ({total_pnl/total_cost*100:+.2f}%)")

    # 逐个持仓
    action_needed = []
    print(f"\n  ── 逐个持仓 ──")
    print(f"  {'代码':<8} {'名称':<8} {'持仓':<6} {'成本':<8} {'现价':<8} {'盈亏':<10} {'天数':<5} {'状态':<8} {'操作'}")
    print(f"  {'-'*65}")

    for p in positions:
        price_str = f"{p.last_price:.2f}" if p.last_price > 0 else "---"
        pnl_str = f"{p.pnl_pct:+.1f}%" if p.last_price > 0 else "---"
        print(f"  {p.code:<8} {p.name:<8} {p.qty:<6} {p.cost:<8.2f} {price_str:<8} {pnl_str:<10} "
              f"{p.hold_days if p.hold_days > 0 else '?':<5} {p.status:<8} {p.action}")

        if p.warnings:
            for w in p.warnings:
                print(f"    → {w}")
            if p.action in ("清仓", "减半"):
                action_needed.append(p)

    # 需要行动
    if action_needed:
        print(f"\n  ╔══════════════════════════════════╗")
        print(f"  ║  ⚠ 需要立即行动: {len(action_needed)} 笔  ║")
        print(f"  ╚══════════════════════════════════╝")
        for p in action_needed:
            price_info = f" @{p.last_price:.2f}" if p.last_price > 0 else ""
            print(f"  → {p.name}({p.code}): {p.action}{price_info} — {p.warnings[0] if p.warnings else ''}")
    else:
        print(f"\n  ✅ 所有持仓状态正常，无需操作")

    # 今日价格更新提示
    if not any(p.last_price > 0 for p in positions):
        print(f"\n  💡 提示: 提供实时价格以获取完整检查结果")
        print(f"     python position_manager.py update <code> <price> ...")

    print()


def main():
    manager = PositionManager()

    if len(sys.argv) < 2:
        # 默认：显示报告（可能无实时价格）
        positions = manager.update_positions()
        report(positions, manager)
        return

    cmd = sys.argv[1]

    if cmd == "report":
        # 显示完整报告
        prices = {}
        # 支持从命令行传入价格
        i = 2
        while i + 1 < len(sys.argv):
            prices[sys.argv[i]] = float(sys.argv[i + 1])
            i += 2
        positions = manager.update_positions(prices)
        report(positions, manager)

    elif cmd == "update":
        # 更新价格并显示
        prices = {}
        i = 2
        while i + 1 < len(sys.argv):
            prices[sys.argv[i]] = float(sys.argv[i + 1])
            i += 2
        positions = manager.update_positions(prices)
        report(positions, manager)

    elif cmd == "auto":
        # 自动模式：从最新盘中报告提取价格
        import glob
        today = datetime.now().strftime("%Y%m%d")
        pattern = os.path.join(DATA_DIR, f"analysis_30min_{today}*.json")
        files = sorted(glob.glob(pattern))
        if not files:
            # 尝试找最近的
            pattern = os.path.join(DATA_DIR, "analysis_30min_*.json")
            files = sorted(glob.glob(pattern))
        if files:
            latest = files[-1]
            with open(latest, "r") as f:
                data = json.load(f)
            prices = {}
            for h in data.get("holdings", []):
                prices[h["code"]] = float(h["price"])
            print(f"[auto] 从 {os.path.basename(latest)} 提取 {len(prices)} 个价格")
            positions = manager.update_positions(prices)
            report(positions, manager)
        else:
            print("[auto] 未找到盘中报告, 使用无价格模式")
            positions = manager.update_positions()
            report(positions, manager)

    elif cmd == "can_open":
        can, reasons = manager.can_open_new()
        if can:
            print("✅ 可以开新仓")
        else:
            print("⛔ 不建议开新仓")
            for _, reason in reasons:
                print(f"  - {reason}")

    elif cmd == "plan":
        # 为持仓中某只股票生成交易计划
        if len(sys.argv) < 3:
            print("用法: python position_manager.py plan <code>")
            return
        code = sys.argv[2]
        h = next((h for h in HOLDINGS if h["code"] == code), None)
        if h:
            print(f"\n  {'='*50}")
            print(f"  {h['name']}({h['code']}) 交易计划")
            print(f"  {'='*50}")
            print(f"  ┌────────────────────────────┐")
            print(f"  │ 成本: {h['cost']:.2f}")
            print(f"  │ 仓位: {h['qty']}股 ({h['qty']*h['cost']:,.0f}元)")
            print(f"  │ 硬止损(-7%): {h['cost']*0.93:.2f}")
            print(f"  │ 止盈50%(+8%): {h['cost']*1.08:.2f}")
            print(f"  │ 止盈全部(+15%): {h['cost']*1.15:.2f}")
            print(f"  │ 移动止损激活(+5%): {h['cost']*1.05:.2f}")
            print(f"  └────────────────────────────┘")
        else:
            print(f"持仓中未找到 {code}")

    elif cmd == "history":
        # 显示操作历史
        history = manager.state.get("history", [])
        if history:
            print(f"\n  操作历史 ({len(history)} 条):")
            for h in history[-20:]:
                print(f"  {h.get('date','')} {h.get('action','')} {h.get('code','')} — {h.get('reason','')}")
        else:
            print("暂无操作记录")

    elif cmd == "log":
        # 记录一次操作
        if len(sys.argv) < 4:
            print("用法: python position_manager.py log <code> <action> <reason>")
            return
        code = sys.argv[2]
        action = sys.argv[3]
        reason = " ".join(sys.argv[4:]) if len(sys.argv) > 4 else ""
        manager.state["history"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "code": code,
            "action": action,
            "reason": reason,
        })
        manager.save_state()
        print(f"已记录: {code} {action} — {reason}")

    else:
        print("用法:")
        print("  python position_manager.py                    # 持仓概览")
        print("  python position_manager.py report [code price ...]  # 完整报告+价格")
        print("  python position_manager.py update <code> <price> ... # 更新价格")
        print("  python position_manager.py can_open            # 检查能否开新仓")
        print("  python position_manager.py plan <code>         # 单票交易计划")
        print("  python position_manager.py log <code> <action> <reason>  # 记录操作")
        print("  python position_manager.py history             # 操作历史")


if __name__ == "__main__":
    main()
