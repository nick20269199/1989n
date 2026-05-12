"""
3倍量B点 — 倍量拉升→缩量回踩→均线B点买入信号
========================================
策略逻辑:
  1. 某日成交量 ≥ 3倍 20日均量 (增量资金入场)
  2. 随后 2-5 日成交量逐步萎缩 (缩量洗盘)
  3. 价格回踩但不破 20日均线 (强势整理)
  4. 缩量至均量附近 + K线出现止跌信号 → B点买入

用法:
  python "3倍量B点.py"              # 扫描全市场
  python "3倍量B点.py" 000062       # 扫描单只
  python "3倍量B点.py" 000062,002156 # 扫描指定持仓
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

# ── 配置 ──
VOLUME_RATIO = 3.0       # 倍量阈值: ≥3倍20日均量
NEAR_MISS_RATIO = 2.0    # 接近阈值(用于展示潜力)
SHRINK_MAX_DAYS = 5      # 缩量观察窗口: 倍量后最多N天
MA_PERIOD = 20           # 均线周期
BOUNCE_MIN_HOLD_DAYS = 2 # 回踩至少持续N天

STOCK_DATA_DIR = Path("D:/1989n/stock_data")
OUTPUT_DIR = STOCK_DATA_DIR / "signals"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 持仓列表（用于优先扫描 + 持仓映射）
WATCHLIST = [
    ("000062", "深圳华强"), ("002156", "通富微电"),
    ("300480", "光力科技"), ("002407", "多氟多"),
    ("300342", "天银机电"), ("300739", "明阳电路"),
    ("601789", "宁波建工"),
]


# ═══════════════════════════════════════════════
# 数据获取
# ═══════════════════════════════════════════════

def fetch_kline(code: str, days: int = 60) -> Optional[list]:
    """通过新浪/腾讯获取日K线数据，返回 [{date, open, high, low, close, volume}, ...]"""
    now = datetime.now()
    end_date = now.strftime("%Y%m%d")
    start = (now - timedelta(days=days)).strftime("%Y%m%d")

    # 尝试新浪
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://finance.sina.com.cn",
    }
    prefix = _sina_prefix(code)
    url = f"https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_{code}/=/CN_MarketData.getKLineData?symbol={prefix}{code}&scale=60&datalen={days // 5}"

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        text = resp.text
        # 解析 JSONP
        json_str = text[text.find("(") + 1 : text.rfind(")")]
        data = json.loads(json_str)
        result = []
        for item in data:
            try:
                result.append({
                    "date": item["date"],
                    "open": float(item["open"]),
                    "high": float(item["high"]),
                    "low": float(item["low"]),
                    "close": float(item["close"]),
                    "volume": float(item["volume"]),
                })
            except (KeyError, ValueError):
                continue
        if result:
            return result
    except Exception:
        pass

    # 备选: 腾讯
    try:
        tc_code = f"{'sh' if code.startswith('6') else 'sz'}{code}"
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={tc_code},day,,,{days},qfq"
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        days_list = data.get("data", {}).get(tc_code, {}).get("day", [])
        if not days_list or "qfqday" in str(data.get("data", {}).get(tc_code, {}).keys()):
            days_list = data.get("data", {}).get(tc_code, {}).get("qfqday", days_list)
        result = []
        for item in days_list:
            try:
                result.append({
                    "date": item[0],
                    "open": float(item[1]),
                    "close": float(item[2]),
                    "high": float(item[3]),
                    "low": float(item[4]),
                    "volume": float(item[5]) if len(item) > 5 else 0,
                })
            except (ValueError, IndexError):
                continue
        if result:
            return result
    except Exception:
        pass

    return None


def _sina_prefix(code: str) -> str:
    """新浪股票前缀"""
    if code.startswith("6"):
        return "sh"
    elif code.startswith("0") or code.startswith("3"):
        return "sz"
    elif code.startswith("4"):
        return "bj"
    return "sz"


# ═══════════════════════════════════════════════
# 策略核心
# ═══════════════════════════════════════════════

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

        # 倍量当天应该收阳或至少收在中间以上（不算严格，但排除大跌放量）
        day_range = kline[i]["high"] - kline[i]["low"]
        if day_range > 0:
            pos = (kline[i]["close"] - kline[i]["low"]) / day_range
        else:
            pos = 0.5
        if pos < 0.3:  # 收盘在最低30%区域 → 可能是出货量，排除
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
            if ma_volumes[i] > 0:
                day_shrink = 1 - (day_vol / ma_volumes[i])
            else:
                day_shrink = 0

            # 检查价格: 是否在均线上方
            if ma_prices[j] is None:
                continue
            above_ma = kline[j]["close"] >= ma_prices[j] * 0.98  # 允许2%偏差
            if not above_ma:
                continue

            # 检查是否止跌 (缩量+小实体)
            candle_body = abs(kline[j]["close"] - kline[j]["open"])
            if candle_body / kline[j]["close"] < 0.04:  # 小实体
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


# ═══════════════════════════════════════════════
# 输出
# ═══════════════════════════════════════════════

def print_report(results: list, watchlist_signals: list, near_misses: list = None):
    """格式化输出 B 点信号报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    print(f"\n{'='*60}")
    print(f"  3倍量B点 — 信号报告")
    print(f"  {now}")
    print(f"{'='*60}")

    if not results:
        print("\n  当前无符合条件的B点信号。")
    else:
        # 持仓信号优先展示
        if watchlist_signals:
            print(f"\n  ▶ 持仓B点信号 ({len(watchlist_signals)}只)")
            print(f"  {'-'*56}")
            for s in watchlist_signals:
                print(f"  {s['name']}({s['code']})  ⚡B点确认")
                print(f"    倍量: {s['signal_date']}  {s['volume_ratio']}x 均量")
                print(f"    缩量: {s['b_point_date']}  回缩 {s['shrink_pct']}%")
                print(f"    价格: {s['current_price']}  20MA: {s['ma_price']}")
                print(f"    回踩: {s['bounce_pct']}%")
                print()

        # 全市场信号
        others = [r for r in results if r.get("name", "") not in [s.get("name", "") for s in watchlist_signals]]
        if others:
            print(f"\n  ▶ 其他符合条件的信号 ({len(others)}只)")
            print(f"  {'-'*56}")
            for s in others[:10]:
                print(f"  {s.get('name', '?')}({s.get('code', '?')})")
                print(f"    B点: {s.get('b_point_date', '?')}  倍量: {s.get('volume_ratio', '?')}x")
                print(f"    价格: {s.get('current_price', '?')}  20MA: {s.get('ma_price', '?')}")
                print()

        if len(others) > 10:
            print(f"  ... 还有 {len(others) - 10} 只，见信号文件\n")

    # 近信号展示（未完全达标但接近的）
    if near_misses:
        print(f"\n  ▶ 接近信号 (2.0-2.99x, 仅差临门一脚) — {len(near_misses)}只")
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


# ═══════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════

def scan_stock(code: str, name: str = "") -> Optional[dict]:
    """扫描单只股票，返回信号或None"""
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
    """检测接近3倍量但未完全满足条件的股票（潜力观察）"""
    kline = fetch_kline(code)
    if not kline or len(kline) < MA_PERIOD + 5:
        return None

    # 计算20日均量
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
    raw = sys.argv[1:] if len(sys.argv) > 1 else []
    codes = []
    for c in raw:
        codes.extend([x.strip() for x in c.split(",") if x.strip()])

    if codes:
        # 扫描指定股票
        all_codes = codes
        named = {}
        for c, n in WATCHLIST:
            named[c] = n
        results = []
        for code in all_codes:
            code = code.strip()
            name = named.get(code, "")
            print(f"  扫描 {name or code}...", end=" ", flush=True)
            sig = scan_stock(code, name)
            if sig:
                print("✓ B点")
                results.append(sig)
            else:
                print("—")
            time.sleep(0.3)
    else:
        # 默认扫描持仓
        print(f"\n  ▶ 扫描持仓...")
        results = []
        for code, name in WATCHLIST:
            print(f"    {name}({code})...", end=" ", flush=True)
            sig = scan_stock(code, name)
            if sig:
                print("⚡B点")
                results.append(sig)
            else:
                print("—")
            time.sleep(0.3)

    if not codes:
        # 扩展扫描（这里可添加板块龙头扫描，暂略）
        pass

    # 扫描接近信号（潜力观察）
    print(f"\n  ▶ 扫描接近信号(2-3x倍量潜力)...")
    near_misses_list = []
    nm_scanned = {s.get("code") for s in results}
    for code, name in WATCHLIST:
        if code in nm_scanned:
            continue
        mn = scan_near_miss(code, name)
        if mn:
            near_misses_list.append(mn)
        time.sleep(0.15)

    # 分类输出
    watchlist_signals = [s for s in results if s.get("code") in {c for c, _ in WATCHLIST}]
    print_report(results, watchlist_signals, near_misses_list)


if __name__ == "__main__":
    main()
