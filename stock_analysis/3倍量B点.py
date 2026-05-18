"""
3倍量B点 — 倍量拉升->缩量回踩->均线B点买入信号
========================================
策略逻辑:
  1. 某日成交量 >= 3倍 20日均量 (增量资金入场)
  2. 随后 2-5 日成交量逐步萎缩 (缩量洗盘)
  3. 价格回踩但不破 20日均线 (强势整理)
  4. 缩量至均量附近 + K线出现止跌信号 -> B点买入

用法:
  python "3倍量B点.py"              # 全市场扫描(默认, 排除科创板/ST)
  python "3倍量B点.py" --watch      # 仅扫描持仓
  python "3倍量B点.py" 000062       # 扫描单只
  python "3倍量B点.py" 000062,002156 # 扫描指定持仓
"""

import concurrent.futures
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from market_pool import MarketPool
from market_pool.stock_list import filter_stocks, load_stock_list as mp_load_stock_list

pool = MarketPool()

# -- 配置 --
VOLUME_RATIO = 3.0       # 倍量阈值: >=3倍20日均量
NEAR_MISS_RATIO = 2.0    # 接近阈值(用于展示潜力)
SHRINK_MAX_DAYS = 5      # 缩量观察窗口: 倍量后最多N天
MA_PERIOD = 20           # 均线周期
BOUNCE_MIN_HOLD_DAYS = 2 # 回踩至少持续N天

STOCK_DATA_DIR = Path("D:/1989n/stock_data")
OUTPUT_DIR = STOCK_DATA_DIR / "signals"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 持仓列表（用于 --watch 模式 + 持仓映射）
WATCHLIST = [
    ("000062", "深圳华强"), ("002156", "通富微电"),
    ("300480", "光力科技"), ("002407", "多氟多"),
    ("300342", "天银机电"), ("300739", "明阳电路"),
    ("601789", "宁波建工"),
]


# ================================================
# 数据获取
# ================================================

def fetch_kline(code: str, days: int = 120) -> Optional[list]:
    """通过 market_pool 获取日K线 (本地缓存, 毫秒级)"""
    df = pool.get_kline(code, days)
    if df is None or df.empty:
        return None
    bars = []
    for _, row in df.iterrows():
        bars.append({
            "date": str(row["date"]),
            "open": float(row["open"]),
            "close": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "volume": float(row["volume"]),
        })


# ================================================
# A股全市场列表
# ================================================

def load_a_stock_list(force_refresh: bool = False) -> list[dict]:
    """从 market_pool 加载A股全市场列表, 排除ST/科创板/北交所。"""
    stocks = mp_load_stock_list(force_refresh=force_refresh)
    stocks = filter_stocks(stocks, exclude_st=True, exclude_bj=True, exclude_kcb=True)
    return stocks


def scan_full_market() -> tuple[list, list, list]:
    """
    全市场扫描: 对所有候选股检查B点信号。
    并发15线程。首次运行较慢(K线无缓存), 之后靠缓存提速。
    """
    stocks = load_a_stock_list()
    if not stocks:
        print("  !! 无法获取股票列表")
        return [], [], []

    total = len(stocks)
    print(f"\n  >> 全市场扫描开始 ({total}只, 并发15线程)...")
    print(f"  >> 首次需获取所有K线(腾讯通道), 预计6-10分钟; 之后读取缓存仅需30-60秒")
    print()

    results = []
    near_misses = []
    scanned = 0
    t0 = time.time()

    def scan_one(s: dict) -> tuple[Optional[dict], Optional[dict]]:
        kline = fetch_kline(s["code"])
        if not kline or len(kline) < MA_PERIOD + 5:
            return None, None
        sig = detect_b_point(kline)
        nm = None
        if not sig:
            ma_vols = []
            for i in range(len(kline)):
                if i < MA_PERIOD - 1:
                    ma_vols.append(None)
                else:
                    ma_vols.append(sum(kline[j]["volume"] for j in range(i - MA_PERIOD + 1, i + 1)) / MA_PERIOD)
            for i in range(len(kline) - 1, MA_PERIOD, -1):
                if ma_vols[i] is None or ma_vols[i] == 0:
                    continue
                ratio = kline[i]["volume"] / ma_vols[i]
                if NEAR_MISS_RATIO <= ratio < VOLUME_RATIO:
                    nm = {"code": s["code"], "name": s["name"], "near_misses": [{
                        "date": kline[i]["date"], "volume_ratio": round(ratio, 2), "close": kline[i]["close"],
                    }]}
                    break
        if sig:
            sig["code"] = s["code"]
            sig["name"] = s["name"]
        return sig, nm

    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        futures = {executor.submit(scan_one, s): s for s in stocks}
        for fut in concurrent.futures.as_completed(futures):
            s = futures[fut]
            scanned += 1
            sig, nm = fut.result()
            if sig:
                results.append(sig)
                print(f"  V {s['name']}({s['code']}) B点! 倍量{sig['volume_ratio']}x")
            if nm:
                near_misses.append(nm)

            if scanned % 200 == 0:
                elapsed = time.time() - t0
                rate = scanned / elapsed if elapsed > 0 else 0
                remaining = (total - scanned) / rate if rate > 0 else 0
                print(f"  ...进度 {scanned}/{total} ({scanned*100//total}%)  {rate:.0f}只/秒 还剩{remaining:.0f}s")

    return results, [], near_misses


# ================================================
# 策略核心
# ================================================

def detect_b_point(kline: list) -> Optional[dict]:
    """
    检测3倍量B点信号。

    返回:
      {
        "signal_date": "倍量日",
        "b_point_date": "B点日",
        "volume_ratio": 倍量倍数,
        "shrink_pct": 缩量百分比,
        "ma_price": 均线价格,
        "current_price": 当前价,
        "bounce_pct": 回踩幅度,
        "status": "ready" | "watching"
      }
      或 None
    """
    if not kline or len(kline) < MA_PERIOD + 5:
        return None

    # 计算20日均量
    ma_volumes = []
    for i in range(len(kline)):
        if i < MA_PERIOD - 1:
            ma_volumes.append(None)
        else:
            avg = sum(kline[j]["volume"] for j in range(i - MA_PERIOD + 1, i + 1)) / MA_PERIOD
            ma_volumes.append(avg)

    # 计算20日均线
    ma_prices = []
    for i in range(len(kline)):
        if i < MA_PERIOD - 1:
            ma_prices.append(None)
        else:
            avg = sum(kline[j]["close"] for j in range(i - MA_PERIOD + 1, i + 1)) / MA_PERIOD
            ma_prices.append(avg)

    # 找倍量信号: 从后往前扫描
    for i in range(len(kline) - 1, MA_PERIOD, -1):
        if ma_volumes[i] is None or ma_volumes[i] == 0:
            continue

        ratio = kline[i]["volume"] / ma_volumes[i]
        if ratio < VOLUME_RATIO:
            continue

        # 倍量当天排除大跌出货
        day_range = kline[i]["high"] - kline[i]["low"]
        if day_range > 0:
            pos = (kline[i]["close"] - kline[i]["low"]) / day_range
        else:
            pos = 0.5
        if pos < 0.3:
            continue

        # 倍量后观察缩量回踩
        remaining = min(SHRINK_MAX_DAYS, len(kline) - 1 - i)
        if remaining < BOUNCE_MIN_HOLD_DAYS:
            continue

        signal_date = kline[i]["date"]
        b_point = None
        shrink_pct = 0

        for j in range(i + 1, i + remaining + 1):
            if j >= len(kline):
                break
            day_vol = kline[j]["volume"]
            if kline[i]["volume"] > 0:
                day_shrink = 1 - (day_vol / kline[i]["volume"])
            else:
                day_shrink = 0

            # 价格在均线上方(允许2%偏差)
            if ma_prices[j] is None:
                continue
            above_ma = kline[j]["close"] >= ma_prices[j] * 0.98
            if not above_ma:
                continue

            # 止跌信号: 缩量 + 小实体
            candle_body = abs(kline[j]["close"] - kline[j]["open"])
            if candle_body / kline[j]["close"] < 0.04:
                b_point = kline[j]
                shrink_pct = day_shrink
                break

        if b_point and shrink_pct > 0:
            bounce_pct = (b_point["close"] - kline[i]["close"]) / kline[i]["close"] * 100
            return {
                "signal_date": signal_date,
                "b_point_date": b_point["date"],
                "volume_ratio": round(ratio, 2),
                "shrink_pct": round(shrink_pct * 100, 1),
                "ma_price": round(ma_prices[kline.index(b_point)], 2) if b_point in kline else 0,
                "current_price": b_point["close"],
                "signal_price": kline[i]["close"],
                "bounce_pct": round(bounce_pct, 2),
                "status": "ready",
            }

    return None


# ================================================
# 输出
# ================================================

def print_report(results: list, watchlist_signals: list, near_misses: list = None):
    """格式化输出B点信号报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'='*60}")
    print(f"  3倍量B点 -- 信号报告")
    print(f"  {now}")
    print(f"{'='*60}")

    if not results:
        print("\n  当前无符合条件的B点信号。")
    else:
        # 持仓信号优先展示
        if watchlist_signals:
            print(f"\n  >> 持仓B点信号 ({len(watchlist_signals)}只)")
            print(f"  {'-'*56}")
            for s in watchlist_signals:
                print(f"  {s['name']}({s['code']})  B点确认")
                print(f"    倍量: {s['signal_date']}  {s['volume_ratio']}x 均量")
                print(f"    缩量: {s['b_point_date']}  回缩 {s['shrink_pct']}%")
                print(f"    价格: {s['current_price']}  20MA: {s['ma_price']}")
                print(f"    回踩: {s['bounce_pct']}%")
                print()

        # 全市场信号
        wl_codes = {s.get("code") for s in watchlist_signals}
        others = [r for r in results if r.get("code") not in wl_codes]
        if others:
            print(f"\n  >> 其他符合条件的信号 ({len(others)}只)")
            print(f"  {'-'*56}")
            for s in others[:10]:
                print(f"  {s.get('name', '?')}({s.get('code', '?')})")
                print(f"    B点: {s.get('b_point_date', '?')}  倍量: {s.get('volume_ratio', '?')}x")
                print(f"    价格: {s.get('current_price', '?')}  20MA: {s.get('ma_price', '?')}")
                print()

        if len(others) > 10:
            print(f"  ... 还有 {len(others) - 10} 只, 见信号文件\n")

    # 近信号展示
    if near_misses:
        print(f"\n  >> 接近信号 (2.0-2.99x, 仅差临门一脚) -- {len(near_misses)}只")
        print(f"  {'-'*56}")
        for nm in near_misses[:8]:
            dates = ", ".join(m["date"] for m in nm["near_misses"][:3])
            ratios = ", ".join(f'{m["volume_ratio"]}x' for m in nm["near_misses"][:3])
            print(f"  {nm['name']}({nm['code']}) 倍量: {ratios} ({dates})")
        if len(near_misses) > 8:
            print(f"  ... 还有 {len(near_misses) - 8} 只")
        print()

    # 保存到文件
    report = {
        "generated": now,
        "total_signals": len(results),
        "watchlist_signals": len(watchlist_signals),
        "signals": results,
        "near_misses": near_misses or [],
    }
    report_path = OUTPUT_DIR / f"3倍量B点_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  完整信号已保存: {report_path}")
    print()


# ================================================
# 主流程
# ================================================

def scan_stock(code: str, name: str = "") -> Optional[dict]:
    """扫描单只股票, 返回信号或None"""
    kline = fetch_kline(code)
    if not kline:
        return None

    signal = detect_b_point(kline)
    if signal:
        signal["code"] = code
        signal["name"] = name or code
        return signal
    return None


def scan_near_miss(code: str, name: str = "") -> Optional[dict]:
    """检测接近3倍量但未完全满足条件的股票(潜力观察)"""
    kline = fetch_kline(code)
    if not kline or len(kline) < MA_PERIOD + 5:
        return None

    ma_vols = []
    for i in range(len(kline)):
        if i < MA_PERIOD - 1:
            ma_vols.append(None)
        else:
            ma_vols.append(sum(kline[j]["volume"] for j in range(i - MA_PERIOD + 1, i + 1)) / MA_PERIOD)

    near_misses = []
    for i in range(len(kline) - 1, MA_PERIOD, -1):
        if ma_vols[i] is None or ma_vols[i] == 0:
            continue
        ratio = kline[i]["volume"] / ma_vols[i]
        if NEAR_MISS_RATIO <= ratio < VOLUME_RATIO:
            near_misses.append({
                "date": kline[i]["date"],
                "volume_ratio": round(ratio, 2),
                "close": kline[i]["close"],
            })
        if len(near_misses) >= 3:
            break

    if near_misses:
        return {"code": code, "name": name or code, "near_misses": near_misses}
    return None


def main():
    args = sys.argv[1:]

    # --watch: 仅扫描持仓
    if "--watch" in args or "-w" in args:
        print(f"\n  >> 扫描持仓...")
        results = []
        for code, name in WATCHLIST:
            print(f"    {name}({code})...", end=" ", flush=True)
            sig = scan_stock(code, name)
            if sig:
                print("B点")
                results.append(sig)
            else:
                print("--")
            time.sleep(0.3)

        print(f"\n  >> 扫描接近信号...")
        near_misses_list = []
        nm_scanned = {s.get("code") for s in results}
        for code, name in WATCHLIST:
            if code in nm_scanned:
                continue
            mn = scan_near_miss(code, name)
            if mn:
                near_misses_list.append(mn)
            time.sleep(0.15)

        watchlist_signals = [s for s in results if s.get("code") in {c for c, _ in WATCHLIST}]
        print_report(results, watchlist_signals, near_misses_list)
        return

    # 扫描指定股票代码
    codes = []
    for c in args:
        codes.extend([x.strip() for x in c.split(",") if x.strip()])

    if codes:
        named = {c: n for c, n in WATCHLIST}
        results = []
        for code in codes:
            name = named.get(code, "")
            print(f"  扫描 {name or code}...", end=" ", flush=True)
            sig = scan_stock(code, name)
            if sig:
                print("B点")
                results.append(sig)
            else:
                print("--")
            time.sleep(0.3)

        watchlist_signals = [s for s in results if s.get("code") in named]
        print_report(results, watchlist_signals, [])
        return

    # 默认: 全市场扫描
    results, _, near_misses = scan_full_market()
    watchlist_signals = [s for s in results if s.get("code") in {c for c, _ in WATCHLIST}]
    print_report(results, watchlist_signals, near_misses)


if __name__ == "__main__":
    main()
