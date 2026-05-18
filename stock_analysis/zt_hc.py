#!/usr/bin/env python3
"""
涨停回踩 (Limit-Up Pullback) — 策略扫描器 v3.0
===============================================
全A股市场扫描 (5000+ 标的)

核心条件 (四重过滤):
  1. 10个交易日内有过涨停
  2. 趋势向上 (10MA > 20MA > 60MA)
  3. 股价回踩到10日均线附近 (偏离 < 2%)
  4. 10日均线缩量翘头向上 (量缩 + MA10斜率转正)

用法:
  python zt_hc.py                    # 全市场扫描 (并发)
  python zt_hc.py 000062 002156     # 指定股票
  python zt_hc.py --top 10           # 只取前10结果
  python zt_hc.py --json             # JSON输出
"""

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

from market_pool import MarketPool
from market_pool.stock_list import filter_stocks, load_stock_list as mp_load_stock_list

pool = MarketPool()


# ═══════════════════════════════════════════════════
#  数据获取
# ═══════════════════════════════════════════════════

def get_all_a_stocks() -> list[dict]:
    """market_pool 全A股列表 (本地缓存, 毫秒级)。"""
    stocks = mp_load_stock_list()
    stocks = filter_stocks(stocks, exclude_st=True, exclude_bj=True, exclude_kcb=True)
    return stocks


def get_kline(code: str, days: int = 120) -> list[dict]:
    """market_pool K线 + 涨跌幅计算, 正序 (旧→新)。"""
    df = pool.get_kline(code, days)
    if df is None or df.empty:
        return []
    bars = []
    prev_close = None
    for _, row in df.iterrows():
        close = float(row["close"])
        if prev_close is not None:
            change_pct = (close - prev_close) / prev_close * 100
        else:
            change_pct = 0.0
        prev_close = close
        bars.append({
            "date": str(row["date"]),
            "open": float(row["open"]),
            "close": close,
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
            "change_pct": change_pct,
        })
    return bars


# ═══════════════════════════════════════════════════
#  技术指标
# ═══════════════════════════════════════════════════

def sma(bars: list[dict], field: str, idx: int, period: int) -> float:
    start = max(0, idx - period + 1)
    vals = [b[field] for b in bars[start:idx + 1]]
    return sum(vals) / len(vals) if vals else 0


def ma_slope(bars: list[dict], field: str, idx: int, period: int = 10) -> float:
    ma_now = sma(bars, field, idx, period)
    ma_before = sma(bars, field, max(0, idx - 3), period)
    if ma_before == 0:
        return 0
    return (ma_now - ma_before) / ma_before * 100


def threshold_for(code: str) -> float:
    prefix = code[:2] if code else ""
    if prefix in ("30", "68"):
        return 19.0
    if prefix in ("83", "87", "4"):
        return 29.0
    return 9.5


# ═══════════════════════════════════════════════════
#  四重过滤核心
# ═══════════════════════════════════════════════════

def check_stock(bars: list[dict], code: str = "") -> Optional[dict]:
    """四重过滤, 返回结果 dict 或 None。"""
    n = len(bars)
    if n < 30:
        return None

    thresh = threshold_for(code)

    # ── 条件1: 10个交易日内有过涨停 ──
    limit_up_idx = None
    for offset in range(min(10, n - 1)):
        idx = n - 1 - offset
        try:
            chg = float(bars[idx]["change_pct"])
        except (ValueError, TypeError):
            continue
        if chg >= thresh:
            limit_up_idx = idx
            break
    if limit_up_idx is None:
        return None

    latest = bars[-1]
    li = n - 1

    # ── 条件2: 趋势向上 ──
    ma10 = sma(bars, "close", li, 10)
    ma20 = sma(bars, "close", li, 20)
    ma60 = sma(bars, "close", li, 60)
    if not (ma10 > ma20 > ma60 * 0.98):
        return None

    # ── 条件3: 股价在10日均线附近 ──
    if ma10 == 0:
        return None
    dev = (latest["close"] - ma10) / ma10 * 100
    if not (-2 <= dev <= 2):
        return None

    # ── 条件4: 缩量 + MA10翘头 ──
    vol_ma3 = sma(bars, "volume", li, 3)
    vol_ma10 = sma(bars, "volume", li, 10)
    if vol_ma10 <= 0:
        return None
    shrink = vol_ma3 < vol_ma10 * 0.8
    slope = ma_slope(bars, "close", li, 10)
    turning = slope > 0.1
    if not (shrink and turning):
        return None

    # ── 通过 ──
    zt_bar = bars[limit_up_idx]
    retrace = (zt_bar["close"] - latest["close"]) / zt_bar["close"] * 100
    shrink_ratio = vol_ma3 / vol_ma10

    score = 60
    if abs(dev) < 1:
        score += 15
    elif abs(dev) < 1.5:
        score += 10
    if shrink_ratio < 0.5:
        score += 10
    elif shrink_ratio < 0.7:
        score += 5
    if slope > 0.3:
        score += 5
    if 2 < retrace < 8:
        score += 10

    return {
        "code": code,
        "name": "",
        "zt_date": zt_bar["date"],
        "zt_price": round(zt_bar["close"], 2),
        "latest_close": round(latest["close"], 2),
        "ma10": round(ma10, 2),
        "ma20": round(ma20, 2),
        "ma60": round(ma60, 2),
        "ma5": round(sma(bars, "close", li, 5), 2),
        "dev_pct": round(dev, 2),
        "retrace_pct": round(retrace, 2),
        "slope_ma10": round(slope, 2),
        "shrink_ratio": round(shrink_ratio, 2),
        "score": min(score, 100),
        "days_since_zt": li - limit_up_idx,
    }


# ═══════════════════════════════════════════════════
#  扫描引擎
# ═══════════════════════════════════════════════════

def is_excluded(stk: dict) -> bool:
    """排除科创板(688)和ST/*ST。"""
    code = stk.get("code", "")
    name = stk.get("name", "")
    if code.startswith("688"):
        return True
    if "ST" in name.upper() or "*ST" in name.upper():
        return True
    return False


def scan_one(stk: dict, days: int) -> Optional[dict]:
    """扫一只股票, 返回结果或None。"""
    if is_excluded(stk):
        return None
    try:
        bars = get_kline(stk["code"], days)
        if not bars or len(bars) < 30:
            return None
        r = check_stock(bars, stk["code"])
        if r:
            r["name"] = stk.get("name", "")
        return r
    except Exception:
        return None


def scan_all(days: int = 120, top: Optional[int] = None, workers: int = 6) -> list[dict]:
    """全市场并发扫描。"""
    stocks = get_all_a_stocks()
    total = len(stocks)
    print(f"\n全A股扫描启动 | 列表 {total} 只 | 并发 {workers} 线程 | 回溯 {days} 天", file=sys.stderr)
    print(f"{'=' * 50}", file=sys.stderr)

    results = []
    done = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        fut_map = {executor.submit(scan_one, stk, days): stk for stk in stocks}

        for fut in as_completed(fut_map):
            done += 1
            stk = fut_map[fut]
            try:
                r = fut.result()
                if r:
                    results.append(r)
                    # 实时输出发现的标的
                    print(f"  ▶ {r['code']} {r['name']} | 涨停{r['zt_date']} "
                          f"回踩{r['dev_pct']}% | 分{r['score']}", file=sys.stderr)
            except Exception:
                pass

            # 进度 (每5秒或每50只)
            if done % 100 == 0 or done == total:
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (total - done) / rate if rate > 0 else 0
                print(f"  进度 {done}/{total} | 已发现 {len(results)} 个 "
                      f"| 耗时 {elapsed:.0f}s | 速率 {rate:.1f}只/秒 "
                      f"| 预估剩 {eta:.0f}s", file=sys.stderr)

            if top and len(results) >= top:
                for f in fut_map:
                    f.cancel()
                break

    elapsed = time.time() - t0
    print(f"\n扫描完成 | 耗时 {elapsed:.0f}s | 发现 {len(results)} 个标的\n", file=sys.stderr)
    results.sort(key=lambda x: x["score"], reverse=True)
    return results


# ═══════════════════════════════════════════════════
#  输出
# ═══════════════════════════════════════════════════

def fmt(v):
    return f"{v:>8.2f}"


def print_results(results: list[dict]):
    if not results:
        print("未检测到符合四重条件的涨停回踩标的")
        return

    best = [r for r in results if r["score"] >= 80]
    good = [r for r in results if 65 <= r["score"] < 80]
    watch = [r for r in results if r["score"] < 65]

    print(f"\n{'=' * 90}")
    print(f"  涨停回踩扫描结果 | {datetime.now().strftime('%m-%d %H:%M')} | 共 {len(results)} 个标的")
    print(f"{'=' * 90}")

    sections = [
        ("★★★★ 高质量 (≥80)", best),
        ("★★★ 关注 (65-79)", good),
    ]
    for title, items in sections:
        if not items:
            continue
        print(f"\n{title} — {len(items)} 只")
        print(f"{'代码':<8} {'名称':<8} {'涨停日':<11} {'涨停价':>8} {'现价':>8} "
              f"{'MA10':>8} {'偏离%':>7} {'回撤%':>7} {'量缩比':>7} {'MA10斜率':>8} {'分数':>5}")
        print("-" * 90)
        for r in items:
            flag = " ★" if r["score"] >= 90 else ""
            print(f"{r['code']:<8} {r['name']:<8} {r['zt_date']:<11} "
                  f"{fmt(r['zt_price'])} {fmt(r['latest_close'])} "
                  f"{fmt(r['ma10'])} {r['dev_pct']:>6.2f}% "
                  f"{r['retrace_pct']:>6.2f}% {r['shrink_ratio']:>6.2f} "
                  f"{r['slope_ma10']:>7.2f}% {r['score']:>4}{flag}")

    if watch:
        print(f"\n★★ 观察 (<65) — {len(watch)} 只")
        for r in watch[:8]:
            print(f"  {r['code']} {r['name']} 涨停{r['zt_date']} 现价{r['latest_close']} "
                  f"MA10={r['ma10']} 偏离{r['dev_pct']}% 分{r['score']}")
        if len(watch) > 8:
            print(f"  ... 还有 {len(watch) - 8} 只")
    print()


# ═══════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="涨停回踩全市场扫描器")
    parser.add_argument("codes", nargs="*", help="指定股票代码")
    parser.add_argument("--days", type=int, default=120, help="回溯天数")
    parser.add_argument("--top", type=int, default=0, help="只取前N个结果")
    parser.add_argument("--workers", type=int, default=6, help="并发线程数")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    args = parser.parse_args()

    if args.codes:
        # ── 指定股票模式 ──
        results = []
        for code in args.codes:
            name = ""
            try:
                from stock_quote import PORTFOLIO
                if code in PORTFOLIO:
                    name = PORTFOLIO[code].get("name", "")
            except ImportError:
                pass
            bars = get_kline(code, args.days)
            if bars and len(bars) >= 30:
                r = check_stock(bars, code)
                if r:
                    r["name"] = name
                    results.append(r)
                else:
                    nm = f"({name})" if name else ""
                    print(f"{code} {nm}: 不符合四重条件")
            else:
                print(f"{code}: 数据不足 ({len(bars) if bars else 0} 条)")
        results.sort(key=lambda x: x["score"], reverse=True)
    else:
        # ── 全市场模式 ──
        results = scan_all(args.days, args.top if args.top > 0 else None, args.workers)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_results(results)


if __name__ == "__main__":
    main()
