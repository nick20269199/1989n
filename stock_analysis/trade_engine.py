"""
交易引擎 v1.0 — 三层机制：过滤层 / 执行层 / 风控层
基于 2021-2026 共 3,817 笔往返交易的回测数据构建
"""
import json
import os
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, List, Tuple

DATA_DIR = "D:/1989n/stock_data"

# ============================================================
# 从5年数据中提炼的核心参数（不可随意修改）
# ============================================================

class Params:
    # —— 来自5年数据的实证 ——
    # 放量买入均收益 +1.35%，缩量买入均收益 -0.68%
    # 0-2天持仓胜率47.4%，3-5天41.5%，6-10天53.5%
    # 止损犹豫254笔亏45.8万，均亏-12.6%
    # 低频标的(<4次)胜率29.8%，高频(≥10次)胜率53.5%
    # 盈亏比0.72 — 赚1元覆盖不了亏1元

    # —— 过滤层参数 ——
    MIN_STOCK_FAMILIARITY = 4       # 标的至少交易过4次
    VOLUME_MIN_STATE = "正常"       # 缩量不开仓
    TREND_BLACKLIST = ["空头排列"]   # 空头排列不开多仓
    SENTIMENT_BLACKLIST = ["恐慌"]   # 恐慌日不开仓

    # —— 执行层参数 ——
    HARD_STOP_PCT = -7.0            # 无条件硬止损
    SOFT_STOP_PCT = -3.0            # 浮亏3%减半仓
    PROFIT_TAKE_50_PCT = 8.0        # +8%止盈一半
    PROFIT_TAKE_ALL_PCT = 15.0      # +15%清仓
    TRAIL_STOP_ACTIVATE = 5.0       # 浮盈5%启动移动止损
    TRAIL_STOP_DISTANCE = 3.0       # 移动止损距离3%
    DANGER_ZONE_START = 3           # 持仓第3天起进入危险区
    DANGER_ZONE_END = 5             # 持仓第5天结束
    MAX_HOLD_DAYS = 10              # 最大持仓天数

    # —— 风控层参数 ——
    MAX_SINGLE_POSITION_PCT = 0.30  # 单票最高30%仓位
    DAILY_LOSS_LIMIT_PCT = 0.02     # 日亏损2%停止交易
    CONSECUTIVE_LOSS_LIMIT = 3      # 连续亏损3笔停一天
    MONTHLY_MIN_WIN_RATE = 0.40     # 月胜率<40%下月减半仓
    MAX_DAILY_TRADES = 8            # 单日最多8笔


class Signal(Enum):
    GO = "开仓"
    NOGO = "不开仓"
    WARN = "警示(需人工确认)"


class PositionState(Enum):
    ACTIVE = "持仓中"
    CLOSED_WIN = "已止盈"
    CLOSED_STOP = "已止损"
    CLOSED_TIME = "时间止"
    CLOSED_FILTER = "过滤止"


@dataclass
class TradePlan:
    """单笔交易计划"""
    code: str
    name: str
    entry_price: float
    position_pct: float
    hard_stop: float          # -7%
    soft_stop: float           # -3%
    target_50: float           # +8%
    target_all: float          # +15%
    max_hold_days: int = 10
    danger_zone: Tuple[int, int] = (3, 5)
    signals: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def summary(self):
        return f"""
╔══════════════════════════════════════╗
║ {self.name}({self.code}) 交易计划
╠══════════════════════════════════════╣
║ 入场价: {self.entry_price:.2f}
║ 仓位: {self.position_pct*100:.0f}%
║ ────────────────────────────────
║ 硬止损(-7%): {self.hard_stop:.2f}
║ 软止损(-3%): {self.soft_stop:.2f}
║ 止盈50%(+8%): {self.target_50:.2f}
║ 止盈全部(+15%): {self.target_all:.2f}
║ ────────────────────────────────
║ 最大持仓: {self.max_hold_days}天
║ 危险区: 第{self.danger_zone[0]}-{self.danger_zone[1]}天
╚══════════════════════════════════════╝"""


@dataclass
class DailyState:
    """每日交易状态追踪"""
    date: str
    total_trades: int = 0
    consecutive_losses: int = 0
    daily_pnl: float = 0.0
    daily_pnl_pct: float = 0.0
    circuit_breaker: bool = False
    active_positions: List[str] = field(default_factory=list)


class TradeEngine:
    """核心交易引擎"""

    def __init__(self, portfolio_value: float = 240000):
        self.portfolio_value = portfolio_value
        self.daily_state = DailyState(date=datetime.now().strftime("%Y-%m-%d"))
        self.position_history: List[Dict] = []
        self.stock_familiarity: Dict[str, int] = {}  # code -> prior trade count

        # 加载历史数据
        self._load_familiarity()
        self._load_market_calendar()

    def _load_familiarity(self):
        """从历史交易中加载每个标的的交易次数"""
        analysis_path = os.path.join(DATA_DIR, "bs_full_analysis.json")
        if not os.path.exists(analysis_path):
            return
        # 从原始数据重新统计
        try:
            import openpyxl
            from collections import Counter
            stock_count = Counter()
            for f in ["2021-22.xlsx", "2022-2023.xlsx", "2023-2024xlsx.xlsx",
                       "2024-2025.xlsx", "2025-2026.xlsx"]:
                path = os.path.join("D:/东方财富", f)
                if os.path.exists(path):
                    wb = openpyxl.load_workbook(path)
                    ws = wb.active
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        if row[3] and row[5] in ("证券买入", "证券卖出"):
                            stock_count[str(row[3])] += 1
                    wb.close()
            self.stock_familiarity = dict(stock_count)
        except Exception:
            pass

    def _load_market_calendar(self):
        """加载市场日历"""
        cal_path = os.path.join(DATA_DIR, "market_calendar_full.json")
        if os.path.exists(cal_path):
            with open(cal_path, "r") as f:
                self.calendar = json.load(f)
        else:
            self.calendar = {}

    # ================================================================
    # 第一层：过滤层 — 判断能不能开仓
    # ================================================================

    def filter_volume(self, trade_date: str) -> Tuple[Signal, str]:
        """量能过滤：缩量不开仓"""
        mkt = self.calendar.get(trade_date)
        if not mkt:
            return Signal.WARN, "无市场数据，人工判断"
        vol = mkt.get("volume_state", "正常")
        if vol == "缩量":
            return Signal.NOGO, f"缩量环境(5年均收益-0.68%)"
        if vol == "放量":
            return Signal.GO, f"放量环境(5年均收益+1.35%)"
        return Signal.GO, f"量能正常"

    def filter_trend(self, trade_date: str) -> Tuple[Signal, str]:
        """趋势过滤：空头排列不开多仓"""
        mkt = self.calendar.get(trade_date)
        if not mkt:
            return Signal.WARN, "无市场数据"
        trend = mkt.get("trend", "")
        if trend in Params.TREND_BLACKLIST:
            return Signal.NOGO, f"大盘{trend}，5年空头买入均亏"
        return Signal.GO, f"大盘{trend}"

    def filter_sentiment(self, trade_date: str) -> Tuple[Signal, str]:
        """情绪过滤：恐慌日不开仓"""
        mkt = self.calendar.get(trade_date)
        if not mkt:
            return Signal.WARN, "无市场数据"
        sent = mkt.get("sentiment", "")
        if sent in Params.SENTIMENT_BLACKLIST:
            return Signal.NOGO, f"市场{sent}，情绪极端不宜开仓"
        if sent == "弱势":
            return Signal.WARN, f"市场{sent}，建议减半仓"
        return Signal.GO, f"市场情绪{sent}"

    def filter_familiarity(self, stock_code: str) -> Tuple[Signal, str]:
        """标的熟悉度过滤：低频标的胜率仅29.8%"""
        count = self.stock_familiarity.get(stock_code, 0)
        if count == 0:
            return Signal.WARN, f"全新标的(5年数据: 首次交易胜率极低)"
        if count < Params.MIN_STOCK_FAMILIARITY:
            return Signal.WARN, f"仅交易过{count}次(低频标的胜率29.8%)"
        if count >= 10:
            return Signal.GO, f"高频标的({count}次, 胜率53.5%)"
        return Signal.GO, f"已交易{count}次"

    def filter_account_state(self) -> Tuple[Signal, str]:
        """账户状态过滤"""
        if self.daily_state.circuit_breaker:
            return Signal.NOGO, f"熔断中: 连续亏损{Params.CONSECUTIVE_LOSS_LIMIT}笔"
        if self.daily_state.daily_pnl_pct <= -Params.DAILY_LOSS_LIMIT_PCT:
            return Signal.NOGO, f"日亏损已达{self.daily_state.daily_pnl_pct*100:.1f}%"
        if self.daily_state.consecutive_losses >= 2:
            return Signal.WARN, f"已连续亏损{self.daily_state.consecutive_losses}笔"
        if self.daily_state.total_trades >= Params.MAX_DAILY_TRADES:
            return Signal.NOGO, f"已达日交易上限{Params.MAX_DAILY_TRADES}笔"
        return Signal.GO, "账户状态正常"

    def pre_trade_check(self, stock_code: str, trade_date: str = None) -> Tuple[Signal, List[str]]:
        """开仓前综合检查 — 调用所有过滤器"""
        if trade_date is None:
            trade_date = datetime.now().strftime("%Y-%m-%d")

        checks = []
        all_go = True
        has_nogo = False
        warnings = []

        for name, check_fn in [
            ("量能", self.filter_volume),
            ("大盘", self.filter_trend),
            ("情绪", self.filter_sentiment),
            ("标的", lambda d: self.filter_familiarity(stock_code)),
            ("账户", lambda d: self.filter_account_state()),
        ]:
            signal, msg = check_fn(trade_date)
            checks.append(f"[{signal.value}] {name}: {msg}")
            if signal == Signal.NOGO:
                has_nogo = True
            elif signal == Signal.WARN:
                warnings.append(msg)
            if signal != Signal.GO:
                all_go = False

        if has_nogo:
            return Signal.NOGO, checks
        if not all_go:
            return Signal.WARN, checks
        return Signal.GO, checks

    # ================================================================
    # 第二层：执行层 — 开仓后怎么管
    # ================================================================

    def create_trade_plan(self, code: str, name: str, entry_price: float,
                          position_pct: float = None) -> TradePlan:
        """生成交易计划"""
        if position_pct is None:
            # 默认仓位：根据标的熟悉度调整
            count = self.stock_familiarity.get(code, 0)
            if count >= 10:
                position_pct = 0.25
            elif count >= 4:
                position_pct = 0.15
            else:
                position_pct = 0.05  # 不熟悉的用5%试仓

        # 仓位不能超过30%
        position_pct = min(position_pct, Params.MAX_SINGLE_POSITION_PCT)

        plan = TradePlan(
            code=code,
            name=name,
            entry_price=entry_price,
            position_pct=position_pct,
            hard_stop=round(entry_price * (1 + Params.HARD_STOP_PCT / 100), 2),
            soft_stop=round(entry_price * (1 + Params.SOFT_STOP_PCT / 100), 2),
            target_50=round(entry_price * (1 + Params.PROFIT_TAKE_50_PCT / 100), 2),
            target_all=round(entry_price * (1 + Params.PROFIT_TAKE_ALL_PCT / 100), 2),
            max_hold_days=Params.MAX_HOLD_DAYS,
            danger_zone=(Params.DANGER_ZONE_START, Params.DANGER_ZONE_END),
        )
        return plan

    def check_position(self, plan: TradePlan, current_price: float,
                       hold_days: int, current_pnl_pct: float) -> Tuple[PositionState, str]:
        """持仓检查 — 每个交易日至少跑一次"""

        # 铁律：-7% 无条件砍
        if current_pnl_pct <= Params.HARD_STOP_PCT:
            return PositionState.CLOSED_STOP, f"硬止损触发: {current_pnl_pct:.1f}% ≤ -7%"

        # 危险区(3-5天)特殊处理
        if Params.DANGER_ZONE_START <= hold_days <= Params.DANGER_ZONE_END:
            # 危险区 + 浮亏 → 砍
            if current_pnl_pct <= -3:
                return PositionState.CLOSED_TIME, f"危险区第{hold_days}天 + 浮亏{current_pnl_pct:.1f}%"
            # 危险区 + 微利 → 减半
            if 0 <= current_pnl_pct <= 2:
                return PositionState.CLOSED_TIME, f"危险区第{hold_days}天, 微利{current_pnl_pct:.1f}%止盈"

        # 浮盈5%启动移动止损
        if current_pnl_pct >= Params.TRAIL_STOP_ACTIVATE:
            trail_stop = current_pnl_pct - Params.TRAIL_STOP_DISTANCE
            if current_pnl_pct <= trail_stop:
                return PositionState.CLOSED_WIN, f"移动止损触发: 回撤至{current_pnl_pct:.1f}%"

        # +8% 止盈50%
        if current_pnl_pct >= Params.PROFIT_TAKE_50_PCT:
            return PositionState.CLOSED_WIN, f"+8%止盈一半: {current_pnl_pct:.1f}%"

        # +15% 全清
        if current_pnl_pct >= Params.PROFIT_TAKE_ALL_PCT:
            return PositionState.CLOSED_WIN, f"+15%全清: {current_pnl_pct:.1f}%"

        # 超时
        if hold_days > Params.MAX_HOLD_DAYS:
            return PositionState.CLOSED_TIME, f"超时{hold_days}天, 强制清仓"

        # -3% 软止损
        if current_pnl_pct <= Params.SOFT_STOP_PCT:
            return PositionState.CLOSED_STOP, f"软止损触发: {current_pnl_pct:.1f}% ≤ -3%, 减半仓或清"

        return PositionState.ACTIVE, f"持仓正常, 第{hold_days}天, {current_pnl_pct:+.1f}%"

    # ================================================================
    # 第三层：风控层 — 全账户级别的风险控制
    # ================================================================

    def check_account_risk(self) -> Tuple[bool, str]:
        """账户级别风控检查"""
        if self.daily_state.circuit_breaker:
            return False, "熔断中: 今日禁止开新仓"
        if self.daily_state.daily_pnl_pct <= -Params.DAILY_LOSS_LIMIT_PCT:
            self.daily_state.circuit_breaker = True
            return False, f"日亏损{self.daily_state.daily_pnl_pct*100:.1f}%触发熔断"
        return True, "风控正常"

    def on_trade_closed(self, pnl_pct: float, is_win: bool):
        """每笔交易平仓后调用"""
        self.daily_state.total_trades += 1
        if is_win:
            self.daily_state.consecutive_losses = 0
        else:
            self.daily_state.consecutive_losses += 1
            if self.daily_state.consecutive_losses >= Params.CONSECUTIVE_LOSS_LIMIT:
                self.daily_state.circuit_breaker = True

    def end_of_day_reset(self):
        """每日重置"""
        self.daily_state = DailyState(date=datetime.now().strftime("%Y-%m-%d"))


# ================================================================
# 方便的CLI接口
# ================================================================

def pre_trade_checklist(stock_code: str, stock_name: str = "",
                        entry_price: float = 0, portfolio_value: float = 240000):
    """开仓前完整检查清单 — 打印给用户看"""
    engine = TradeEngine(portfolio_value)

    print(f"\n{'='*60}")
    print(f"交易决策检查清单 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    # 第一层
    print(f"\n── 第一层：过滤层 ──")
    signal, checks = engine.pre_trade_check(stock_code)
    for c in checks:
        print(f"  {c}")

    if signal == Signal.NOGO:
        print(f"\n  >>> 结论: 不开仓。以上红色项不满足。")
        return None
    elif signal == Signal.WARN:
        print(f"\n  >>> 结论: 警示。黄色项需人工确认后方可开仓。")

    # 第二层
    if entry_price > 0 and signal != Signal.NOGO:
        print(f"\n── 第二层：执行层 ──")
        plan = engine.create_trade_plan(stock_code, stock_name or f"股票{stock_code}",
                                        entry_price)
        print(plan.summary())

        # 模拟持仓检查时间线
        print(f"── 持仓时间线模拟 ──")
        for day, price_pct, scenario in [
            (1, +3.0, "快速盈利"),
            (3, -1.5, "危险区微亏"),
            (3, +2.5, "危险区微利"),
            (4, +5.5, "启动移动止损后回撤"),
            (7, -7.5, "硬止损触发"),
        ]:
            sim_price = entry_price * (1 + price_pct / 100)
            state, msg = engine.check_position(plan, sim_price, day, price_pct)
            flag = "✓" if state == PositionState.ACTIVE else "✗"
            print(f"  第{day}天 {price_pct:+.1f}% @{sim_price:.2f} → [{state.value}] {msg}")
        return plan

    return None


def daily_status(portfolio_value: float = 240000):
    """每日开盘前打印市场状态"""
    engine = TradeEngine(portfolio_value)
    today = datetime.now().strftime("%Y-%m-%d")
    mkt = engine.calendar.get(today, {})

    print(f"\n{'='*40}")
    print(f"每日市场状态 — {today}")
    print(f"{'='*40}")
    print(f"  大盘趋势: {mkt.get('trend', '无数据')}")
    print(f"  量能状态: {mkt.get('volume_state', '无数据')}")
    print(f"  市场情绪: {mkt.get('sentiment', '无数据')}")
    print(f"  昨日涨跌: {mkt.get('pct_chg', 0):+.2f}%")

    vol = mkt.get('volume_state', '')
    trend = mkt.get('trend', '')
    sent = mkt.get('sentiment', '')

    print(f"\n  今日交易建议:")
    if vol == "缩量":
        print(f"    ⛔ 缩量日 — 建议不主动开新仓")
    elif vol == "放量":
        print(f"    ✅ 放量日 — 可积极寻找机会")
    else:
        print(f"    ✅ 量能正常 — 可正常交易")

    if trend == "空头排列":
        print(f"    ⛔ 空头排列 — 只做超短(0-2天), 不恋战")
    elif trend == "多头排列":
        print(f"    ✅ 多头排列 — 可适当延长持仓")

    if sent == "恐慌":
        print(f"    ⛔ 恐慌日 — 只卖不买")
    elif sent == "弱势":
        print(f"    ⚠ 弱势 — 仓位减半")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "status":
            daily_status()
        elif cmd == "check" and len(sys.argv) >= 3:
            code = sys.argv[2]
            name = sys.argv[3] if len(sys.argv) > 3 else ""
            price = float(sys.argv[4]) if len(sys.argv) > 4 else 0
            pre_trade_checklist(code, name, price)
        else:
            print("用法: python trade_engine.py status|check <code> [name] [price]")
    else:
        daily_status()
        print("\n试试: python trade_engine.py check 002156 通富微电 49.79")
