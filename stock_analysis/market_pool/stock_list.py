"""
stock_list — A股全市场代码列表管理

提供全市场股票代码列表的获取、缓存、过滤。
数据源: 腾讯批量接口 + Sina 备选。
"""
import json
import logging
import re
import urllib.request
from datetime import datetime, timezone
from typing import Optional

from .config import STOCK_LIST_FILE, HEADERS, REQUEST_TIMEOUT

logger = logging.getLogger("market_pool.stock_list")

# 可过滤的板块前缀
EXCLUDE_PREFIXES = ("4", "8", "9")  # 北交所/三板


def _fetch(uri, headers=None, timeout=REQUEST_TIMEOUT, encoding="utf-8"):
    """通用 HTTP GET"""
    req = urllib.request.Request(uri, headers=headers or HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(encoding, errors="replace")
    except Exception as e:
        logger.debug("Fetch failed: %s — %s", uri[:60], e)
        return None


def fetch_stock_list() -> list[dict]:
    """从腾讯API获取全市场股票列表。

    返回 [{code, name, market}, ...] 按 code 排序。
    """
    # 沪深两市分开拉
    markets = [
        ("sz", "https://web.ifzq.gtimg.cn/appstock/app/hk/assets/stocks?market=1"),
        ("sh", "https://web.ifzq.gtimg.cn/appstock/app/hk/assets/stocks?market=0"),
    ]
    seen = set()
    result = []
    for market, url in markets:
        resp = _fetch(url)
        if not resp:
            logger.warning("股票列表获取失败(market=%s)", market)
            continue
        try:
            data = json.loads(resp)
            codes = data.get("data", [])
            for item in codes:
                code = str(item.get("code", "")).strip()
                name = item.get("name", "").strip()
                if not code or not code.isdigit():
                    continue
                if len(code) != 6:
                    continue
                if code in seen:
                    continue
                seen.add(code)
                result.append({"code": code, "name": name, "market": market})
        except Exception as e:
            logger.warning("解析股票列表失败(%s): %s", market, e)

    result.sort(key=lambda x: x["code"])
    logger.info("获取到 %d 只A股 (腾讯API)", len(result))
    return result


def load_stock_list(force_refresh=False) -> list[dict]:
    """加载股票列表(缓存优先)，返回 [{code, name, market}, ...]"""
    if not force_refresh and STOCK_LIST_FILE.exists():
        with open(STOCK_LIST_FILE, encoding="utf-8") as f:
            data = json.load(f)
        # 兼容两种格式: 老版 {"date":..., "stocks":[{code, name}, ...]}
        if isinstance(data, dict) and "stocks" in data:
            stocks = data["stocks"]
            result = []
            for s in stocks:
                if isinstance(s, dict) and "code" in s:
                    code = str(s["code"]).strip()
                    name = s.get("name", "")
                    market = "sh" if code.startswith(("6", "9")) else "sz"
                    result.append({"code": code, "name": name, "market": market})
            logger.info("从旧缓存加载股票列表: %d 只", len(result))
            return result
        if isinstance(data, list):
            logger.info("从缓存加载股票列表: %d 只", len(data))
            return data
        logger.warning("股票列表缓存格式异常, 重新获取")
        return fetch_stock_list()

    data = fetch_stock_list()
    STOCK_LIST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STOCK_LIST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    logger.info("股票列表已缓存: %s (%d 只)", STOCK_LIST_FILE, len(data))
    return data


def filter_stocks(
    stocks: list[dict],
    exclude_st: bool = True,
    exclude_bj: bool = True,
    exclude_kcb: bool = True,
    min_price: float = 3.0,
    max_price: float = 200.0,
) -> list[dict]:
    """过滤股票列表，返回符合条件的新列表"""
    result = []
    for s in stocks:
        code = s["code"]
        if exclude_kcb and code.startswith(("688", "689")):
            continue
        if exclude_bj and code.startswith(EXCLUDE_PREFIXES):
            continue
        if exclude_st and ("ST" in s.get("name", "").upper() or "退" in s.get("name", "")):
            continue
        # 价格过滤会在调用方完成 (需要实时行情)
        result.append(s)
    return result
