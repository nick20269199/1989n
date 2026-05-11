"""
Desktop automation for stock monitoring popups.

Runs a background monitoring loop that:
  - Checks market open/closed status
  - Polls portfolio prices periodically
  - Shows Windows toast notifications on big moves
  - Monitors Shanghai/Shenzhen index movements
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

from config import STOCK_DATA_DIR, HEADERS

logger = logging.getLogger("desktop_auto")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POLL_INTERVAL_SECONDS = 60
BIG_MOVE_THRESHOLD = 3.0       # % move that triggers alert
INDEX_CHECK_URL = "https://hq.sinajs.cn/list=s_sh000001,s_sz399001"
PORTFOLIO_FILE = STOCK_DATA_DIR / "portfolio.json"

# Log file
_LOG_DIR = STOCK_DATA_DIR / "desktop_logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

# Market hours in 24h Beijing time
_MARKET_OPEN = (9, 30)
_MARKET_CLOSE = (15, 0)
_PRE_MARKET_OPEN = (9, 15)

# Windows toast availability
_TOAST_AVAILABLE = False
try:
    from win10toast import ToastNotifier  # type: ignore[import-untyped]

    _toaster = ToastNotifier()
    _TOAST_AVAILABLE = True
except ImportError:
    _toaster = None  # type: ignore[assignment]
    logger.info("win10toast 未安装，将使用控制台输出代替弹窗")


# ---------------------------------------------------------------------------
# Market status
# ---------------------------------------------------------------------------

def check_market_status() -> str:
    """
    Determine current market status based on Beijing time.

    Returns one of: "open", "closed", "pre-market", "after-hours",
    "weekend", "holiday" (holiday detection is basic).
    """
    now = datetime.now()
    weekday = now.weekday()  # 0=Mon, 6=Sun

    # Weekends
    if weekday >= 5:
        return "weekend"

    hour, minute = now.hour, now.minute

    # Pre-market
    if hour == _PRE_MARKET_OPEN[0] and minute >= _PRE_MARKET_OPEN[1]:
        return "pre-market"
    if hour == _MARKET_OPEN[0] and minute < _MARKET_OPEN[1]:
        return "pre-market"

    # Open
    if hour == _MARKET_OPEN[0] and minute >= _MARKET_OPEN[1]:
        return "open"
    if _MARKET_OPEN[0] < hour < _MARKET_CLOSE[0]:
        return "open"
    if hour == _MARKET_CLOSE[0] and minute <= _MARKET_CLOSE[1]:
        return "open"

    # After hours
    if hour == _MARKET_CLOSE[0] and minute > _MARKET_CLOSE[1]:
        return "after-hours"
    if _MARKET_CLOSE[0] < hour < 24:
        return "after-hours"

    # Overnight / early morning
    return "closed"


def _is_market_active() -> bool:
    """True when the market is open for trading."""
    return check_market_status() == "open"


# ---------------------------------------------------------------------------
# Windows toast notification
# ---------------------------------------------------------------------------

def show_popup(title: str, message: str) -> None:
    """
    Show a Windows toast notification.

    Falls back to console print if win10toast is not installed.
    """
    if _TOAST_AVAILABLE and _toaster is not None:
        try:
            _toaster.show_toast(
                title,
                message,
                duration=8,
                threaded=True,
            )
            logger.info(f"弹窗: {title}")
        except Exception:
            logger.debug("Toast 发送异常", exc_info=True)
            print(f"\n[弹窗] {title}\n{message}\n")
    else:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{ts}] [弹窗] {title}\n{message}\n")


# ---------------------------------------------------------------------------
# Portfolio monitoring
# ---------------------------------------------------------------------------

def monitor_portfolio_prices() -> list[dict]:
    """
    Fetch current prices for all portfolio stocks and return any
    that have moved more than BIG_MOVE_THRESHOLD %.
    """
    alerts: list[dict] = []

    # Load portfolio
    stocks = _load_portfolio()
    if not stocks:
        return alerts

    codes = [s["code"] for s in stocks if s.get("code")]
    if not codes:
        return alerts

    # Build Sina query string
    sina_codes = []
    for c in codes:
        prefix = "sh" if c.startswith(("6", "9")) else "sz"
        sina_codes.append(f"{prefix}{c}")

    try:
        url = f"{INDEX_CHECK_URL},{','.join(sina_codes)}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.encoding = "gb2312"
        lines = resp.text.strip().split("\n")
    except Exception:
        logger.error("获取行情失败", exc_info=True)
        return alerts

    for line in lines:
        if "=" not in line:
            continue
        try:
            raw = line.split('"')[1]
        except IndexError:
            continue
        fields = raw.split(",")
        if len(fields) < 4:
            continue

        name = fields[0]
        price = _safe_float(fields[3])
        prev_close = _safe_float(fields[2])
        if price is None or prev_close is None or prev_close == 0:
            continue

        change_pct = (price - prev_close) / prev_close * 100
        if abs(change_pct) >= BIG_MOVE_THRESHOLD:
            direction = "涨" if change_pct >= 0 else "跌"
            alerts.append({
                "code": line.split("_")[-1].split("=")[0].replace("sz", "").replace("sh", ""),
                "name": name,
                "price": price,
                "change_pct": round(change_pct, 2),
                "message": f"{name} {direction}{abs(change_pct):.2f}%（¥{price:.2f}）",
            })

    return alerts


# ---------------------------------------------------------------------------
# Index monitoring
# ---------------------------------------------------------------------------

def monitor_index() -> dict | None:
    """
    Fetch Shanghai Composite (sh000001) and Shenzhen Component (sz399001).

    Returns a dict with sh_index, sz_index, and their change_pct, or None
    on failure.
    """
    try:
        resp = requests.get(INDEX_CHECK_URL, headers=HEADERS, timeout=10)
        resp.encoding = "gb2312"
        lines = resp.text.strip().split("\n")
    except Exception:
        logger.error("指数获取失败", exc_info=True)
        return None

    result: dict[str, Any] = {}
    for line in lines:
        if "=" not in line:
            continue
        try:
            raw = line.split('"')[1]
        except IndexError:
            continue
        fields = raw.split(",")
        if len(fields) < 4:
            continue

        name = fields[0]
        price = _safe_float(fields[3])
        prev_close = _safe_float(fields[2])

        if price is not None and prev_close is not None and prev_close > 0:
            change_pct = (price - prev_close) / prev_close * 100
            if "上证" in name or "000001" in line:
                result["sh_name"] = name
                result["sh_index"] = round(price, 2)
                result["sh_change_pct"] = round(change_pct, 2)
            elif "深证" in name or "399001" in line:
                result["sz_name"] = name
                result["sz_index"] = round(price, 2)
                result["sz_change_pct"] = round(change_pct, 2)

    return result if result else None


# ---------------------------------------------------------------------------
# Main monitoring loop
# ---------------------------------------------------------------------------

_should_run = True


def start_monitoring() -> None:
    """
    Start the desktop monitoring loop.

    Checks market status every POLL_INTERVAL_SECONDS during active
    hours.  Pushes desktop popups for significant portfolio moves
    and saves status JSON to STOCK_DATA_DIR.
    """
    global _should_run
    _should_run = True

    logger.info("=" * 50)
    logger.info("桌面自动监测启动")
    logger.info(f"轮询间隔: {POLL_INTERVAL_SECONDS}s")
    logger.info(f"异动阈值: ±{BIG_MOVE_THRESHOLD}%")
    logger.info("=" * 50)

    show_popup("股票监测已启动", f"轮询间隔 {POLL_INTERVAL_SECONDS}s | 异动阈值 {BIG_MOVE_THRESHOLD}%")

    iteration = 0

    while _should_run:
        try:
            iteration += 1
            status = check_market_status()
            now = datetime.now().strftime("%H:%M:%S")

            logger.info(f"[#{iteration}] {now} 市场状态: {status}")

            if status == "open":
                # Check indices
                idx = monitor_index()
                if idx:
                    logger.info(
                        f"指数: {idx.get('sh_name', '沪')} "
                        f"{idx.get('sh_index')} ({idx.get('sh_change_pct'):+.2f}%)  |  "
                        f"{idx.get('sz_name', '深')} "
                        f"{idx.get('sz_index')} ({idx.get('sz_change_pct'):+.2f}%)"
                    )

                # Check portfolio
                alerts = monitor_portfolio_prices()
                for a in alerts:
                    logger.warning(f"异动: {a['message']}")
                    show_popup(
                        title=f"股价异动 - {a['name']}",
                        message=a["message"],
                    )

                # Save status
                status_data = {
                    "time": datetime.now().isoformat(),
                    "market_status": status,
                    "index": idx,
                    "alerts": alerts,
                }
                _save_status(status_data)

            elif status == "pre-market":
                logger.info("盘前等待中...")

            elif status in ("after-hours", "weekend", "closed"):
                logger.info(f"非交易时段 ({status})，进入低频率等待")
                # Save an idle status entry
                _save_status({
                    "time": datetime.now().isoformat(),
                    "market_status": status,
                })
                # Sleep longer when market is closed
                time.sleep(_next_poll_seconds(status))
                continue

            time.sleep(POLL_INTERVAL_SECONDS)

        except KeyboardInterrupt:
            logger.info("收到中断信号，正在退出...")
            break
        except Exception:
            logger.error(f"监测循环异常:\n{traceback.format_exc()}")
            time.sleep(30)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_portfolio() -> list[dict]:
    """Load portfolio from JSON file or config."""
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.warning("portfolio.json 读取失败", exc_info=True)

    # Fallback: hardcoded portfolio from config constants
    return [
        {"code": "000062", "name": "深圳华强"},
        {"code": "002384", "name": "东山精密"},
        {"code": "300115", "name": "长盈精密"},
        {"code": "002402", "name": "和而泰"},
        {"code": "002463", "name": "沪电股份"},
        {"code": "002709", "name": "天赐材料"},
        {"code": "003031", "name": "中瓷电子"},
    ]


def _save_status(data: dict[str, Any]) -> None:
    """Append a status line to the daily log file."""
    today = datetime.now().strftime("%Y%m%d")
    log_path = _LOG_DIR / f"desktop_{today}.jsonl"
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(data, ensure_ascii=False, default=str) + "\n")
    except Exception:
        logger.warning("状态写入失败", exc_info=True)


def _next_poll_seconds(status: str) -> int:
    """Return a longer poll interval when market is inactive."""
    if status == "after-hours":
        return 300   # 5 min
    if status == "weekend":
        return 3600  # 1 hour
    return 600       # 10 min default


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        start_monitoring()
    except KeyboardInterrupt:
        logger.info("用户中断，退出")
    except Exception:
        logger.critical(f"致命错误:\n{traceback.format_exc()}")
        sys.exit(1)
