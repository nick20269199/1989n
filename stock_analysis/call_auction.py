#!/usr/bin/env python3
"""
集合竞价数据采集 — 工作日 9:26 执行
=====================================
A股集合竞价 9:15-9:25，9:25 产生开盘价，9:26 数据可用。

采集内容:
  1. 竞价涨跌分布 (涨幅>0 / 跌幅>0 / 平盘)
  2. 竞价涨停/跌停封单
  3. 概念板块竞价表现
  4. 行业板块竞价表现
  5. 昨日连板股今日竞价
  6. 竞价资金方向 (量价分析)
  7. 持仓股竞价

存储: JSON + 飞书推送
"""

from error_capture import trap; trap()

import json
import logging
import os
import sys
import time
import traceback
from datetime import datetime, time as dt_time, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

from config import (
    STOCK_DATA_DIR, HEADERS, EASTMONEY_QUOTE_URL,
    FEISHU_WEBHOOK_URL,
)

# ── 后备数据通道 ──────────────────────────────────────────────
try:
    from data_source_router import tencent_quotes, sina_quotes
    _FALLBACK_OK = True
except ImportError:
    _FALLBACK_OK = False

    def tencent_quotes(codes): return {}
    def sina_quotes(codes): return {}

# ── 可选依赖 ─────────────────────────────────────────────────────
try:
    from feishu_sender import send_feishu_message
    _FEISHU_OK = True
except ImportError:
    _FEISHU_OK = False

try:
    from database import save_auction_data, batch_check_auction_volume
    from l2_parser import sync_l2_to_db
    _DB_OK = True
except ImportError:
    _DB_OK = False

    def save_auction_data(data): pass
    def batch_check_auction_volume(data, **kw): return []
    def sync_l2_to_db(code): return {"status": "import_error"}

# ── 日志 ─────────────────────────────────────────────────────────
CST = timezone(timedelta(hours=8))
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("call_auction")
logger.setLevel(logging.DEBUG)

fh = logging.FileHandler(LOG_DIR / "call_auction.log", encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)
logger.addHandler(ch)

# ── 常量 ─────────────────────────────────────────────────────────
TIMEOUT = 15
MAX_RETRIES = 2
DATA_GAP_DIR = Path(STOCK_DATA_DIR).parent / "logs" / "data_gaps"

def now_cst() -> datetime:
    return datetime.now(CST)

def ts_now() -> str:
    return now_cst().strftime("%Y-%m-%d %H:%M:%S")

def ts_compact() -> str:
    return now_cst().strftime("%Y%m%d_%H%M")

def safe_get(url: str, params: dict = None, timeout: int = TIMEOUT) -> Optional[requests.Response]:
    for attempt in range(MAX_RETRIES + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(1 * (attempt + 1))
            else:
                logger.warning(f"请求失败: {url[:100]} — {e}")
    return None

def _prefix(code: str) -> str:
    return "0" if code.startswith(("0", "3")) else "1"


# ═══════════════════════════════════════════════════════════════════
#  1. 竞价涨跌分布 (全市场广度)
# ═══════════════════════════════════════════════════════════════════

def _fetch_page(fs: str, pn: int, po: int = 1, pz: int = 100) -> list:
    r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
        "pn": pn, "pz": pz, "po": po, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": fs,
        "fields": "f2,f3,f12,f14",
    })
    if r and r.json().get("data"):
        return r.json()["data"].get("diff", [])
    return []


def _safe_float(v, default=0.0) -> float:
    """API返回的f3可能是数字或字符串"""
    if v is None:
        return default
    try:
        return float(v)
    except (ValueError, TypeError):
        return default


def fetch_auction_breadth() -> dict:
    """
    全市场竞价涨跌分布 — 精确计数涨停/跌停 + 采样估算涨跌比

    策略:
     - 涨停: 涨幅榜第1页，若第100只<9.8%则计数精确(通常如此)
     - 跌停: 跌幅榜第1页，同理
     - 涨跌比: 取涨幅榜第2页(排名101-200)统计，此处通常是微涨微跌交界区
    """
    result = {"up": 0, "down": 0, "flat": 0, "limit_up": 0, "limit_down": 0,
              "total": 0, "avg_change": 0.0, "details": []}
    try:
        fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"

        # 1. 总数 + 涨幅前100
        top_r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
            "pn": 1, "pz": 100, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2, "fid": "f3",
            "fs": fs,
            "fields": "f2,f3,f12,f14",
        })
        if not top_r or not top_r.json().get("data"):
            return result
        top_data = top_r.json()["data"]
        total = top_data.get("total", 0)
        top_items = top_data.get("diff", [])
        result["total"] = total

        # 统计涨幅前100: 涨停 + 涨家数
        zt = 0
        top_pos = 0
        for it in top_items:
            chg = _safe_float(it.get("f3"))
            if chg >= 9.8:
                zt += 1
            if chg > 0:
                top_pos += 1

        time.sleep(0.3)

        # 2. 跌幅前100
        bot_items = _fetch_page(fs, pn=1, po=0)
        dt = 0
        bot_neg = 0
        for it in bot_items:
            chg = _safe_float(it.get("f3"))
            if chg <= -9.8:
                dt += 1
            if chg < 0:
                bot_neg += 1

        # 如果涨停在第100名还没结束，说明涨停太多，需要继续扫
        # 但涨停>100只的极端行情极少见，先不处理
        result["limit_up"] = zt
        result["limit_down"] = dt

        # 3. 双采样点估算涨跌比
        # 取12.5%分位(≈第7页) + 50%分位(≈第28页)双点平均
        # 避免单点受排序位置影响过大的问题
        sample_pages = [max(2, total // 800), max(2, total // 200)]
        ratios = []
        all_mid_chgs = []
        for sp in sample_pages:
            time.sleep(0.2)
            items = _fetch_page(fs, pn=sp, po=1)
            if items:
                up = sum(1 for i in items if _safe_float(i.get("f3")) > 0)
                down = sum(1 for i in items if _safe_float(i.get("f3")) < 0)
                t = up + down
                if t > 0:
                    ratios.append(up / t)
                all_mid_chgs.extend([_safe_float(i.get("f3")) for i in items if i.get("f3") is not None])

        if ratios:
            ratio = sum(ratios) / len(ratios)
            # 极端行情下向50%收缩，避免单边外推崩盘
            ratio = max(0.2, min(0.8, ratio))
        else:
            ratio = 0.5

        if all_mid_chgs:
            result["avg_change"] = round(sum(all_mid_chgs) / len(all_mid_chgs), 2)

        # 外推: 剩余股票(总数-已知zt-dt)按比例分配
        rest = total - zt - dt
        result["up"] = int(rest * ratio)
        result["down"] = int(rest * (1 - ratio))
        result["flat"] = max(0, total - result["up"] - result["down"] - zt - dt)


        # 详情: 涨幅前20
        result["details"] = [
            {"code": str(it.get("f12", "")).zfill(6),
             "name": it.get("f14", ""),
             "change_pct": _safe_float(it.get("f3"))}
            for it in top_items[:20]
        ]

        logger.info(f"[竞价] 广度: 涨{result['up']} 跌{result['down']} "
                    f"平{result['flat']} 涨停{result['limit_up']} 跌停{result['limit_down']} "
                    f"均涨{result['avg_change']:.2f}%")
    except Exception as e:
        logger.warning(f"[竞价] 广度获取失败: {e}")
        import traceback
        traceback.print_exc()
    return result


# ═══════════════════════════════════════════════════════════════════
#  2. 概念板块竞价表现
# ═══════════════════════════════════════════════════════════════════

def fetch_auction_concepts() -> list[dict]:
    """概念板块竞价涨跌 (9:26 可用)"""
    concepts = []
    try:
        # Top 10 涨幅概念
        r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
            "pn": 1, "pz": 10, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2,
            "fid": "f3", "fs": "m:90+t:3",
            "fields": "f2,f3,f8,f12,f14,f104,f128",
        })
        if r:
            for it in r.json().get("data", {}).get("diff", []):
                concepts.append({
                    "name": it.get("f14", ""),
                    "change_pct": it.get("f3", 0),
                    "turnover": round(it.get("f8", 0) / 1e8, 2) if it.get("f8") else 0,
                    "leading_stock": it.get("f128", ""),
                    "leading_pct": it.get("f104", 0),
                })
        logger.info(f"[竞价] 概念板块: {len(concepts)} 个")
    except Exception as e:
        logger.warning(f"[竞价] 概念失败: {e}")
    return concepts


# ═══════════════════════════════════════════════════════════════════
#  3. 行业板块竞价表现
# ═══════════════════════════════════════════════════════════════════

def fetch_auction_industries() -> list[dict]:
    """行业板块竞价涨跌 + 资金方向"""
    industries = []
    try:
        r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
            "pn": 1, "pz": 15, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2,
            "fid": "f3", "fs": "m:90+t:2",
            "fields": "f2,f3,f8,f12,f14,f62,f184,f128",
        })
        if r:
            for it in r.json().get("data", {}).get("diff", []):
                industries.append({
                    "name": it.get("f14", ""),
                    "change_pct": it.get("f3", 0),
                    "turnover": round(it.get("f8", 0) / 1e8, 2) if it.get("f8") else 0,
                    "main_net_inflow": round(it.get("f62", 0) / 1e8, 2) if it.get("f62") else 0,
                    "leading_stock": it.get("f128", ""),
                })
        logger.info(f"[竞价] 行业板块: {len(industries)} 个")
    except Exception as e:
        logger.warning(f"[竞价] 行业失败: {e}")
    return industries


# ═══════════════════════════════════════════════════════════════════
#  4. 涨停/跌停竞价封单
# ═══════════════════════════════════════════════════════════════════

def fetch_auction_limit_orders() -> dict:
    """竞价涨停封单 — 昨日涨停股今日竞价表现"""
    result = {"limit_up_strength": [], "limit_down_pressure": []}
    try:
        # 涨幅接近涨停的个股竞价情况
        r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
            "pn": 1, "pz": 50, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f5,f6,f8,f10,f12,f14,f20,f21",
        })
        if r:
            zt_list = []
            dt_list = []
            for it in r.json().get("data", {}).get("diff", []):
                chg = it.get("f3", 0) or 0
                if chg >= 9.8:
                    zt_list.append({
                        "code": str(it.get("f12", "")).zfill(6),
                        "name": it.get("f14", ""),
                        "price": it.get("f2", 0),
                        "change_pct": chg,
                        "volume": it.get("f5", 0),
                        "amount": round(it.get("f6", 0) / 1e8, 2) if it.get("f6") else 0,
                        "volume_ratio": it.get("f10", 0),
                        "turnover_rate": it.get("f8", 0),
                        "market_cap": round(it.get("f20", 0) / 1e8, 2) if it.get("f20") else 0,
                    })
                elif chg <= -9.8:
                    dt_list.append({
                        "code": str(it.get("f12", "")).zfill(6),
                        "name": it.get("f14", ""),
                        "price": it.get("f2", 0),
                        "change_pct": chg,
                        "volume": it.get("f5", 0),
                    })
            result["limit_up_strength"] = zt_list[:20]
            result["limit_down_pressure"] = dt_list[:10]

        logger.info(f"[竞价] 涨停{len(result['limit_up_strength'])}只 "
                    f"跌停{len(result['limit_down_pressure'])}只")
    except Exception as e:
        logger.warning(f"[竞价] 封单获取失败: {e}")
    return result


# ═══════════════════════════════════════════════════════════════════
#  5. 持仓竞价
# ═══════════════════════════════════════════════════════════════════

def load_portfolio() -> list[dict]:
    pf = Path(__file__).parent / "data" / "portfolio.json"
    if pf.exists():
        try:
            data = json.loads(pf.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("holdings", [])
        except Exception:
            pass
    return [
        {"code": "002156", "name": "通富微电", "shares": 2300, "cost": 49.787, "sector": "半导体封测"},
        {"code": "000062", "name": "深圳华强", "shares": 2000, "cost": 36.884, "sector": "华为昇腾/电子元器件分销"},
        {"code": "300480", "name": "光力科技", "shares": 700, "cost": 36.289, "sector": "半导体设备"},
        {"code": "002407", "name": "多氟多", "shares": 400, "cost": 35.60, "sector": "锂电化工/氟化工"},
        {"code": "002328", "name": "新朋股份", "shares": 600, "cost": 10.60, "sector": "汽车零部件/半导体"},
        {"code": "002261", "name": "拓维信息", "shares": 100, "cost": 35.04, "sector": "华为昇腾/国产算力"},
        {"code": "300739", "name": "明阳电路", "shares": 100, "cost": 29.727, "sector": "PCB印制电路板"},
    ]


def fetch_auction_detail(code: str) -> Optional[dict]:
    """
    [A方案] 从 push2 API 获取逐笔委托明细，解析竞价全过程。

    details/get 返回格式: "time,price,volume,unk,type"
      type=1: 买盘委托
      type=2: 卖盘委托
      type=4: 竞价虚拟撮合

    返回:
      {code, name, auction_price, prev_close, auction_chg_pct,
       open_volume, match_volume, match_amount,
       auction_high, auction_low, auction_trend: [{time,price,vol,type}],
       buy_orders, sell_orders, source: "push2_api"}
    """
    secid = f"{_prefix(code)}.{code}"
    try:
        r = safe_get("https://push2.eastmoney.com/api/qt/stock/details/get", params={
            "secid": secid,
            "fields1": "f1,f2,f3,f4",
            "fields2": "f51,f52,f53,f54,f55",
            "pos": "0",
            "ut": "fa5fd1943c7b386f172d6893dbd97f6b",
        })
        if not r or not r.json().get("data"):
            return None

        data = r.json()["data"]
        details = data.get("details", [])
        if not details:
            return None

        # 解析竞价时段 (09:15-09:26)
        auction_trend = []
        buy_orders = []
        sell_orders = []
        match_price = None
        match_volume = 0
        match_amount = 0.0
        auction_high = 0.0
        auction_low = 999999.0

        for d in details:
            parts = d.split(",")
            time_str = parts[0]
            if not ("09:15" <= time_str <= "09:26"):
                continue
            price = float(parts[1])
            volume = int(parts[2])
            typ = int(parts[3]) if len(parts) > 3 else 0

            point = {"time": time_str, "price": price, "volume": volume, "type": typ}
            auction_trend.append(point)

            if "09:25" <= time_str <= "09:26":
                if match_price is None:
                    match_price = price
                match_volume += volume
                match_amount += price * volume
            else:
                if typ == 1:
                    buy_orders.append(point)
                elif typ == 2:
                    sell_orders.append(point)

            if price > auction_high:
                auction_high = price
            if price < auction_low:
                auction_low = price

        if match_price is None and auction_trend:
            match_price = auction_trend[-1]["price"]
            match_volume = auction_trend[-1]["volume"]

        if auction_low == 999999.0:
            auction_low = match_price or 0

        # 取前收盘价
        prev_close = data.get("prePrice", 0) or 0
        if prev_close == 0 and match_price:
            prev_close = match_price
        change_pct = ((match_price - prev_close) / prev_close * 100) if prev_close else 0

        return {
            "code": code,
            "name": data.get("name", ""),
            "auction_price": round(match_price, 2) if match_price else 0,
            "prev_close": round(prev_close, 2),
            "auction_chg_pct": round(change_pct, 2),
            "open_volume": match_volume,
            "match_volume": match_volume,
            "match_amount": round(match_amount, 2),
            "auction_high": round(auction_high, 2),
            "auction_low": round(auction_low, 2),
            "auction_trend": auction_trend,
            "buy_orders": len(buy_orders),
            "sell_orders": len(sell_orders),
            "source": "push2_api",
        }
    except Exception as e:
        logger.warning(f"[A方案] {code} API竞价明细失败: {e}")
        return None


def fetch_portfolio_auction(holdings: list[dict]) -> list[dict]:
    """
    获取持仓股竞价表现。
    优先用 A 方案 (push2 details API → 完整竞价过程)，
    A 方案失败则回退到 B 方案 (腾讯行情API)，
    B 方案失败则回退到 C 方案 (新浪行情API)。
    """
    results = []
    for h in holdings:
        code = h["code"]

        # A 方案: 竞价明细 API (东财 push2)
        detail = fetch_auction_detail(code)
        if detail:
            detail["sector"] = h.get("sector", "")
            detail["shares"] = h.get("shares", 0)
            detail["_source"] = "A"
            results.append(detail)
            continue

        # B 方案: 腾讯行情 API
        if _FALLBACK_OK:
            try:
                q = tencent_quotes([code])
                if code in q:
                    d = q[code]
                    prev_close = d.get('prev_close', 0)
                    cur = d.get('current', 0)
                    change_pct = ((cur - prev_close) / prev_close * 100) if prev_close else 0
                    results.append({
                        "code": code,
                        "name": d.get('name', h.get('name', '')),
                        "auction_price": round(cur, 2),
                        "prev_close": round(prev_close, 2),
                        "auction_chg_pct": round(change_pct, 2),
                        "open_volume": d.get('volume', 0),
                        "sector": h.get("sector", ""),
                        "shares": h.get("shares", 0),
                        "_source": "B",
                    })
                    logger.info(f"[B方案/腾讯] {code} 获取成功")
                    continue
            except Exception as e:
                logger.warning(f"[B方案/腾讯] {code} 失败: {e}")

        # C 方案: 新浪行情 API
        if _FALLBACK_OK:
            try:
                q = sina_quotes([code])
                if code in q:
                    d = q[code]
                    prev_close = d.get('prev_close', 0)
                    cur = d.get('current', 0)
                    change_pct = ((cur - prev_close) / prev_close * 100) if prev_close else 0
                    results.append({
                        "code": code,
                        "name": d.get('name', h.get('name', '')),
                        "auction_price": round(cur, 2),
                        "prev_close": round(prev_close, 2),
                        "auction_chg_pct": round(change_pct, 2),
                        "open_volume": d.get('volume', 0),
                        "sector": h.get("sector", ""),
                        "shares": h.get("shares", 0),
                        "_source": "C",
                    })
                    logger.info(f"[C方案/新浪] {code} 获取成功")
                    continue
            except Exception as e:
                logger.warning(f"[C方案/新浪] {code} 失败: {e}")

        logger.warning(f"[竞价] {code} 全部通道均失败")
    logger.info(f"[竞价] 持仓: {len(results)}/{len(holdings)} 只 "
                f"(A:{sum(1 for r in results if r.get('_source')=='A')} "
                f"B:{sum(1 for r in results if r.get('_source')=='B')} "
                f"C:{sum(1 for r in results if r.get('_source')=='C')})")
    return results


# ═══════════════════════════════════════════════════════════════════
#  汇总 & 飞书
# ═══════════════════════════════════════════════════════════════════

def build_auction_output(
    breadth: dict, concepts: list[dict], industries: list[dict],
    limit_orders: dict, portfolio_auction: list[dict],
) -> dict:
    return {
        "type": "call_auction",
        "time": ts_now(),
        "date": datetime.now(CST).strftime("%Y-%m-%d"),
        "market_breadth": breadth,
        "concept_auction": concepts,
        "industry_auction": industries,
        "limit_orders": limit_orders,
        "portfolio_auction": portfolio_auction,
    }


def send_auction_feishu(output: dict) -> bool:
    if not FEISHU_WEBHOOK_URL and not _FEISHU_OK:
        return False

    t = now_cst()
    date_str = t.strftime("%m/%d")
    breadth = output.get("market_breadth", {})
    concepts = output.get("concept_auction", [])
    industries = output.get("industry_auction", [])
    limit_orders = output.get("limit_orders", {})
    portfolio = output.get("portfolio_auction", [])

    lines = [
        f"**集合竞价速报** | {date_str} 9:26",
        "",
        "─── **市场广度** ───",
        f"涨: **{breadth.get('up', '-')}** | 跌: {breadth.get('down', '-')} | "
        f"平: {breadth.get('flat', '-')}",
        f"涨停: **{breadth.get('limit_up', '-')}**只 | "
        f"跌停: {breadth.get('limit_down', '-')}只",
        f"均涨幅: {breadth.get('avg_change', 0):.2f}%",
        "",
        "─── **竞价涨停** ───",
    ]
    for zt in limit_orders.get("limit_up_strength", [])[:10]:
        lines.append(
            f"- {zt['name']}({zt['code']}): **{zt['change_pct']:.1f}%** "
            f"| 成交{zt.get('amount','-')}亿 | 量比{zt.get('volume_ratio','-')}"
        )

    lines.append("")
    lines.append("─── **概念竞价 Top 5** ───")
    for c in concepts[:5]:
        lines.append(f"- {c['name']}: **{c['change_pct']:+.2f}%** | 龙头{c.get('leading_stock','')}")

    lines.append("")
    lines.append("─── **行业竞价** ───")
    for ind in industries[:5]:
        net = ind.get("main_net_inflow", 0)
        lines.append(f"- {ind['name']}: {ind['change_pct']:+.2f}% | 资金{net:+.2f}亿")

    lines.append("")
    lines.append("─── **持仓竞价** ───")
    for h in portfolio:
        sign = "+" if h["auction_chg_pct"] >= 0 else ""
        lines.append(
            f"- {h['name']}({h['code']}): {h['auction_price']} "
            f"({sign}{h['auction_chg_pct']:.2f}%)"
        )

    content = "\n".join(lines)
    title = f"集合竞价 | {date_str} 9:26"

    try:
        if _FEISHU_OK:
            ok = send_feishu_message(title=title, content=content)
        else:
            payload = {
                "msg_type": "interactive",
                "card": {
                    "header": {"title": {"tag": "plain_text", "content": title}, "template": "red"},
                    "elements": [{"tag": "div", "text": {"tag": "lark_md", "content": content}}],
                },
            }
            r = requests.post(FEISHU_WEBHOOK_URL, json=payload, timeout=15)
            ok = r.status_code == 200
        logger.info(f"[飞书] {'成功' if ok else '失败'}")
        return ok
    except Exception as e:
        logger.error(f"[飞书] 异常: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
#  数据缺失记录
# ═══════════════════════════════════════════════════════════════════

def _record_data_gap(source: str, channel: str, issue: str, impact: str):
    """记录数据缺失到 data_gaps/，供情报部周审"""
    try:
        DATA_GAP_DIR.mkdir(parents=True, exist_ok=True)
        gap = {
            "date": now_cst().strftime("%Y-%m-%d"),
            "source": source,
            "channel": channel,
            "issue": issue,
            "impact": impact,
            "fallback": "已切换腾讯/新浪通道",
            "recorded_at": ts_now(),
            "severity": "HIGH" if "全部" in impact else "MEDIUM",
        }
        fname = f"{now_cst().strftime('%Y%m%d_%H%M')}_{source}.json"
        (DATA_GAP_DIR / fname).write_text(
            json.dumps(gap, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.warning(f"[数据缺失] 已记录: {source} — {issue}")
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════════════════════════

def main():
    logger.info("=" * 60)
    logger.info(f"集合竞价采集启动 | {ts_now()}")

    now = now_cst()
    if now.weekday() >= 5:
        logger.info("非交易日，跳过")
        return 0

    start = time.time()

    try:
        # 1. 市场广度
        breadth = fetch_auction_breadth()
        if breadth.get("total", 0) == 0:
            _record_data_gap("fetch_auction_breadth", "东方财富 push2",
                             "WAF封锁，全市场竞价涨跌分布采集空", "竞价广度/涨停跌停计数/涨跌比 全部缺失")
        time.sleep(0.3)

        # 2. 概念板块竞价
        concepts = fetch_auction_concepts()
        if not concepts:
            _record_data_gap("fetch_auction_concepts", "东方财富 push2",
                             "WAF封锁，概念板块竞价采集空", "概念板块竞价表现缺失")
        time.sleep(0.3)

        # 3. 行业板块竞价
        industries = fetch_auction_industries()
        if not industries:
            _record_data_gap("fetch_auction_industries", "东方财富 push2",
                             "WAF封锁，行业板块竞价采集空", "行业板块竞价表现缺失")
        time.sleep(0.3)

        # 4. 涨停封单
        limit_orders = fetch_auction_limit_orders()
        if not limit_orders.get("limit_up_strength") and not limit_orders.get("limit_down_pressure"):
            _record_data_gap("fetch_auction_limit_orders", "东方财富 push2",
                             "WAF封锁，涨停/跌停竞价封单采集空", "涨停/跌停封单数据缺失")

        # 5. 持仓竞价
        holdings = load_portfolio()
        portfolio_auction = fetch_portfolio_auction(holdings)

        # 6. 汇总
        output = build_auction_output(
            breadth, concepts, industries, limit_orders, portfolio_auction
        )

        # 7. 存 JSON
        STOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
        fname = f"call_auction_{ts_compact()}.json"
        json_path = STOCK_DATA_DIR / fname
        json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"[JSON] {json_path}")

        # 7a. 竞价数据落库 + 放量信号
        if _DB_OK and portfolio_auction:
            try:
                save_auction_data(portfolio_auction)
                logger.info(f"[DB] 竞价数据写入 {len(portfolio_auction)} 只")
                signals = batch_check_auction_volume(portfolio_auction)
                vol_up = [s for s in signals if s.get("signal") == "放量"]
                vol_down = [s for s in signals if s.get("signal") == "缩量"]
                if vol_up:
                    detail = "; ".join(f"{s['name']}({s['code']}) {s['ratio']}x" for s in vol_up)
                    logger.info(f"[竞价放量] {len(vol_up)} 只: {detail}")
                output["volume_signals"] = signals

                # L2 逐笔成交同步
                l2_signals = []
                for p in portfolio_auction:
                    try:
                        l2 = sync_l2_to_db(p["code"])
                        if l2.get("status") in ("synced", "cached") and l2.get("buy_ratio") is not None:
                            l2_signals.append({
                                "code": p["code"], "name": p.get("name", ""),
                                "l2_buy_ratio": l2["buy_ratio"],
                                "l2_net_flow": l2["net_flow"],
                                "l2_records": l2["records"],
                            })
                    except Exception:
                        pass
                if l2_signals:
                    output["l2_signals"] = l2_signals
                    high_buy = [s for s in l2_signals if s["l2_buy_ratio"] >= 0.6]
                    high_sell = [s for s in l2_signals if s["l2_buy_ratio"] <= 0.4]
                    if high_buy:
                        detail = "; ".join(f"{s['name']}({s['code']}) 买盘{s['l2_buy_ratio']:.0%}" for s in high_buy)
                        logger.info(f"[L2买盘主导] {detail}")
                    if high_sell:
                        detail = "; ".join(f"{s['name']}({s['code']}) 卖盘{(1-s['l2_buy_ratio']):.0%}" for s in high_sell)
                        logger.info(f"[L2卖盘主导] {detail}")
            except Exception as e:
                logger.warning(f"[DB] 竞价落库异常(非关键): {e}")

        # 8. 飞书推送
        send_auction_feishu(output)

        elapsed = time.time() - start
        logger.info(f"集合竞价采集完成 | 耗时 {elapsed:.1f}s")
        return 0

    except Exception as e:
        logger.error(f"集合竞价崩溃: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
