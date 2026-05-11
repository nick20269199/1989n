"""
Stock monitor for 深圳华强 (000062).

Fetches real-time quote data, performs technical analysis, checks
alert conditions, and pushes results to both local JSON and Feishu.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from bridge_sender import broadcast_alert
from config import STOCK_DATA_DIR, HEADERS

logger = logging.getLogger("monitor_000062")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CODE = "000062"
NAME = "深圳华强"
MONITOR_FILE = STOCK_DATA_DIR / "monitor_000062.json"

# Data URLs
_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/mkline"
_SINA_URL = "https://hq.sinajs.cn/list="

# Technical analysis parameters
MA_PERIODS = [5, 10, 20, 60]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
VOLUME_AVG_DAYS = 20

# Alert thresholds
VOLUME_SURGE_MULT = 2.0
RSI_OVERBOUGHT = 80
RSI_OVERSOLD = 20
STOP_LOSS_PCT = 0.03   # 3% proximity to stop loss


# ---------------------------------------------------------------------------
# Data fetching
# ---------------------------------------------------------------------------

def fetch_000062_data() -> dict:
    """
    Fetch real-time quote, daily K-line, and latest news for 000062.

    Returns a dict with keys: quote, kline, news, fetch_time.
    """
    result: dict[str, Any] = {"code": CODE, "name": NAME, "fetch_time": datetime.now().isoformat()}

    # --- Real-time quote (Sina) ---
    try:
        resp = requests.get(f"{_SINA_URL}sz{CODE}", headers=HEADERS, timeout=10)
        resp.encoding = "gb2312"
        text = resp.text
        # Format: var hq_str_sz000062="name,open,yesterday_close,price,high,low,...,date,time,...";
        if "=" in text:
            fields = text.split('"')[1].split(",")
            if len(fields) >= 32:
                result["quote"] = {
                    "name": fields[0],
                    "open": _safe_float(fields[1]),
                    "yesterday_close": _safe_float(fields[2]),
                    "price": _safe_float(fields[3]),
                    "high": _safe_float(fields[4]),
                    "low": _safe_float(fields[5]),
                    "volume": _safe_float(fields[8]),
                    "amount": _safe_float(fields[9]),
                    "date": fields[30],
                    "time": fields[31],
                }
                price = result["quote"]["price"]
                prev_close = result["quote"]["yesterday_close"]
                if price and prev_close and prev_close > 0:
                    result["quote"]["change_pct"] = round((price - prev_close) / prev_close * 100, 2)
                else:
                    result["quote"]["change_pct"] = 0.0
    except Exception:
        logger.warning("Sina quote fetch failed", exc_info=True)

    # --- Daily K-line (Tencent) ---
    try:
        resp = requests.get(
            f"{_KLINE_URL}?param=sz{CODE},day,,,60,qfq",
            headers=HEADERS,
            timeout=10,
        )
        kline_data = resp.json()
        days = kline_data.get("data", {}).get("sz000062", {}).get("day", [])
        if days:
            result["kline"] = []
            for d in days[-MA_PERIODS[-1] * 2:]:  # enough for MAs + volume avg
                result["kline"].append({
                    "date": d[0],
                    "open": _safe_float(d[1]),
                    "close": _safe_float(d[2]),
                    "high": _safe_float(d[3]),
                    "low": _safe_float(d[4]),
                    "volume": _safe_float(d[5]),
                })
    except Exception:
        logger.warning("Tencent K-line fetch failed", exc_info=True)

    # --- News (Eastmoney brief) ---
    try:
        resp = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "secid": f"0.{CODE}",
                "fields": "f12,f14,f31,f32,f33,f34,f35,f36,f37,f38,f39,f40,f41",
                "np": "3",
                "fltt": "2",
            },
            headers=HEADERS,
            timeout=10,
        )
        # The basic quote API doesn't return news; try the news API instead
        news_resp = requests.get(
            "https://push2.eastmoney.com/api/qt/stock/get",
            params={
                "secid": f"0.{CODE}",
                "fields": "f271,f272,f273,f274",
            },
            headers=HEADERS,
            timeout=10,
        )
        if news_resp.ok:
            news_json = news_resp.json()
            raw_news = news_json.get("data", {})
            if raw_news:
                result["news"] = raw_news
    except Exception:
        logger.warning("News fetch failed", exc_info=True)

    return result


# ---------------------------------------------------------------------------
# Technical analysis
# ---------------------------------------------------------------------------

def analyze_000062(data: dict) -> dict:
    """
    Run technical analysis on 000062 data.

    Returns a dict with: ma_alignment, rsi, macd_signal, volume_status,
    support, resistance, ma_values.
    """
    technical: dict[str, Any] = {}

    kline = data.get("kline", [])
    if not kline or len(kline) < MA_PERIODS[-1]:
        technical["ma_alignment"] = "数据不足"
        return technical

    closes = [d["close"] for d in kline if d.get("close")]
    volumes = [d["volume"] for d in kline if d.get("volume")]

    # --- Moving Averages ---
    ma_values: dict[str, float] = {}
    for period in MA_PERIODS:
        if len(closes) >= period:
            ma = sum(closes[-period:]) / period
            ma_values[f"MA{period}"] = round(ma, 2)
    technical["ma_values"] = ma_values

    # MA alignment
    if len(ma_values) >= 4:
        ma5, ma10, ma20, ma60 = (ma_values.get(f"MA{p}") for p in [5, 10, 20, 60])
        if ma5 and ma10 and ma20 and ma60:
            if ma5 > ma10 > ma20 > ma60:
                technical["ma_alignment"] = "多头排列"
            elif ma5 < ma10 < ma20 < ma60:
                technical["ma_alignment"] = "空头排列"
            elif ma5 > ma10 > ma20:
                technical["ma_alignment"] = "短期多头"
            elif ma5 < ma10 < ma20:
                technical["ma_alignment"] = "短期空头"
            else:
                technical["ma_alignment"] = "均线交叉/缠绕"
        else:
            technical["ma_alignment"] = "均线数据不完整"
    else:
        technical["ma_alignment"] = "均线数据不足"

    # --- RSI (14) ---
    if len(closes) >= RSI_PERIOD + 1:
        gains = []
        losses = []
        for i in range(len(closes) - RSI_PERIOD, len(closes)):
            delta = closes[i] - closes[i - 1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
        avg_gain = sum(gains) / RSI_PERIOD
        avg_loss = sum(losses) / RSI_PERIOD
        if avg_loss == 0:
            rsi = 100.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        technical["rsi"] = round(rsi, 1)
    else:
        technical["rsi"] = None

    # --- MACD ---
    if len(closes) >= MACD_SLOW + MACD_SIGNAL:
        ema_fast = _ema(closes, MACD_FAST)
        ema_slow = _ema(closes, MACD_SLOW)
        diffs = [f - s for f, s in zip(ema_fast, ema_slow)]
        # Align diffs to match the shorter EMA
        offset = MACD_SLOW - MACD_FAST
        diffs_aligned = diffs[offset:]
        dea = _ema(diffs_aligned, MACD_SIGNAL)
        # histogram values
        macd_hist = [d - e for d, e in zip(diffs_aligned[-len(dea):], dea)]

        if len(macd_hist) >= 2:
            if macd_hist[-2] <= 0 and macd_hist[-1] > 0:
                technical["macd_signal"] = "金叉(看涨)"
            elif macd_hist[-2] >= 0 and macd_hist[-1] < 0:
                technical["macd_signal"] = "死叉(看跌)"
            elif macd_hist[-1] > 0:
                technical["macd_signal"] = "MACD红柱(多头)"
            else:
                technical["macd_signal"] = "MACD绿柱(空头)"

            technical["macd_hist"] = round(macd_hist[-1], 4)
            technical["dif"] = round(diffs_aligned[-1], 4)
            technical["dea"] = round(dea[-1], 4)
        else:
            technical["macd_signal"] = "数据不足"
    else:
        technical["macd_signal"] = "数据不足"

    # --- Volume status ---
    if len(volumes) >= VOLUME_AVG_DAYS + 1:
        avg_vol = sum(volumes[-VOLUME_AVG_DAYS - 1:-1]) / VOLUME_AVG_DAYS
        current_vol = volumes[-1]
        if avg_vol > 0:
            vol_ratio = current_vol / avg_vol
            technical["volume_ratio"] = round(vol_ratio, 2)
            if vol_ratio >= 2.0:
                technical["volume_status"] = "巨量(>2倍均量)"
            elif vol_ratio >= 1.5:
                technical["volume_status"] = "放量(1.5-2倍)"
            elif vol_ratio >= 0.8:
                technical["volume_status"] = "正常"
            else:
                technical["volume_status"] = "缩量(<0.8倍)"
        else:
            technical["volume_status"] = "均量异常"
    else:
        technical["volume_status"] = "数据不足"

    # --- Support / Resistance (simple: recent high/low) ---
    if len(closes) >= 20:
        recent_20_high = max(closes[-20:])
        recent_20_low = min(closes[-20:])
        current = closes[-1]
        technical["resistance"] = round(recent_20_high, 2)
        technical["support"] = round(recent_20_low, 2)
        technical["position_in_range"] = round(
            (current - recent_20_low) / (recent_20_high - recent_20_low) * 100, 1
        ) if recent_20_high != recent_20_low else 50.0

    return technical


# ---------------------------------------------------------------------------
# Alert checking
# ---------------------------------------------------------------------------

def check_alerts(data: dict) -> list[dict]:
    """
    Scan data for alert conditions and return a list of alert dicts.

    Each alert has: type, severity, message, reason.
    """
    alerts: list[dict] = []
    quote = data.get("quote", {})
    technical = data.get("technical", {})
    ma_values = technical.get("ma_values", {})

    price = quote.get("price", 0.0)
    if not price:
        return alerts

    # 1. Price break through MA20 / MA60
    ma20 = ma_values.get("MA20")
    ma60 = ma_values.get("MA60")
    if ma20 and price > ma20:
        prev_close = quote.get("yesterday_close", price)
        # Check if crossed above today (open below, now above)
        if prev_close and prev_close <= ma20:
            alerts.append({
                "type": "price_break",
                "severity": "high",
                "message": f"价格突破 MA20 (¥{ma20})",
                "reason": f"当前价 ¥{price} > MA20 ¥{ma20}",
            })
    if ma60 and price > ma60:
        prev_close = quote.get("yesterday_close", price)
        if prev_close and prev_close <= ma60:
            alerts.append({
                "type": "price_break",
                "severity": "medium",
                "message": f"价格突破 MA60 (¥{ma60})",
                "reason": f"当前价 ¥{price} > MA60 ¥{ma60}",
            })

    # 2. Volume surge
    vol_ratio = technical.get("volume_ratio", 1.0)
    if vol_ratio >= VOLUME_SURGE_MULT:
        alerts.append({
            "type": "volume_surge",
            "severity": "high",
            "message": f"成交量暴增至均量 {vol_ratio:.1f}x",
            "reason": f"量比 {vol_ratio:.1f} >= {VOLUME_SURGE_MULT}倍",
        })

    # 3. RSI extremes
    rsi = technical.get("rsi")
    if rsi is not None:
        if rsi >= RSI_OVERBOUGHT:
            alerts.append({
                "type": "technical",
                "severity": "medium",
                "message": f"RSI 超买 ({rsi})",
                "reason": f"RSI {rsi} >= {RSI_OVERBOUGHT}，短期回调风险",
            })
        elif rsi <= RSI_OVERSOLD:
            alerts.append({
                "type": "technical",
                "severity": "medium",
                "message": f"RSI 超卖 ({rsi})",
                "reason": f"RSI {rsi} <= {RSI_OVERSOLD}，短期反弹可能性",
            })

    # 4. MACD cross
    macd_signal = technical.get("macd_signal", "")
    if "金叉" in macd_signal:
        alerts.append({
            "type": "technical",
            "severity": "high",
            "message": "MACD 金叉信号",
            "reason": "DIF 上穿 DEA，看涨信号",
        })
    elif "死叉" in macd_signal:
        alerts.append({
            "type": "technical",
            "severity": "high",
            "message": "MACD 死叉信号",
            "reason": "DIF 下穿 DEA，看跌信号",
        })

    # 5. Stop-loss proximity (use MA60 as proxy if no cost basis)
    support = technical.get("support", price)
    if support > 0:
        distance_pct = (price - support) / support * 100
        if distance_pct < STOP_LOSS_PCT * 100:
            alerts.append({
                "type": "risk",
                "severity": "critical",
                "message": f"接近止损位 (距支撑仅 {distance_pct:.1f}%)",
                "reason": f"当前价 ¥{price} 距20日低点 ¥{support} 仅 {distance_pct:.1f}%",
            })

    return alerts


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_report(data: dict, alerts: list[dict]) -> str:
    """Build a human-readable monitoring report string."""
    quote = data.get("quote", {})
    technical = data.get("technical", {})
    fetch_time = data.get("fetch_time", "")

    price = quote.get("price", "N/A")
    change_pct = quote.get("change_pct", 0.0)
    direction = "+" if change_pct >= 0 else ""
    high = quote.get("high", "N/A")
    low = quote.get("low", "N/A")
    volume = quote.get("volume", "N/A")
    amount = quote.get("amount", "N/A")

    lines = [
        f"## {NAME} ({CODE}) 监测报告",
        "",
        f"**价格**: ¥{price}  |  涨跌幅: {direction}{change_pct}%",
        f"**最高**: ¥{high}  |  最低: ¥{low}",
        f"**成交量**: {volume}手  |  成交额: {amount}元",
        "",
        "### 技术指标",
        f"- 均线排列: **{technical.get('ma_alignment', 'N/A')}**",
    ]

    ma_values = technical.get("ma_values", {})
    if ma_values:
        ma_str = "  |  ".join(f"MA{p}: ¥{v}" for p, v in ma_values.items())
        lines.append(f"- {ma_str}")

    rsi = technical.get("rsi")
    lines.append(f"- RSI(14): {rsi if rsi is not None else 'N/A'}")
    lines.append(f"- MACD: {technical.get('macd_signal', 'N/A')}")
    lines.append(f"- 量能: {technical.get('volume_status', 'N/A')}")

    if "support" in technical and "resistance" in technical:
        lines.append(
            f"- 支撑: ¥{technical['support']}  |  "
            f"阻力: ¥{technical['resistance']}  |  "
            f"位置: {technical.get('position_in_range', 'N/A')}%"
        )

    # Alerts section
    if alerts:
        lines.append("")
        lines.append("### 告警")
        for a in alerts:
            severity_icon = {"critical": "!!", "high": "!", "medium": "-", "low": "."}
            icon = severity_icon.get(a.get("severity", "medium"), "-")
            lines.append(f"- [{a['type']}] {icon} {a['message']}")
    else:
        lines.append("")
        lines.append("### 告警: 无")

    lines.append("")
    lines.append(f"*报告生成: {fetch_time}*")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_float(value: Any) -> float | None:
    """Convert to float, returning None on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ema(data: list[float], period: int) -> list[float]:
    """Compute Exponential Moving Average for a series."""
    if len(data) < period:
        return []
    multiplier = 2.0 / (period + 1)
    ema_values = [sum(data[:period]) / period]  # SMA as seed
    for price in data[period:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
    return ema_values


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Fetch data, analyse, check alerts, save JSON, and push to Feishu."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(f"开始监测 {NAME} ({CODE}) ...")

    # 1. Fetch
    data = fetch_000062_data()
    if not data.get("quote"):
        logger.error("无法获取行情数据，监测中止")
        sys.exit(1)

    # 2. Analyse
    technical = analyze_000062(data)
    data["technical"] = technical

    logger.info(
        f"价格: ¥{data['quote']['price']} "
        f"({data['quote']['change_pct']:+.2f}%)  |  "
        f"均线: {technical.get('ma_alignment')}"
    )

    # 3. Check alerts
    alerts = check_alerts(data)
    data["alerts"] = alerts
    logger.info(f"告警: {len(alerts)} 条")

    for a in alerts:
        logger.warning(f"[{a['severity'].upper()}] {a['type']}: {a['message']}")

    # 4. Save to local JSON
    Path(STOCK_DATA_DIR).mkdir(parents=True, exist_ok=True)
    with open(MONITOR_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    logger.info(f"监测数据已保存: {MONITOR_FILE}")

    # 5. Generate and output report
    report = generate_report(data, alerts)
    print("\n" + report)

    # 6. Send Feishu alert for high+ severity
    for a in alerts:
        if a.get("severity") in ("high", "critical"):
            broadcast_alert(
                alert_type=a["type"],
                message=f"{NAME}({CODE}) {a['message']}\n\n{a.get('reason', '')}",
            )


if __name__ == "__main__":
    main()
