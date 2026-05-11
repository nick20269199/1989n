"""
Emotional / Sentiment Cycle Analysis

Cross-references market-wide sentiment data (from StockAPI) with individual
stock performance to surface how each holding behaves under different
sentiment regimes (STRONG / WEAK / NORMAL).

Output: emotional_cycle_raw.json in STOCK_DATA_DIR
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

from config import STOCK_DATA_DIR, HEADERS, STOCKAPI_TOKEN, MA_PERIODS, RSI_PERIOD
from database import get_portfolio, get_market_history

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EMOTIONAL_CYCLE_FILE = Path(STOCK_DATA_DIR) / "emotional_cycle_raw.json"
STOCKAPI_SENTIMENT_URL = "https://www.stockapi.com.cn/v1/base/emotionalCycle"
CACHE_MAX_AGE_HOURS = 6
REQUEST_TIMEOUT = 15

# Sentiment level thresholds
SENTIMENT_STRONG_THRESHOLD = 70
SENTIMENT_WEAK_THRESHOLD = 30

# ---------------------------------------------------------------------------
# Sentiment data fetch
# ---------------------------------------------------------------------------


def fetch_emotional_cycle(force_refresh: bool = False) -> dict:
    """Fetch the latest market-wide sentiment snapshot from StockAPI.

    The result is cached to emotional_cycle_raw.json for up to CACHE_MAX_AGE_HOURS.
    Pass force_refresh=True to bypass the cache.

    Returns dict matching:
      {"update_time": "...", "sentiment_index": int, "level": "STRONG"|"WEAK"|"NORMAL",
       "description": "...", "history": [...]}
    """
    # 1. Check local cache
    if not force_refresh and EMOTIONAL_CYCLE_FILE.exists():
        try:
            cached = json.loads(EMOTIONAL_CYCLE_FILE.read_text(encoding="utf-8"))
            update_str = cached.get("update_time", "")
            if update_str:
                try:
                    update_dt = datetime.strptime(update_str, "%Y-%m-%d %H:%M:%S")
                    age = datetime.now() - update_dt
                    if age < timedelta(hours=CACHE_MAX_AGE_HOURS):
                        logger.info("Using cached sentiment data (age=%s)", age)
                        return cached
                except ValueError:
                    pass
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Corrupt sentiment cache: %s", e)

    # 2. Attempt StockAPI fetch
    raw_data = _fetch_from_stockapi()
    if raw_data is not None:
        _save_and_return(raw_data)
        return raw_data

    # 3. Fallback: compute proxy sentiment from cached history or empty
    logger.warning("StockAPI unavailable; generating proxy sentiment index")
    return _generate_proxy_sentiment()


def _fetch_from_stockapi() -> dict | None:
    """Call StockAPI sentiment endpoint. Returns None on failure."""
    if not STOCKAPI_TOKEN:
        logger.warning("STOCKAPI_TOKEN not configured, skipping StockAPI fetch")
        return None
    headers = HEADERS.copy()
    headers["Authorization"] = f"Bearer {STOCKAPI_TOKEN}"
    try:
        resp = requests.get(
            STOCKAPI_SENTIMENT_URL,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
        # Normalise keys from API into our canonical format
        return _normalise_stockapi_response(payload)
    except requests.exceptions.RequestException as e:
        logger.error("StockAPI sentiment fetch failed: %s", e)
        return None
    except Exception as e:
        logger.error("Unexpected error fetching sentiment: %s", e)
        return None


def _normalise_stockapi_response(payload: dict) -> dict:
    """Map StockAPI emotionalCycle response into our canonical sentiment dict.

    StockAPI returns: {"code": 20000, "data": {"colNameList": [...], "contentList": [[...], ...]}}
    Columns: date1, szbl(上涨比例), lbjs, ylgd, zxgd, dmqx(大面情绪), drqx(大肉情绪),
             ztjs(涨停家数), dbcgl(打板成功率), dtjs(跌停家数), ygmc, zbjs
    """
    data = payload.get("data", payload)
    col_names = data.get("colNameList", [])
    content_list = data.get("contentList", [])

    if not col_names or not content_list:
        return _empty_sentiment()

    # Build column index map
    col_map = {name: idx for idx, name in enumerate(col_names)}
    szbl_idx = col_map.get("szbl")
    dmqx_idx = col_map.get("dmqx")
    drqx_idx = col_map.get("drqx")
    ztjs_idx = col_map.get("ztjs")
    dtjs_idx = col_map.get("dtjs")
    date_idx = col_map.get("date1", 0)

    if szbl_idx is None:
        return _empty_sentiment()

    # Build history records
    history: list[dict] = []
    for row in content_list[-90:]:
        try:
            d = str(row[date_idx])
            szbl = float(row[szbl_idx]) if szbl_idx is not None else 50.0
            dmqx = float(row[dmqx_idx]) if dmqx_idx is not None else 0
            drqx = float(row[drqx_idx]) if drqx_idx is not None else 0
            ztjs = int(row[ztjs_idx]) if ztjs_idx is not None else 0
            dtjs = int(row[dtjs_idx]) if dtjs_idx is not None else 0
            history.append({
                "date": f"{d[:4]}-{d[4:6]}-{d[6:8]}",
                "sentiment_index": round(szbl, 1),
                "up_pct": szbl,
                "limit_up_count": ztjs,
                "limit_down_count": dtjs,
                "big_meat_sentiment": drqx,
                "big_noodle_sentiment": dmqx,
                "level": _index_to_level(int(szbl)),
            })
        except (IndexError, ValueError, TypeError):
            continue

    # Latest data point
    latest = history[-1] if history else {}
    idx = latest.get("sentiment_index", 50)
    level = _index_to_level(int(idx))
    drqx_val = latest.get("big_meat_sentiment", 0)
    dmqx_val = latest.get("big_noodle_sentiment", 0)
    zt = latest.get("limit_up_count", 0)
    dt = latest.get("limit_down_count", 0)
    desc = f"上涨比例{idx}% | 涨停{zt}家 跌停{dt}家 | 大肉{drqx_val} 大面{dmqx_val}"

    return {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sentiment_index": idx,
        "level": level,
        "description": desc,
        "history": history,
    }


def _empty_sentiment() -> dict:
    return {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sentiment_index": 50,
        "level": "NORMAL",
        "description": "无法解析情绪数据",
        "history": [],
    }


def _generate_proxy_sentiment() -> dict:
    """Produce a minimal proxy sentiment record when StockAPI is unreachable.

    Reads prior history file and appends a neutral placeholder so downstream
    consumers do not break on missing data.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing_history: list = []
    if EMOTIONAL_CYCLE_FILE.exists():
        try:
            old = json.loads(EMOTIONAL_CYCLE_FILE.read_text(encoding="utf-8"))
            existing_history = old.get("history", [])
        except Exception:
            pass
    existing_history.append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sentiment_index": 50,
        "level": "NORMAL",
        "source": "proxy",
    })
    result = {
        "update_time": now_str,
        "sentiment_index": 50,
        "level": "NORMAL",
        "description": "代理情绪指数 (StockAPI不可用时的估算值)",
        "history": existing_history[-90:],
    }
    _save_and_return(result)
    return result


def _save_and_return(data: dict) -> None:
    """Persist sentiment data to disk."""
    try:
        EMOTIONAL_CYCLE_FILE.parent.mkdir(parents=True, exist_ok=True)
        EMOTIONAL_CYCLE_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.debug("Sentiment data saved to %s", EMOTIONAL_CYCLE_FILE)
    except OSError as e:
        logger.error("Failed to write sentiment cache: %s", e)


# ---------------------------------------------------------------------------
# Sentiment helper utilities
# ---------------------------------------------------------------------------


def _index_to_level(index: int) -> str:
    if index >= SENTIMENT_STRONG_THRESHOLD:
        return "STRONG"
    elif index <= SENTIMENT_WEAK_THRESHOLD:
        return "WEAK"
    return "NORMAL"


def _describe_level(level: str) -> str:
    descriptions = {
        "STRONG": "市场情绪高涨，多数参与者偏乐观，板块轮动活跃",
        "WEAK": "市场情绪低迷，避险情绪升温，成交缩量",
        "NORMAL": "市场情绪中性，震荡分化，无明显方向性共识",
    }
    return descriptions.get(level, "未知")


# ---------------------------------------------------------------------------
# Cross-analysis: sentiment vs individual stock
# ---------------------------------------------------------------------------


def cross_analyze_emotion_vs_stock(code: str) -> dict:
    """Evaluate how a single stock performs across different sentiment regimes.

    Pulls the sentiment history from the cache file and the stock's market data
    from the database, then aligns them by date.

    Returns:
      {
        "code": "...",
        "analysis_period_days": int,
        "matched_days": int,
        "regimes": {
          "STRONG":  {"days": N, "avg_change_pct": X.X, "win_rate_pct": Y.Y},
          "WEAK":   {"days": N, "avg_change_pct": X.X, "win_rate_pct": Y.Y},
          "NORMAL": {"days": N, "avg_change_pct": X.X, "win_rate_pct": Y.Y}
        },
        "correlation_verdict": "顺周期"|"逆周期"|"独立行情"|"数据不足"
      }
    """
    # 1. Load sentiment history
    sentiment_by_date: dict[str, str] = {}
    try:
        raw = json.loads(EMOTIONAL_CYCLE_FILE.read_text(encoding="utf-8"))
        for entry in raw.get("history", []):
            d = entry.get("date", "")
            lvl = entry.get("level", entry.get("sentiment", ""))
            if d and lvl:
                sentiment_by_date[d] = lvl
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("Cannot load sentiment history for cross-analysis: %s", e)

    if not sentiment_by_date:
        return _empty_cross_result(code)

    # 2. Load stock market data from DB
    market_rows = get_market_history(code, days=90)
    if not market_rows:
        logger.warning("No market history for %s; cross-analysis limited", code)
        return _empty_cross_result(code)

    # 3. Align by date and bucket by regime
    regimes: dict[str, dict] = {
        "STRONG": {"changes": [], "days": 0, "wins": 0},
        "WEAK": {"changes": [], "days": 0, "wins": 0},
        "NORMAL": {"changes": [], "days": 0, "wins": 0},
    }
    matched = 0
    for row in market_rows:
        row_date = row.get("date", "")
        if not row_date or row_date not in sentiment_by_date:
            continue
        regime = sentiment_by_date[row_date]
        if regime not in regimes:
            continue
        change = row.get("change_pct", 0) or 0
        try:
            change_f = float(change)
        except (ValueError, TypeError):
            change_f = 0.0
        regimes[regime]["changes"].append(change_f)
        regimes[regime]["days"] += 1
        if change_f > 0:
            regimes[regime]["wins"] += 1
        matched += 1

    # 4. Compute regime statistics
    regime_stats: dict[str, dict] = {}
    for level, bucket in regimes.items():
        changes = bucket["changes"]
        days = bucket["days"]
        if days > 0:
            regime_stats[level] = {
                "days": days,
                "avg_change_pct": round(sum(changes) / days, 2),
                "win_rate_pct": round(bucket["wins"] / days * 100, 2),
            }
        else:
            regime_stats[level] = {"days": 0, "avg_change_pct": 0.0, "win_rate_pct": 0.0}

    # 5. Derive correlation verdict
    verdict = _derive_verdict(regime_stats, matched)
    return {
        "code": code,
        "analysis_period_days": 90,
        "matched_days": matched,
        "regimes": regime_stats,
        "correlation_verdict": verdict,
    }


def _derive_verdict(stats: dict[str, dict], matched: int) -> str:
    """Infer whether the stock is pro-cyclical, counter-cyclical, or independent."""
    if matched < 10:
        return "数据不足"
    strong_avg = stats.get("STRONG", {}).get("avg_change_pct", 0.0) or 0.0
    weak_avg = stats.get("WEAK", {}).get("avg_change_pct", 0.0) or 0.0
    s_days = stats.get("STRONG", {}).get("days", 0)
    w_days = stats.get("WEAK", {}).get("days", 0)
    if s_days < 3 or w_days < 3:
        return "数据不足"
    diff = strong_avg - weak_avg
    if diff > 1.5:
        return "顺周期"
    elif diff < -1.5:
        return "逆周期"
    return "独立行情"


def _empty_cross_result(code: str) -> dict:
    return {
        "code": code,
        "analysis_period_days": 90,
        "matched_days": 0,
        "regimes": {
            "STRONG": {"days": 0, "avg_change_pct": 0.0, "win_rate_pct": 0.0},
            "WEAK": {"days": 0, "avg_change_pct": 0.0, "win_rate_pct": 0.0},
            "NORMAL": {"days": 0, "avg_change_pct": 0.0, "win_rate_pct": 0.0},
        },
        "correlation_verdict": "数据不足",
    }


# ---------------------------------------------------------------------------
# Batch analysis across all holdings
# ---------------------------------------------------------------------------


def analyze_portfolio_emotion() -> list[dict]:
    """Run cross-analysis for every holding in the portfolio.

    Returns a list of per-stock cross-analysis results.
    """
    portfolio = get_portfolio()
    if not portfolio:
        logger.warning("No portfolio data found; cannot run cross-analysis")
        return []
    codes = [p["stock_code"] for p in portfolio if p.get("stock_code")]
    results: list[dict] = []
    for code in codes:
        try:
            result = cross_analyze_emotion_vs_stock(code)
            results.append(result)
        except Exception as e:
            logger.error("Cross-analysis failed for %s: %s", code, e)
            results.append(_empty_cross_result(code))
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    import sys
    if len(sys.argv) < 2:
        print("Usage: python emotional_analysis.py <fetch|cross|batch> [code]")
        print("  fetch       - Fetch/refresh sentiment index from StockAPI")
        print("  cross CODE  - Cross-analyze sentiment vs specific stock")
        print("  batch       - Cross-analyze all portfolio holdings")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "fetch":
        data = fetch_emotional_cycle(force_refresh=True)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif cmd == "cross":
        if len(sys.argv) < 3:
            print("Error: cross command requires a stock code")
            sys.exit(1)
        result = cross_analyze_emotion_vs_stock(sys.argv[2])
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif cmd == "batch":
        results = analyze_portfolio_emotion()
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
