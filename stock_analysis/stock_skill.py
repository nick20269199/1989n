"""
Stock Analysis Skill -- technical indicators, VCP pattern detection,
watchlist scanning, and comprehensive holdings analysis.

Data sources: Sina K-line (primary), Tencent K-line (fallback), Sina real-time quotes (primary), Eastmoney quotes (fallback).
All indicators are calculated from raw price data -- never from API pre-computed values.
"""

import json
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
import urllib3

from config import (
    STOCK_DATA_DIR,
    HEADERS,
    TENCENT_KLINE_URL,
    SINA_QUOTE_URL,
    EASTMONEY_QUOTE_URL,
    VCP_MIN_TIGHTENING_DAYS,
    MA_PERIODS,
    RSI_PERIOD,
    MACD_FAST,
    MACD_SLOW,
    MACD_SIGNAL,
)
from database import get_portfolio, save_market_data, get_market_history

urllib3.disable_warnings()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default watchlist -- tech, semiconductor, AI supply chain, lithium, benchmark
# ---------------------------------------------------------------------------
DEFAULT_WATCHLIST: list[str] = [
    "002230",  # 科大讯飞
    "300750",  # 宁德时代
    "300124",  # 汇川技术
    "002415",  # 海康威视
    "688981",  # 中芯国际
    "688256",  # 寒武纪
    "300474",  # 景嘉微
    "688012",  # 中微公司
    "300604",  # 长川科技
    "688111",  # 金山办公
    "002371",  # 北方华创
    "300502",  # 新易盛
    "688313",  # 仕佳光子
    "002916",  # 深南电路
    "300661",  # 圣邦股份
    "688008",  # 澜起科技
    "002049",  # 紫光国微
    "300782",  # 卓胜微
    "000977",  # 浪潮信息
    "603501",  # 韦尔股份
    "300308",  # 中际旭创
    "002475",  # 立讯精密
    "601012",  # 隆基绿能
    "600519",  # 贵州茅台
    "000858",  # 五粮液
    "300274",  # 阳光电源
    "603986",  # 兆易创新
    "002709",  # 天赐材料
]

# ---------------------------------------------------------------------------
# Market helpers
# ---------------------------------------------------------------------------


def _market_prefix(code: str) -> str:
    """Determine market prefix: sh for 60xxxx/68xxxx, sz for 00xxxx/30xxxx, bj for others."""
    if code.startswith(("60", "68")):
        return "sh"
    elif code.startswith(("00", "30")):
        return "sz"
    elif code.startswith(("83", "87", "43")):
        return "bj"
    return "sz"


def _eastmoney_market(code: str) -> str:
    """Eastmoney market code: 1=SH, 0=SZ."""
    return "1" if code.startswith(("60", "68")) else "0"


# ---------------------------------------------------------------------------
# API layer with rate limiting (exponential backoff)
# ---------------------------------------------------------------------------


def _fetch_with_retry(
    url: str,
    params: dict | None = None,
    headers: dict | None = None,
    max_retries: int = 3,
    timeout: int = 15,
    verify: bool = True,
) -> requests.Response:
    """GET request with exponential backoff on transient failures."""
    if headers is None:
        headers = HEADERS.copy()
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout, verify=verify)
            resp.raise_for_status()
            return resp
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else 0
            if status == 429:
                wait = min(2 ** attempt * 2.0, 30.0)
                logger.warning("Rate limited (%s), retrying in %.1fs (attempt %d/%d)",
                               url[:80], wait, attempt + 1, max_retries)
                time.sleep(wait)
                continue
            if 500 <= status < 600:
                wait = min(2 ** attempt, 10.0)
                logger.warning("Server error %d for %s, retrying in %.1fs",
                               status, url[:80], wait)
                time.sleep(wait)
                continue
            raise
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
            wait = min(2 ** attempt * 1.5, 20.0)
            logger.warning("Network error for %s: %s, retrying in %.1fs",
                           url[:80], e, wait)
            time.sleep(wait)
    raise last_exc or RuntimeError(f"Max retries exceeded for {url}")


# ---------------------------------------------------------------------------
# K-line data -- Sina API (primary) + Tencent (fallback) + Eastmoney (last resort)
# ---------------------------------------------------------------------------

SINA_KLINE_URL = "https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
EASTMONEY_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

# Sina K-line scale mapping: day=240, week=1200, month=7200
_SINA_SCALE_MAP = {"day": "240", "week": "1200", "month": "7200"}


def _get_kline_sina(code: str, period: str, limit: int) -> list[dict] | None:
    """Fetch K-line from Sina finance API. Returns None on failure."""
    prefix = _market_prefix(code)
    scale = _SINA_SCALE_MAP.get(period, "240")
    params = {
        "symbol": f"{prefix}{code}",
        "scale": scale,
        "ma": "no",
        "datalen": limit,
    }
    sina_headers = HEADERS.copy()
    sina_headers["Referer"] = "https://finance.sina.com.cn"
    try:
        resp = _fetch_with_retry(SINA_KLINE_URL, params=params, headers=sina_headers)
        data = resp.json()
        if not isinstance(data, list) or not data:
            logger.warning("Sina K-line returned empty for %s", code)
            return None
        result: list[dict] = []
        for row in data:
            try:
                result.append({
                    "date": row.get("day", ""),
                    "open": float(row.get("open", 0)),
                    "close": float(row.get("close", 0)),
                    "high": float(row.get("high", 0)),
                    "low": float(row.get("low", 0)),
                    "volume": float(row.get("volume", 0)),
                })
            except (ValueError, TypeError):
                continue
        return result if result else None
    except Exception:
        logger.exception("Sina K-line failed for %s", code)
        return None


def _code_to_secid(code: str) -> str:
    """Convert stock code to Eastmoney secid: 600519 -> 1.600519, 000001 -> 0.000001."""
    if code.startswith(("60", "68")):
        return f"1.{code}"
    return f"0.{code}"


def _get_kline_eastmoney(code: str, period: str, limit: int) -> list[dict] | None:
    """Fetch K-line from Eastmoney. Returns None on failure."""
    klt_map = {"day": 101, "week": 102, "month": 103}
    klt = klt_map.get(period, 101)
    secid = _code_to_secid(code)
    params = {
        "secid": secid,
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "klt": klt,
        "fqt": 1,
        "end": "20500101",
        "lmt": limit,
    }
    try:
        resp = _fetch_with_retry(EASTMONEY_KLINE_URL, params=params)
        data = resp.json()
        if data.get("rc") != 0:
            logger.error("Eastmoney K-line error for %s: rc=%s", code, data.get("rc"))
            return None
        raw = data.get("data", {}).get("klines", [])
        if not raw:
            return None
        result: list[dict] = []
        for row in raw:
            fields = row.split(",")
            if len(fields) < 6:
                continue
            result.append({
                "date": fields[0],
                "open": float(fields[1]),
                "close": float(fields[2]),
                "high": float(fields[3]),
                "low": float(fields[4]),
                "volume": float(fields[5]),
            })
        return result
    except Exception:
        logger.exception("Eastmoney K-line failed for %s", code)
        return None


def get_kline_tencent(
    code: str, period: str = "day", limit: int = 120
) -> list[dict]:
    """Fetch K-line data. Sina primary, Tencent fallback, Eastmoney last resort."""
    logger.info("Fetching K-line for %s (period=%s, limit=%d)", code, period, limit)

    # 1. Sina K-line (primary) -- currently the most reliable from China ISPs
    result = _get_kline_sina(code, period, limit)
    if result:
        return result

    # 2. Tencent K-line (fallback) -- SSL cert may not match CDN host, disable verify
    market = _market_prefix(code)
    param = f"{market}{code},{period},,,{limit}"
    url = f"{TENCENT_KLINE_URL}?param={param}"
    try:
        resp = _fetch_with_retry(url, verify=False)
        data = resp.json()
        if data.get("code") != 0:
            return []
        key = f"{market}{code}"
        stock_data = data.get("data", {}).get(key, {})
        raw_rows = stock_data.get(period, [])
        if not raw_rows:
            return []
        result = []
        for row in raw_rows:
            try:
                result.append({
                    "date": str(row[0]),
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": float(row[5]) if len(row) > 5 else 0.0,
                })
            except (IndexError, ValueError, TypeError):
                continue
        return result
    except Exception:
        logger.exception("Tencent K-line fallback failed for %s", code)

    # 3. Eastmoney K-line (last resort) -- often unreachable from some ISPs
    result = _get_kline_eastmoney(code, period, limit)
    if result:
        return result

    return []


# ---------------------------------------------------------------------------
# Real-time quotes -- Sina API (primary) + Eastmoney (fallback)
# ---------------------------------------------------------------------------


_SINA_FIELD_MAP = {
    "name": 0,
    "open": 1,
    "prev_close": 2,
    "price": 3,
    "high": 4,
    "low": 5,
    "volume": 8,
    "amount": 9,
}


def _parse_sina_line(line: str) -> dict | None:
    """Parse a single Sina quote line into a dict."""
    # Format: var hq_str_sh600519="name,open,prev_close,...";
    try:
        header, values_str = line.split("=", 1)
        code_part = header.replace("var hq_str_", "").strip()
        values = values_str.strip().strip('";').split(",")
        if len(values) < 32:
            return None
        price = float(values[3]) if values[3] else 0.0
        prev = float(values[2]) if values[2] else 0.0
        change_pct = ((price - prev) / prev * 100) if prev != 0 else 0.0
        return {
            "code": code_part,
            "name": values[0],
            "price": price,
            "open": float(values[1]) if values[1] else 0.0,
            "high": float(values[4]) if values[4] else 0.0,
            "low": float(values[5]) if values[5] else 0.0,
            "prev_close": prev,
            "change_pct": round(change_pct, 2),
            "volume": float(values[8]) if values[8] else 0.0,
            "amount": float(values[9]) if values[9] else 0.0,
        }
    except (ValueError, IndexError) as e:
        logger.warning("Failed to parse Sina quote line: %s", e)
        return None


def get_realtime_quote_sina(codes: list[str]) -> list[dict]:
    """Fetch real-time quotes from Sina.

    URL: https://hq.sinajs.cn/list=sh600519,sz300739,...
    """
    if not codes:
        return []
    code_list = ",".join(
        f"{_market_prefix(c)}{c}" for c in codes
    )
    url = SINA_QUOTE_URL + code_list
    logger.info("Fetching Sina quotes for %d codes", len(codes))
    headers = HEADERS.copy()
    headers["Referer"] = "https://finance.sina.com.cn"
    resp = _fetch_with_retry(url, headers=headers)
    resp.encoding = "gb2312"
    results: list[dict] = []
    for line in resp.text.strip().split("\n"):
        if not line.strip() or "hq_str_" not in line:
            continue
        parsed = _parse_sina_line(line)
        if parsed:
            results.append(parsed)
    return results


def get_realtime_quote_eastmoney(codes: list[str]) -> list[dict]:
    """Fetch real-time quotes from Eastmoney (fallback).

    URL: https://push2.eastmoney.com/api/qt/stock/get
    """
    if not codes:
        return []
    results: list[dict] = []
    fields = (
        "f43,f44,f45,f46,f47,f48,f50,f51,f52,f55,f57,f58,f60,"
        "f116,f117,f162,f167,f168,f169,f170"
    )
    for code in codes:
        market = _eastmoney_market(code)
        params = {"secid": f"{market}.{code}", "fields": fields}
        logger.debug("Fetching Eastmoney quote for %s", code)
        try:
            resp = _fetch_with_retry(EASTMONEY_QUOTE_URL, params=params)
            raw = resp.json()
            d = raw.get("data", {})
            if not d or d.get("f57") is None:
                logger.warning("Eastmoney returned no data for %s", code)
                continue
            price = d.get("f43", 0) or 0
            prev = d.get("f60", 0) or 0
            results.append({
                "code": code,
                "name": d.get("f58", ""),
                "price": float(price / 100) if isinstance(price, int) and price > 1000 else float(price),
                "open": float((d.get("f46", 0) or 0) / 100) if d.get("f46", 0) and d["f46"] > 1000 else float(d.get("f46", 0) or 0),
                "high": float((d.get("f44", 0) or 0) / 100) if d.get("f44", 0) and d["f44"] > 1000 else float(d.get("f44", 0) or 0),
                "low": float((d.get("f45", 0) or 0) / 100) if d.get("f45", 0) and d["f45"] > 1000 else float(d.get("f45", 0) or 0),
                "prev_close": float(prev / 100) if isinstance(prev, int) and prev > 1000 else float(prev),
                "change_pct": float(d.get("f170", 0) or d.get("f169", 0) or 0),
                "volume": float(d.get("f47", 0) or 0),
                "amount": float(d.get("f48", 0) or 0),
                "pe": float(d.get("f162", 0) or 0),
                "market_cap": float(d.get("f116", 0) or 0),
                "turnover_rate": float(d.get("f168", 0) or 0),
            })
        except Exception as e:
            logger.warning("Eastmoney fetch failed for %s: %s", code, e)
            continue
    return results


# ---------------------------------------------------------------------------
# Technical indicators -- calculated from raw close/volume data
# ---------------------------------------------------------------------------


def calc_ema(data: list[float], period: int) -> list[float]:
    """Exponential Moving Average."""
    if len(data) < period:
        return [sum(data) / len(data)] * len(data) if data else []
    result: list[float] = []
    multiplier = 2.0 / (period + 1)
    seed = sum(data[:period]) / period
    result.append(seed)
    for i in range(period, len(data)):
        result.append((data[i] - result[-1]) * multiplier + result[-1])
    return (result if len(result) == len(data)
            else [result[0]] * (period - 1) + result)


def calc_ma(closes: list[float], period: int) -> list[float]:
    """Simple Moving Average."""
    if not closes or period <= 0:
        return []
    result: list[float] = []
    for i in range(len(closes)):
        if i < period - 1:
            result.append(sum(closes[: i + 1]) / (i + 1))
        else:
            result.append(sum(closes[i - period + 1: i + 1]) / period)
    return result


def calc_rsi(closes: list[float], period: int = RSI_PERIOD) -> float:
    """Relative Strength Index (Wilder's smoothing). Returns latest RSI value."""
    if len(closes) < period + 1:
        return 50.0
    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gains.append(delta if delta > 0 else 0.0)
        losses.append(abs(delta) if delta < 0 else 0.0)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - 100.0 / (1.0 + rs), 2)


def calc_macd(closes: list[float]) -> tuple[float, float, list[float]]:
    """Calculate MACD. Returns (DIF, DEA, histogram) where DIF/DEA are latest
    values and histogram is the full series."""
    ema12_list = calc_ema(closes, MACD_FAST)
    ema26_list = calc_ema(closes, MACD_SLOW)
    dif_list = [e12 - e26 for e12, e26 in zip(ema12_list, ema26_list)]
    dea_list = calc_ema(dif_list, MACD_SIGNAL)
    histogram = [2.0 * (d - e) for d, e in zip(dif_list, dea_list)]
    return (round(dif_list[-1], 4) if dif_list else 0.0,
            round(dea_list[-1], 4) if dea_list else 0.0,
            [round(h, 4) for h in histogram])


# ---------------------------------------------------------------------------
# K-line derived indicators
# ---------------------------------------------------------------------------


def _extract_arrays(kline: list[dict]) -> tuple[list[float], list[float], list[float]]:
    """Extract closes, highs, lows, volumes from kline data."""
    closes = [r["close"] for r in kline]
    highs = [r["high"] for r in kline]
    lows = [r["low"] for r in kline]
    volumes = [r.get("volume", 0) for r in kline]
    return closes, highs, lows, volumes


def _calc_vol_ma(volumes: list[float], period: int = 20) -> float:
    """Average volume over last N days."""
    if not volumes:
        return 0.0
    window = volumes[-period:] if len(volumes) >= period else volumes
    return sum(window) / len(window)


def detect_ma_alignment(kline: list[dict]) -> str:
    """Detect moving-average alignment.

    Returns:
        "多头排列" -- MA5 > MA10 > MA20 > MA60  (bullish)
        "空头排列" -- MA5 < MA10 < MA20 < MA60  (bearish)
        "交叉震荡" -- neither (mixed/sideways)
    """
    closes, _, _, _ = _extract_arrays(kline)
    if len(closes) < 60:
        return "交叉震荡"
    ma5 = calc_ma(closes, 5)[-1]
    ma10 = calc_ma(closes, 10)[-1]
    ma20 = calc_ma(closes, 20)[-1]
    ma60 = calc_ma(closes, 60)[-1]
    if ma5 > ma10 > ma20 > ma60:
        return "多头排列"
    elif ma5 < ma10 < ma20 < ma60:
        return "空头排列"
    return "交叉震荡"


def detect_volume_status(kline: list[dict]) -> str:
    """Analyse recent volume relative to 20-day average.

    Returns:
        "放量" -- latest volume > 1.5x average
        "缩量" -- latest volume < 0.7x average
        "正常" -- otherwise
    """
    _, _, _, volumes = _extract_arrays(kline)
    if len(volumes) < 2:
        return "正常"
    avg20 = _calc_vol_ma(volumes[:-1], 20)  # exclude latest
    latest = volumes[-1]
    if avg20 == 0:
        return "正常"
    ratio = latest / avg20
    if ratio >= 1.5:
        return "放量"
    elif ratio <= 0.7:
        return "缩量"
    return "正常"


def detect_vcp(kline: list[dict]) -> dict:
    """Detect Volatility Contraction Pattern.

    Checks: MA20 support, range narrowing, volume contraction, lower shadows,
    proximity to recent high.

    Returns dict with keys: phase, score, price, volume_ratio, ma20,
    above_ma20, range_narrowing, lower_shadows, has_limit_up
    """
    if len(kline) < 20:
        return _vcp_empty_result()
    closes, highs, lows, volumes = _extract_arrays(kline)
    latest_close = closes[-1]
    ma20_val = calc_ma(closes, 20)[-1]
    above_ma20 = latest_close > ma20_val
    vol_avg20 = _calc_vol_ma(volumes[:-1], 20)
    vol_ratio = int(volumes[-1] / vol_avg20 * 100) if vol_avg20 > 0 else 100
    # --- range narrowing (last VCP_MIN_TIGHTENING_DAYS vs prior equal window) ---
    n = VCP_MIN_TIGHTENING_DAYS
    if len(kline) >= n * 2:
        recent_ranges = [highs[i] - lows[i] for i in range(-n, 0)]
        prior_ranges = [highs[i] - lows[i] for i in range(-n * 2, -n)]
        avg_recent_range = sum(recent_ranges) / n
        avg_prior_range = sum(prior_ranges) / n
        range_narrowing = avg_prior_range > 0 and avg_recent_range < avg_prior_range * 0.85
    else:
        range_narrowing = False
    # --- lower shadows in last 5 days ---
    lower_shadows = 0
    for i in range(max(-5, -len(kline)), 0):
        body_low = min(kline[i]["open"], kline[i]["close"])
        shadow = body_low - kline[i]["low"]
        body = abs(kline[i]["close"] - kline[i]["open"])
        if shadow > body * 0.5 and shadow > 0.01:
            lower_shadows += 1
    # --- limit-up detection ---
    has_limit_up = False
    for i in range(max(-20, -len(kline)), 0):
        change = (closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] > 0 else 0
        if change >= 0.095:
            has_limit_up = True
            break
    # --- phase & score ---
    score = 0
    if above_ma20:
        score += 20
    if range_narrowing:
        score += 30
    if vol_ratio < 80:
        score += 20
    if lower_shadows >= 2:
        score += 15
    # proximity to 20-day high
    high20 = max(highs[-20:])
    if high20 > 0 and latest_close >= high20 * 0.90:
        score += 15
    # phase determination
    if above_ma20 and range_narrowing and vol_ratio < 80:
        phase = "收缩"
    elif above_ma20 and lower_shadows >= 2 and not range_narrowing:
        phase = "企稳"
    elif vol_ratio > 130 and latest_close > ma20_val:
        phase = "突破"
    else:
        phase = "企稳" if above_ma20 else "无"
    return {
        "phase": phase,
        "score": min(score, 100),
        "price": round(latest_close, 2),
        "volume_ratio": vol_ratio,
        "ma20": round(ma20_val, 2),
        "above_ma20": above_ma20,
        "range_narrowing": range_narrowing,
        "lower_shadows": lower_shadows,
        "has_limit_up": has_limit_up,
    }


def _vcp_empty_result() -> dict:
    return {
        "phase": "无", "score": 0, "price": 0.0, "volume_ratio": 100,
        "ma20": 0.0, "above_ma20": False, "range_narrowing": False,
        "lower_shadows": 0, "has_limit_up": False,
    }


# ---------------------------------------------------------------------------
# Scan entry points -- VCP scan, technical scan
# ---------------------------------------------------------------------------


def _build_code_list(codes: list[str] | None) -> list[str]:
    """Resolve scan code list: given list > portfolio > default watchlist."""
    if codes:
        return [c for c in codes if c]
    portfolio = get_portfolio()
    if portfolio:
        portfolio_codes = [p["stock_code"] for p in portfolio if p.get("stock_code")]
        if portfolio_codes:
            return portfolio_codes
    return DEFAULT_WATCHLIST


def scan_vcp(codes: list[str] | None = None) -> dict:
    """Scan for VCP (Volatility Contraction Pattern) across code list.

    Returns dict matching the expected output format:
    {"scan_type":"vcp","param":null,"time":"...","count":N,"results":[...]}
    """
    code_list = _build_code_list(codes)
    logger.info("VCP scan starting for %d codes", len(code_list))
    results: list[dict] = []
    for code in code_list:
        try:
            kline = get_kline_tencent(code, period="day", limit=120)
            if not kline or len(kline) < 20:
                logger.debug("Skipping %s: insufficient K-line data", code)
                continue
            vcp = detect_vcp(kline)
            if vcp["phase"] == "无":
                continue
            vcp["code"] = code
            results.append(vcp)
        except Exception as e:
            logger.error("VCP scan failed for %s: %s", code, e)
            continue
    results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "scan_type": "vcp",
        "param": None,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(results),
        "results": results,
    }


def scan_watchlist_tech(codes: list[str] | None = None) -> dict:
    """Technical indicator scan across code list.

    Returns dict matching the expected output format:
    {"scan_type":"watchlist_tech","param":"default","time":"...","count":N,"results":[...]}
    """
    code_list = _build_code_list(codes)
    logger.info("Technical scan starting for %d codes", len(code_list))
    # Get real-time quotes first for names & price
    quotes_map: dict[str, dict] = {}
    try:
        quotes = get_realtime_quote_sina(code_list)
    except Exception as e:
        logger.warning("Sina quote fetch failed, trying Eastmoney: %s", e)
        quotes = get_realtime_quote_eastmoney(code_list)
    for q in quotes:
        quotes_map[q["code"]] = q
    results: list[dict] = []
    for code in code_list:
        try:
            kline = get_kline_tencent(code, period="day", limit=120)
            if not kline or len(kline) < 40:
                logger.debug("Skipping %s: insufficient K-line data", code)
                continue
            closes, _, _, _ = _extract_arrays(kline)
            quote = quotes_map.get(code, {})
            price = quote.get("price", closes[-1]) if quote else closes[-1]
            change_pct = quote.get("change_pct", 0.0) if quote else 0.0
            name = quote.get("name", "") if quote else ""
            ma_align = detect_ma_alignment(kline)
            rsi_val = calc_rsi(closes)
            dif_val, dea_val, _ = calc_macd(closes)
            macd_signal = "金叉" if dif_val > dea_val else "死叉"
            vol_status = detect_volume_status(kline)
            # composite score (0--100)
            score = 0
            if ma_align == "多头排列":
                score += 35
            elif ma_align == "空头排列":
                score += 5
            else:
                score += 18
            if macd_signal == "金叉":
                score += 30
            if vol_status == "放量":
                score += 20
            elif vol_status == "缩量":
                score += 5
            else:
                score += 12
            if 30 <= rsi_val <= 70:
                score += 15
            elif rsi_val < 30:
                score += 5
            results.append({
                "code": code,
                "name": name,
                "price": round(price, 2),
                "change_pct": round(change_pct, 2),
                "ma_alignment": ma_align,
                "rsi": round(rsi_val, 2),
                "macd_signal": macd_signal,
                "volume_status": vol_status,
                "score": score,
            })
        except Exception as e:
            logger.error("Tech scan failed for %s: %s", code, e)
            continue
    results.sort(key=lambda x: x["score"], reverse=True)
    return {
        "scan_type": "watchlist_tech",
        "param": "default",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Holdings comprehensive analysis
# ---------------------------------------------------------------------------


def analyze_holdings(codes: list[str]) -> list[dict]:
    """Run comprehensive technical analysis on each holding.

    For each code, produces a dict with:
      code, vcp, ma_alignment, rsi, macd_signal, volume_status, trend_strength,
      risk_warnings (list[str]), composite_score
    """
    results: list[dict] = []
    for code in codes:
        try:
            kline = get_kline_tencent(code, period="day", limit=120)
            if not kline or len(kline) < 40:
                logger.warning("Insufficient K-line data for %s", code)
                results.append(_empty_holding_result(code))
                continue
            closes, highs, lows, volumes = _extract_arrays(kline)
            vcp = detect_vcp(kline)
            ma_align = detect_ma_alignment(kline)
            rsi_val = calc_rsi(closes)
            dif_val, dea_val, histogram = calc_macd(closes)
            vol_status = detect_volume_status(kline)
            # Trend strength: slope of MA20 over last 10 days
            ma20_series = calc_ma(closes, 20)
            if len(ma20_series) >= 10:
                trend_slope = (ma20_series[-1] - ma20_series[-10]) / ma20_series[-10] * 100 if ma20_series[-10] > 0 else 0
                trend_strength = "强势" if trend_slope > 2 else "弱势" if trend_slope < -2 else "中性"
            else:
                trend_strength = "未知"
                trend_slope = 0.0
            # Risk warnings
            warnings: list[str] = []
            latest_close = closes[-1]
            ma60_val = calc_ma(closes, 60)[-1]
            if latest_close < ma60_val:
                warnings.append("跌破MA60中期支撑")
            if rsi_val > 80:
                warnings.append(f"RSI超买({rsi_val:.0f})")
            elif rsi_val < 20:
                warnings.append(f"RSI超卖({rsi_val:.0f})")
            if len(closes) >= 5:
                vol_ratio_5 = sum(volumes[-5:]) / (sum(volumes[-10:-5]) + 1)  # avoid div0
                if vol_ratio_5 > 2.0 and (closes[-1] < closes[-2]):
                    warnings.append("放量下跌，注意风险")
            if dif_val < dea_val and histogram and len(histogram) >= 3:
                if all(h < 0 for h in histogram[-3:]):
                    warnings.append("MACD持续绿柱，空方主导")
            # Composite score
            score = 0
            if vcp["phase"] != "无":
                score += vcp["score"]
            if ma_align == "多头排列":
                score += 35
            elif ma_align != "空头排列":
                score += 15
            if 40 <= rsi_val <= 65:
                score += 20
            elif 30 <= rsi_val <= 70:
                score += 10
            if dif_val > dea_val:
                score += 15
            if vol_status == "放量":
                score += 10
            score -= len(warnings) * 8
            score = max(0, min(score, 100))
            results.append({
                "code": code,
                "vcp_phase": vcp["phase"],
                "vcp_score": vcp["score"],
                "ma_alignment": ma_align,
                "rsi": round(rsi_val, 2),
                "macd_signal": "金叉" if dif_val > dea_val else "死叉",
                "volume_status": vol_status,
                "trend_strength": trend_strength,
                "trend_slope_pct": round(trend_slope, 2),
                "risk_warnings": warnings,
                "composite_score": score,
            })
        except Exception as e:
            logger.error("Holdings analysis failed for %s: %s", code, e)
            results.append(_empty_holding_result(code))
    return results


def _empty_holding_result(code: str) -> dict:
    return {
        "code": code,
        "vcp_phase": "无",
        "vcp_score": 0,
        "ma_alignment": "未知",
        "rsi": 0.0,
        "macd_signal": "未知",
        "volume_status": "未知",
        "trend_strength": "未知",
        "trend_slope_pct": 0.0,
        "risk_warnings": ["数据不足"],
        "composite_score": 0,
    }


# ---------------------------------------------------------------------------
# Bulk market data save (used by daily_task.py)
# ---------------------------------------------------------------------------


def save_holdings_market_data(codes: list[str]) -> int:
    """Fetch quotes for holdings and persist to market_data table.
    Returns count of codes successfully saved.
    """
    saved = 0
    try:
        quotes = get_realtime_quote_sina(codes)
    except Exception:
        quotes = get_realtime_quote_eastmoney(codes)
    records: list[dict] = []
    for q in quotes:
        records.append({
            "code": q["code"],
            "price": q.get("price"),
            "change_pct": q.get("change_pct"),
            "volume": q.get("volume"),
            "amount": q.get("amount"),
            "turnover_rate": q.get("turnover_rate", 0),
            "pe": q.get("pe", 0),
            "market_cap": q.get("market_cap", 0),
        })
    if records:
        save_market_data(records)
        saved = len(records)
    return saved


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    import sys
    if len(sys.argv) < 2:
        print("Usage: python stock_skill.py <vcp|tech|analyze> [codes...]")
        print("  vcp      - VCP pattern scan")
        print("  tech     - Technical indicator scan")
        print("  analyze  - Comprehensive holdings analysis (requires codes)")
        sys.exit(1)
    cmd = sys.argv[1]
    arg_codes = sys.argv[2:] if len(sys.argv) > 2 else None
    if cmd == "vcp":
        result = scan_vcp(arg_codes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif cmd == "tech":
        result = scan_watchlist_tech(arg_codes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif cmd == "analyze":
        if not arg_codes:
            portfolio = get_portfolio()
            arg_codes = [p["stock_code"] for p in portfolio if p.get("stock_code")]
        result = analyze_holdings(arg_codes)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
