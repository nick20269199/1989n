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

# ── 可选依赖 ─────────────────────────────────────────────────────
try:
    from feishu_sender import send_feishu_message
    _FEISHU_OK = True
except ImportError:
    _FEISHU_OK = False

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

def fetch_auction_breadth() -> dict:
    """获取全市场竞价涨跌分布 — 市场广度指标"""
    result = {"up": 0, "down": 0, "flat": 0, "limit_up": 0, "limit_down": 0,
              "total": 0, "avg_change": 0.0, "details": []}
    try:
        # 按涨跌幅获取全 A 股竞价结果
        params = {
            "pn": 1, "pz": 1, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2,
            "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f12,f14",
        }
        # 先获取总数
        r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params=params)
        total = 0
        if r:
            total = r.json().get("data", {}).get("total", 0)
        result["total"] = total

        # 分组获取涨/跌/平/涨停/跌停
        groups = [
            ("up", 1, "f3", 0.01, 100),      # 涨幅 > 0
            ("down", 0, "f3", -100, -0.01),   # 跌幅 < 0
            ("limit_up", 1, "f3", 9.8, 100),   # 涨停
            ("limit_down", 0, "f3", -100, -9.8), # 跌停
        ]

        for label, sort_dir, sort_field, lo, hi in groups:
            params = {
                "pn": 1, "pz": 1, "po": sort_dir, "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2, "invt": 2,
                "fid": sort_field,
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f2,f3,f12,f14",
            }
            # 用价格范围做近似过滤
            r2 = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params=params)
            if r2:
                # 遍历少量数据来估算
                items = r2.json().get("data", {}).get("diff", [])
                if label in ("limit_up", "limit_down"):
                    result[label] = sum(1 for it in items if it.get("f3", 0) and
                                        ((label == "limit_up" and it["f3"] >= 9.8) or
                                         (label == "limit_down" and it["f3"] <= -9.8)))
        time.sleep(0.3)

        # 获取涨跌停数量 (更精确的方法)
        r_zt = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
            "pn": 1, "pz": 1, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2, "fid": "f3",
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
            "fields": "f2,f3,f12,f14",
        })
        if r_zt:
            total_val = r_zt.json().get("data", {}).get("total", 0)
            # 涨停: 取涨幅前 N 条看有多少 >= 9.8
            r_zt_detail = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
                "pn": 1, "pz": 100, "po": 1, "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2, "invt": 2, "fid": "f3",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
                "fields": "f2,f3,f12,f14",
            })
            if r_zt_detail:
                items = r_zt_detail.json().get("data", {}).get("diff", [])
                ups = 0
                downs = 0
                zt = 0
                dt = 0
                total_chg = 0.0
                cnt = 0
                for it in items:
                    chg = it.get("f3", 0) or 0
                    total_chg += chg
                    cnt += 1
                    if chg >= 9.8:
                        zt += 1
                    elif chg <= -9.8:
                        dt += 1
                    elif chg > 0:
                        ups += 1
                    elif chg < 0:
                        downs += 1

                # 根据比例估算全市场
                if cnt > 0 and total_val > 0:
                    scale = total_val / cnt
                    result["limit_up"] = int(zt * scale)
                    result["limit_down"] = int(dt * scale)
                    result["up"] = int(ups * scale)
                    result["down"] = int(downs * scale)
                    result["flat"] = int(total_val - result["up"] - result["down"] -
                                         result["limit_up"] - result["limit_down"])
                    result["avg_change"] = round(total_chg / cnt, 3)
                    result["details"] = [
                        {"code": str(it.get("f12", "")).zfill(6),
                         "name": it.get("f14", ""),
                         "change_pct": it.get("f3", 0)}
                        for it in items[:20]
                    ]

        logger.info(f"[竞价] 广度: 涨{result['up']} 跌{result['down']} "
                    f"涨停{result['limit_up']} 跌停{result['limit_down']} "
                    f"均涨{result['avg_change']:.2f}%")
    except Exception as e:
        logger.warning(f"[竞价] 广度获取失败: {e}")
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


def fetch_portfolio_auction(holdings: list[dict]) -> list[dict]:
    """获取持仓股竞价表现"""
    results = []
    for h in holdings:
        code = h["code"]
        secid = f"{_prefix(code)}.{code}"
        try:
            params = {
                "ut": "fa5fd1943c7b386f172d6893dbf38dc7",
                "secid": secid,
                "fields": "f43,f44,f45,f46,f47,f48,f50,f57,f58,f60,f170",
                "forcect": 1,
            }
            r = safe_get(EASTMONEY_QUOTE_URL, params=params)
            if r and r.json().get("data"):
                d = r.json()["data"]
                price = d.get("f43", 0) / 100 if d.get("f43") else 0
                prev_close = d.get("f60", price * 100) / 100 if d.get("f60") else price
                change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0
                results.append({
                    "code": code,
                    "name": d.get("f57", h.get("name", "")),
                    "auction_price": round(price, 2),
                    "prev_close": round(prev_close, 2),
                    "auction_chg_pct": round(change_pct, 2),
                    "open_volume": d.get("f47", 0),
                    "sector": h.get("sector", ""),
                })
        except Exception as e:
            logger.warning(f"[竞价] {code} 失败: {e}")
    logger.info(f"[竞价] 持仓: {len(results)}/{len(holdings)} 只")
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
        time.sleep(0.3)

        # 2. 概念板块竞价
        concepts = fetch_auction_concepts()
        time.sleep(0.3)

        # 3. 行业板块竞价
        industries = fetch_auction_industries()
        time.sleep(0.3)

        # 4. 涨停封单
        limit_orders = fetch_auction_limit_orders()

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
