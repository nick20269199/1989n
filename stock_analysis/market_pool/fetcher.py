"""
fetcher — 多源统一数据获取层

Tencent(主) + Sina(备) + Sohu(备) 三级回退。
所有 API 反爬失败 → 自动切下一级，调用方无感知。
"""
import json
import logging
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from .config import (
    HEADERS, TENCENT_HEADERS, SINA_HEADERS, REQUEST_TIMEOUT,
)

logger = logging.getLogger("market_pool.fetcher")

# ── 市场前缀 ──

def _prefix(code: str) -> str:
    """A股交易所前缀"""
    c = code.strip()
    if c.startswith(("60", "68", "90", "9")):
        return "sh"
    return "sz"


# ── 底层 HTTP ──

def _fetch(uri, headers=None, timeout=REQUEST_TIMEOUT, encoding="utf-8"):
    req = urllib.request.Request(uri, headers=headers or HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(encoding, errors="replace")
    except Exception as e:
        logger.debug("Fetch failed: %s — %s", uri[:60], e)
        return None


# ═══════════════════════════════════════════════════════
# 1. 日K线 (腾讯前复权 → 搜狐备选)
# ═══════════════════════════════════════════════════════

def fetch_kline_tencent(code: str, days: int = 365) -> Optional[list]:
    """腾讯日K线(前复权) — 主通道。
    返回 [{date, open, close, high, low, volume, amount}, ...] 按日期升序。
    """
    tc = f"{_prefix(code)}{code}"
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={tc},day,,,{days},qfq")
    resp = _fetch(url, TENCENT_HEADERS)
    if not resp:
        return None
    try:
        data = json.loads(resp)
        day_data = (data.get("data", {}).get(tc, {}).get("day")
                    or data.get("data", {}).get(tc, {}).get("qfqday")
                    or [])
        if not day_data:
            return None
        bars = []
        for item in day_data:
            try:
                if not isinstance(item, (list, tuple)):
                    continue
                vol = 0
                if len(item) > 5 and isinstance(item[5], (int, float, str)):
                    vol = float(item[5])
                amt = 0
                if len(item) > 6 and isinstance(item[6], (int, float, str)):
                    amt = float(item[6])
                bars.append({
                    "date": item[0],
                    "open": float(item[1]),
                    "close": float(item[2]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "volume": vol,
                    "amount": amt,
                })
            except (ValueError, IndexError, TypeError):
                continue
        return bars if bars else None
    except json.JSONDecodeError:
        return None


def fetch_kline_sohu(code: str, days: int = 365) -> Optional[list]:
    """搜狐日K线 — 备选通道。"""
    end = datetime.now().strftime("%Y%m%d")
    start = (datetime.now() - timedelta(days=days + 5)).strftime("%Y%m%d")
    url = f"https://q.stock.sohu.com/hisHq?code=cn_{code}&start={start}&end={end}"
    resp = _fetch(url, encoding="utf-8")
    if not resp:
        return None
    try:
        data = json.loads(resp)
        if not data or "hq" not in data[0]:
            return None
        bars = []
        for row in data[0]["hq"]:
            bars.append({
                "date": row[0],
                "open": float(row[1]),
                "close": float(row[2]),
                "high": float(row[6]),
                "low": float(row[5]),
                "volume": int(row[7]) if row[7] else 0,
                "amount": float(row[8]) if row[8] else 0,
            })
        return bars
    except (json.JSONDecodeError, IndexError, ValueError):
        return None


def fetch_kline(code: str, days: int = 365) -> Optional[list]:
    """获取日K线: 腾讯 → 搜狐 自动回退。"""
    bars = fetch_kline_tencent(code, days)
    if bars:
        return bars
    logger.debug("腾讯K线失败(%s), 切搜狐", code)
    bars = fetch_kline_sohu(code, days)
    if bars:
        return bars
    logger.warning("所有K线源均失败: %s", code)
    return None


# ═══════════════════════════════════════════════════════
# 2. 实时行情 (腾讯 → 新浪 双通道)
# ═══════════════════════════════════════════════════════

def fetch_quotes_tencent(codes: list[str]) -> dict:
    """腾讯实时行情 — 主通道。
    一次最多批量查几十只。返回 {code: {fields...}, ...}
    """
    if not codes:
        return {}
    mapped = ",".join(f"{_prefix(c)}{c}" for c in codes)
    url = f"https://web.sqt.gtimg.cn/q={mapped}"
    resp = _fetch(url, TENCENT_HEADERS)
    if not resp:
        return {}
    result = {}
    for line in resp.strip().split("\n"):
        try:
            if "=" not in line:
                continue
            d = line.split('"')[1].split("~")
            if len(d) < 40:
                continue
            num = re.sub(r"\D", "", d[2]) if len(d) > 2 else ""
            if not num:
                continue
            result[num] = {
                "name": d[1],
                "code": num,
                "current": float(d[3]) if d[3] else 0,
                "prev_close": float(d[4]) if d[4] else 0,
                "open": float(d[5]) if d[5] else 0,
                "high": float(d[33]) if len(d) > 33 and d[33] else 0,
                "low": float(d[34]) if len(d) > 34 and d[34] else 0,
                "volume": int(float(d[6]) * 100) if d[6] else 0,
                "amount": float(d[37]) if len(d) > 37 and d[37] else 0,  # 总成交额
                "bid": float(d[9]) if d[9] else 0,     # 买一价
                "ask": float(d[19]) if len(d) > 19 and d[19] else 0,  # 卖一价
                "change_pct": float(d[32]) if len(d) > 32 and d[32] else 0,
                "turnover_rate": float(d[38]) if len(d) > 38 and d[38] else 0,  # 换手率
                "pe": float(d[39]) if len(d) > 39 and d[39] else 0,  # 市盈率
                "high_52w": float(d[43]) if len(d) > 43 and d[43] else 0,  # 52周高
                "low_52w": float(d[44]) if len(d) > 44 and d[44] else 0,   # 52周低
                "time": d[30] if len(d) > 30 else "",
                "market_cap": float(d[45]) if len(d) > 45 and d[45] else 0,  # 总市值(亿)
                "source": "tencent",
            }
        except (ValueError, IndexError):
            continue
    return result


def fetch_quotes_sina(codes: list[str]) -> dict:
    """新浪实时行情 — 备选通道。"""
    if not codes:
        return {}
    mapped = ",".join(f"{_prefix(c)}{c}" for c in codes)
    url = f"https://hq.sinajs.cn/list={mapped}"
    resp = _fetch(url, SINA_HEADERS, encoding="gbk")
    if not resp:
        return {}
    result = {}
    for line in resp.strip().split("\n"):
        try:
            if "=" not in line:
                continue
            d = line.split('"')[1].split(",")
            num = re.sub(r"\D", "", line.split("=")[0].split("_")[-1])
            if not num or len(d) < 32:
                continue
            prev_close = float(d[2]) if d[2] else 0
            current = float(d[3]) if d[3] else 0
            result[num] = {
                "name": d[0],
                "code": num,
                "current": current,
                "prev_close": prev_close,
                "open": float(d[1]) if d[1] else 0,
                "high": float(d[4]) if d[4] else 0,
                "low": float(d[5]) if d[5] else 0,
                "volume": int(d[8]) if d[8] else 0,
                "amount": float(d[9]) if d[9] else 0,
                "bid": float(d[10]) if d[10] else 0,  # 买一价
                "ask": float(d[20]) if len(d) > 20 and d[20] else 0,  # 卖一价
                "change_pct": round((current - prev_close) / prev_close * 100, 2) if prev_close else 0,
                "time": d[30] if len(d) > 30 else "",
                "source": "sina",
            }
        except (ValueError, IndexError):
            continue
    return result


def fetch_quotes(codes: list[str]) -> dict:
    """获取实时行情: 腾讯 → 新浪 自动回退。
    一次可传多只股票代码。返回 {code: {fields...}, ...}
    """
    result = fetch_quotes_tencent(codes)
    missing = [c for c in codes if c not in result]
    if missing:
        logger.debug("腾讯缺失 %d 只, 新浪补", len(missing))
        result.update(fetch_quotes_sina(missing))
    return result


# ═══════════════════════════════════════════════════════
# 3. 指数行情
# ═══════════════════════════════════════════════════════

def _index_prefix(code: str) -> str:
    """指数前缀: 00开头=上海, 39/30=深圳"""
    if code.startswith("00"):
        return "sh"
    return "sz"


A_INDICES = [
    ("000001", "上证指数"),
    ("399001", "深证成指"),
    ("399006", "创业板指"),
    ("000688", "科创50"),
    ("000300", "沪深300"),
]


def fetch_indices() -> list[dict]:
    """获取主要指数行情。返回 [{code, name, price, change_pct}, ...]"""
    codes = [c for c, _ in A_INDICES]
    mapped = ",".join(f"{_index_prefix(c)}{c}" for c in codes)

    # 腾讯通道
    url = f"https://web.sqt.gtimg.cn/q={mapped}"
    resp = _fetch(url, TENCENT_HEADERS)
    if resp:
        result = []
        for line in resp.strip().split("\n"):
            try:
                if "=" not in line:
                    continue
                d = line.split('"')[1].split("~")
                if len(d) < 40:
                    continue
                num = re.sub(r"\D", "", d[2]) if len(d) > 2 else ""
                if not num:
                    continue
                change_pct = float(d[32]) if len(d) > 32 and d[32] else 0
                result.append({
                    "code": num,
                    "name": d[1],
                    "price": float(d[3]) if d[3] else 0,
                    "prev_close": float(d[4]) if d[4] else 0,
                    "change_pct": change_pct,
                    "high": float(d[33]) if len(d) > 33 and d[33] else 0,
                    "low": float(d[34]) if len(d) > 34 and d[34] else 0,
                    "source": "tencent",
                })
            except (ValueError, IndexError):
                continue
        if result:
            return result

    # 新浪备选
    return _fetch_indices_sina(codes)


def _fetch_indices_sina(codes: list[str]) -> list[dict]:
    mapped = ",".join(f"{_index_prefix(c)}{c}" for c in codes)
    url = f"https://hq.sinajs.cn/list={mapped}"
    resp = _fetch(url, SINA_HEADERS, encoding="gbk")
    if not resp:
        return []
    result = []
    for line in resp.strip().split("\n"):
        try:
            if "=" not in line:
                continue
            d = line.split('"')[1].split(",")
            num = re.sub(r"\D", "", line.split("=")[0].split("_")[-1])
            if not num or len(d) < 6:
                continue
            prev_close = float(d[2]) if d[2] else 0
            current = float(d[3]) if d[3] else 0
            result.append({
                "code": num,
                "name": d[0],
                "price": current,
                "prev_close": prev_close,
                "change_pct": round((current - prev_close) / prev_close * 100, 2) if prev_close else 0,
                "high": float(d[4]) if d[4] else 0,
                "low": float(d[5]) if d[5] else 0,
                "source": "sina",
            })
        except (ValueError, IndexError):
            continue
    return result


# ═══════════════════════════════════════════════════════
# 4. 单只批量 —— 用于全市场批量更新
# ═══════════════════════════════════════════════════════

def fetch_batch_kline(codes: list[str], days: int = 365) -> dict:
    """批量获取多只K线 (并行在调用方实现)。
    返回 {code: [bars...], ...} 仅成功获取的。
    """
    result = {}
    for code in codes:
        bars = fetch_kline(code, days)
        if bars:
            result[code] = bars
    return result
