"""
data_quality_gate.py — 发送前数据质量校验

所有飞书报告在发送前必须经过此关卡。
数据质量不达标 → 不发送报告 → 改发简短告警。
"""
import logging
from datetime import datetime, date
from pathlib import Path
from typing import Optional

logger = logging.getLogger("data_quality_gate")

PROJECT_DIR = Path(__file__).parent
PORTFOLIO_FILE = PROJECT_DIR / "data" / "portfolio.json"
CLAUDE_MD = PROJECT_DIR.parent / "CLAUDE.md"

# 阈值配置
MIN_PRICE_VALID_RATIO = 0.6   # 至少 60% 的持仓有有效行情才发送
MAX_ALLOWABLE_STALE_DAYS = 3  # portfolio.json 超过3天未更新 → 告警但不阻止


def check_report_quality(
    report_name: str,
    holdings_data: list[dict],
) -> dict:
    """发送前数据质量校验。

    Args:
        report_name: 报告名称（用于日志）
        holdings_data: 即将发送的持仓数据列表（每项含 code, name, price, pnl_pct 等）

    Returns:
        {"pass": True/False, "should_send": True/False, "reasons": [str]}
        - pass: 数据质量是否合格
        - should_send: 是否应该发送（True=发报告, False=发告警替代）
        - reasons: 质量问题的具体描述
    """
    reasons = []

    # ── 检查 1: portfolio.json 时效性 ──
    portfolio_stale_days = _check_portfolio_freshness()
    if portfolio_stale_days is not None and portfolio_stale_days > MAX_ALLOWABLE_STALE_DAYS:
        reasons.append(
            f"portfolio.json 已 {portfolio_stale_days} 天未更新"
        )

    # ── 检查 2: 价格数据完整性 ──
    total = len(holdings_data)
    valid = sum(1 for h in holdings_data if h.get("pnl_pct") is not None)
    invalid = total - valid
    ratio = valid / total if total > 0 else 0

    if invalid > 0:
        names = [
            h.get("name", h.get("code", "?"))
            for h in holdings_data if h.get("pnl_pct") is None
        ]
        reasons.append(f"{invalid}/{total} 只持仓无行情数据: {', '.join(names)}")

    if total > 0 and ratio < MIN_PRICE_VALID_RATIO:
        # 严重: 大部分数据缺失 → 不发送报告
        logger.warning(
            "[%s] 数据质量 FAIL: 有效行情 %.0f%% (%d/%d), 低于阈值 %.0f%%",
            report_name, ratio * 100, valid, total, MIN_PRICE_VALID_RATIO * 100,
        )
        return {
            "pass": False,
            "should_send": False,
            "reasons": reasons + [
                f"有效行情仅 {valid}/{total} 只 ({ratio:.0%}), "
                f"低于最低要求 {MIN_PRICE_VALID_RATIO:.0%}, 跳过本次报告"
            ],
        }

    # ── 检查 3: 数据合理性 — pnl_pct 不应全部为 0.0 ──
    if total > 0:
        all_zero_pnl = all(
            h.get("pnl_pct") == 0 for h in holdings_data if h.get("pnl_pct") is not None
        )
        if all_zero_pnl:
            reasons.append("所有持仓盈亏均为 0.0%, 疑似行情源异常")

    # ── 结果 ──
    if reasons:
        logger.info("[%s] 数据质量 OK (有注意事项): %s", report_name, "; ".join(reasons))
        return {"pass": True, "should_send": True, "reasons": reasons}

    logger.info("[%s] 数据质量 OK", report_name)
    return {"pass": True, "should_send": True, "reasons": []}


def _check_portfolio_freshness() -> Optional[int]:
    """检查 portfolio.json 的最后更新距今多少天。"""
    if not PORTFOLIO_FILE.exists():
        return None
    try:
        import json
        data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        updated = data.get("updated", "")
        if not updated:
            return None
        updated_date = datetime.strptime(updated, "%Y-%m-%d").date()
        delta = (date.today() - updated_date).days
        return delta
    except Exception:
        return None
