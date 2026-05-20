#!/usr/bin/env python3
"""
盘中情报分析报告 — 每个交易日 9:03-15:03 每30分钟执行
=====================================================
多源新闻 + 市场数据 → 交叉分析 → 结构化情报 → 飞书推送

数据源:
  新闻: 财联社电报 (DB) + 东方财富快讯 (API)
  行情: 东方财富 API (指数/板块/涨跌停/资金流向)
  概念: 东方财富概念板块

采集维度:
  1. 大盘情绪 — 指数 + 涨跌比 + 涨停/跌停/炸板
  2. 资金攻击方向 — 行业资金流入 + 概念涨幅 + 成交额集中度
  3. 新闻驱动 — 最近30分钟快讯 → 关联板块/个股走势
  4. 异动监控 — 突发涨停/跌停 + 量能异动 + 炸板
  5. 持仓观察 — 8只持仓股表现
"""

from error_capture import trap; trap()

import json
import logging
import os
import re
import sqlite3
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

from config import (
    STOCK_DATA_DIR, HEADERS, EASTMONEY_QUOTE_URL,
    DATABASE_PATH, FEISHU_BOT_CHAT_ID, PORTFOLIO_FILE,
)

CST = timezone(timedelta(hours=8))

# ── 日志 ────────────────────────────────────────────────
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("intraday_report")
logger.setLevel(logging.DEBUG)
fh = logging.FileHandler(LOG_DIR / "intraday_report.log", encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

try:
    from feishu_sender import send_feishu_message
    _FEISHU_OK = True
except ImportError:
    _FEISHU_OK = False
    def send_feishu_message(title, content):
        return False

# ── 工具 ────────────────────────────────────────────────

def now() -> datetime:
    return datetime.now(CST)

def _prefix(code: str) -> str:
    return "0" if code.startswith(("0", "3")) else "1"

def safe_get(url: str, params: dict = None, timeout: int = 12, retries: int = 2):
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception:
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    return None

def ei(val) -> float:
    """安全转float，默认0"""
    try:
        return float(val) if val and val != "-" else 0.0
    except (ValueError, TypeError):
        return 0.0

def pct_str(v: float) -> str:
    sign = "+" if v >= 0 else ""
    return f"{sign}{v:.2f}%"

# ── 1. 市场快照 ─────────────────────────────────────────

def fetch_market_snapshot() -> dict:
    """快速获取市场全景 (东方财富 API)"""
    result = {"indices": {}, "breadth": {}, "sectors": [],
              "concepts": [], "limit_up": [], "limit_down": [],
              "top_amount": [], "fund_flow": []}

    # 1.1 指数
    idx_codes = {
        "1.000001": "上证", "0.399001": "深证", "0.399006": "创业板",
        "1.000688": "科创50", "1.000300": "沪深300", "1.000905": "中证500",
    }
    idx_ids = ",".join(idx_codes.keys())
    r = safe_get("https://push2.eastmoney.com/api/qt/ulist.np/get", params={
        "fltt": 2, "invt": 2,
        "fields": "f2,f3,f4,f6",
        "secids": idx_ids,
    })
    if r:
        for item in r.json().get("data", {}).get("diff", []):
            name = idx_codes.get(item.get("f12", ""), "")
            if name:
                result["indices"][name] = {
                    "price": ei(item.get("f2")), "chg_pct": ei(item.get("f3")),
                    "amount": ei(item.get("f6")) / 1e8,
                }

    # 1.2 市场广度 — 用 akshare 获取完整涨跌统计
    try:
        import akshare as ak
        from data_source_router import safe_akshare_call
        spot = safe_akshare_call(ak.stock_zh_a_spot_em)
        up_mask = spot['涨跌幅'] > 0
        down_mask = spot['涨跌幅'] < 0
        zt_mask = spot['涨跌幅'] >= 9.8
        dt_mask = spot['涨跌幅'] <= -9.8
        result["breadth"] = {
            "total": len(spot),
            "up": int(up_mask.sum()),
            "down": int(down_mask.sum()),
            "flat": int((~up_mask & ~down_mask).sum()),
            "limit_up": int(zt_mask.sum()),
            "limit_down": int(dt_mask.sum()),
        }
    except Exception as e:
        logger.warning(f"广度数据获取失败: {e}")
        result["breadth"] = {"total": 0, "up": 0, "down": 0, "flat": 0,
                             "limit_up": 0, "limit_down": 0}

    # 1.2b 涨停/跌停明细
    r2 = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
        "pn": 1, "pz": 50, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f2,f3,f6,f8,f10,f12,f14,f20",
    })
    limit_up_list, limit_down_list = [], []
    if r2:
        for it in r2.json().get("data", {}).get("diff", []):
            chg = ei(it.get("f3"))
            if chg >= 9.8:
                limit_up_list.append({
                    "code": str(it.get("f12", "")).zfill(6),
                    "name": it.get("f14", ""), "chg_pct": chg,
                    "amount": ei(it.get("f6")) / 1e8,
                    "turnover": ei(it.get("f8")),
                    "vol_ratio": ei(it.get("f10")),
                    "mcap": ei(it.get("f20")) / 1e8,
                })
            elif chg <= -9.8:
                limit_down_list.append({
                    "code": str(it.get("f12", "")).zfill(6),
                    "name": it.get("f14", ""), "chg_pct": chg,
                })
    result["limit_up"] = limit_up_list[:15]
    result["limit_down"] = limit_down_list[:5]

    # 1.3 成交额 TOP10
    r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
        "pn": 1, "pz": 10, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f6",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f2,f3,f6,f8,f10,f12,f14",
    })
    if r:
        for it in r.json().get("data", {}).get("diff", []):
            result["top_amount"].append({
                "name": it.get("f14", ""),
                "code": str(it.get("f12", "")).zfill(6),
                "price": ei(it.get("f2")),
                "chg_pct": ei(it.get("f3")),
                "amount": ei(it.get("f6")) / 1e8,
                "turnover": ei(it.get("f8")),
                "vol_ratio": ei(it.get("f10")),
            })

    # 1.4 行业板块 TOP8
    r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
        "pn": 1, "pz": 8, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": "m:90+t:2",
        "fields": "f2,f3,f8,f14,f62,f128",
    })
    if r:
        for it in r.json().get("data", {}).get("diff", []):
            result["sectors"].append({
                "name": it.get("f14", ""),
                "chg_pct": ei(it.get("f3")),
                "amount": ei(it.get("f8")) / 1e8,
                "net_inflow": ei(it.get("f62")) / 1e8,
                "leader": it.get("f128", ""),
            })

    # 1.5 概念板块 TOP10
    r = safe_get("https://push2.eastmoney.com/api/qt/clist/get", params={
        "pn": 1, "pz": 10, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": "m:90+t:3",
        "fields": "f2,f3,f14,f104,f128",
    })
    if r:
        for it in r.json().get("data", {}).get("diff", []):
            result["concepts"].append({
                "name": it.get("f14", ""),
                "chg_pct": ei(it.get("f3")),
                "leader": it.get("f128", ""),
                "leader_pct": ei(it.get("f104")),
            })

    return result


# ── 2. 新闻采集 ─────────────────────────────────────────

def fetch_recent_news(minutes: int = 60) -> list[dict]:
    """从数据库读取最近 N 分钟的新闻"""
    try:
        db_path = DATABASE_PATH
        if not os.path.exists(db_path):
            logger.warning(f"数据库不存在: {db_path}")
            return []

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, pub_time, related_stocks, category, source "
            "FROM news WHERE pub_time > datetime('now', 'localtime', ?) "
            "ORDER BY pub_time DESC LIMIT 80",
            (f"-{minutes} minutes",)
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.warning(f"新闻读取失败: {e}")
        return []


def fetch_cls_live() -> list[dict]:
    """从财联社 API 直接获取最新快讯 (备用)"""
    news = []
    try:
        r = safe_get("https://www.cls.cn/nodeapi/telegraphList",
                     params={"rn": 30, "pn": 0, "subscribed": 0}, timeout=10)
        if r and r.json().get("error") == 0:
            for item in r.json().get("data", {}).get("roll_data", []):
                title = item.get("title", "")
                if title:
                    news.append({
                        "title": title,
                        "time": datetime.fromtimestamp(item.get("ctime", 0), tz=CST).strftime("%H:%M"),
                        "stocks": [s.get("code", "") for s in item.get("stock_list", []) or []],
                        "subjects": item.get("subject", []) or [],
                    })
    except Exception as e:
        logger.warning(f"财联社实时获取失败: {e}")
    return news


# ── 3. 交叉分析 ─────────────────────────────────────────

# 高频词 → 关联概念板块映射
KEYWORD_CONCEPT_MAP = {
    "AI": "人工智能", "人工智能": "人工智能", "大模型": "人工智能",
    "算力": "算力概念", "GPU": "算力概念", "芯片": "半导体",
    "半导体": "半导体", "光刻": "半导体", "封装": "半导体封测",
    "机器人": "机器人概念", "具身智能": "机器人概念",
    "低空": "低空经济", "飞行汽车": "低空经济", "eVTOL": "低空经济",
    "固态电池": "固态电池", "锂电池": "锂电池", "锂电": "锂电池",
    "光伏": "光伏", "储能": "储能", "风电": "风电",
    "医药": "医药", "创新药": "创新药", "医疗器械": "医疗器械",
    "消费": "大消费", "白酒": "白酒", "食品": "食品饮料",
    "房地产": "房地产", "地产": "房地产",
    "汽车": "汽车整车", "新能源车": "新能源汽车", "自动驾驶": "无人驾驶",
    "游戏": "游戏", "短剧": "短剧互动游戏", "传媒": "文化传媒",
    "电力": "电力", "发电": "绿色电力", "电网": "智能电网",
    "数据": "数据要素", "信创": "信创", "国产软件": "国产软件",
    "军工": "军工", "航天": "航天航空",
    "有色": "有色金属", "稀土": "稀土永磁", "黄金": "黄金概念",
    "化工": "化工", "钢铁": "钢铁", "煤炭": "煤炭",
    "金融": "金融", "银行": "银行", "券商": "券商", "保险": "保险",
    "PCB": "PCB", "印制电路": "PCB",
}

# 概念→行业联动
CONCEPT_SECTOR_MAP = {
    "半导体": "半导体", "芯片": "半导体", "算力": "IT服务",
    "AI": "IT服务", "机器人": "通用设备", "低空经济": "航空装备",
    "固态电池": "电池", "锂电池": "电池", "光伏": "光伏设备",
    "游戏": "游戏", "地产": "房地产开发",
}

def extract_themes(news_list: list[dict]) -> Counter:
    """从新闻标题中提取最热门题材"""
    themes = Counter()
    for n in news_list:
        title = n.get("title", "")
        for kw, theme in KEYWORD_CONCEPT_MAP.items():
            if kw in title:
                themes[theme] += 1
    return themes


def find_catalysts(news_list: list[dict], concepts: list[dict]) -> list[dict]:
    """找新闻催化 → 概念涨跌的因果关系"""
    catalyst_map = {}
    for c in concepts:
        catalyst_map[c["name"]] = {"concept": c, "news_count": 0, "news_titles": []}

    for n in news_list:
        title = n.get("title", "")
        for kw, theme in KEYWORD_CONCEPT_MAP.items():
            if kw in title and theme in catalyst_map:
                catalyst_map[theme]["news_count"] += 1
                if len(catalyst_map[theme]["news_titles"]) < 3:
                    catalyst_map[theme]["news_titles"].append(title[:60])

    # 按概念涨幅排序，新闻催化>0的排前面
    result = sorted(
        [v for v in catalyst_map.values() if v["news_count"] > 0],
        key=lambda x: x["concept"]["chg_pct"], reverse=True
    )
    return result[:8]


# ── 4. 持仓分析 ─────────────────────────────────────────

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
        {"code": "002156", "name": "通富微电", "shares": 2300, "cost": 49.787},
        {"code": "000062", "name": "深圳华强", "shares": 2000, "cost": 36.884},
        {"code": "300480", "name": "光力科技", "shares": 700, "cost": 36.289},
        {"code": "002407", "name": "多氟多", "shares": 400, "cost": 35.60},
        {"code": "002328", "name": "新朋股份", "shares": 600, "cost": 10.60},
        {"code": "002261", "name": "拓维信息", "shares": 100, "cost": 35.04},
        {"code": "300739", "name": "明阳电路", "shares": 100, "cost": 29.727},
    ]


def fetch_portfolio_status(holdings: list[dict]) -> list[dict]:
    """获取持仓股实时行情"""
    results = []
    codes = [h["code"] for h in holdings]
    code_str = ",".join(f"{_prefix(c)}.{c}" for c in codes)

    r = safe_get("https://push2.eastmoney.com/api/qt/ulist.np/get", params={
        "fltt": 2, "invt": 2,
        "fields": "f2,f3,f6,f8,f10,f12,f14",
        "secids": code_str,
    })
    if r:
        quotes = {}
        for item in r.json().get("data", {}).get("diff", []):
            quotes[str(item.get("f12", "")).zfill(6)] = {
                "price": ei(item.get("f2")),
                "chg_pct": ei(item.get("f3")),
                "amount": ei(item.get("f6")) / 1e8,
                "turnover": ei(item.get("f8")),
                "vol_ratio": ei(item.get("f10")),
            }

        for h in holdings:
            q = quotes.get(h["code"], {})
            price = q.get("price", 0)
            cost = h.get("cost", 0)
            pnl_pct = ((price - cost) / cost * 100) if cost > 0 else 0
            results.append({
                "code": h["code"],
                "name": h.get("name", ""),
                "price": price,
                "chg_pct": q.get("chg_pct", 0),
                "pnl_pct": round(pnl_pct, 2),
                "amount": q.get("amount", 0),
                "turnover": q.get("turnover", 0),
                "vol_ratio": q.get("vol_ratio", 0),
            })

    return results


# ── 5. 报告生成 ─────────────────────────────────────────

def generate_report(snapshot: dict, catalysts: list, news: list,
                    portfolio: list, hot_themes: Counter) -> str:
    t = now()
    b = snapshot.get("breadth", {})
    idx = snapshot.get("indices", {})

    lines = [
        f"# 盘中情报 | {t.strftime('%m/%d %H:%M')}",
        "",
    ]

    # ── 早间回顾（三线打通）──
    try:
        from stage_context import morning_summary
        ms = morning_summary()
        if ms:
            lines.append(ms)
    except ImportError:
        pass

    # ── 大盘 ──
    lines.append("## 大盘")
    idx_str = " | ".join(
        f"{k} {v['price']:.2f} ({pct_str(v['chg_pct'])})"
        for k, v in idx.items()
    )
    lines.append(f"{idx_str}")
    up_n = b.get('up','?')
    down_n = b.get('down','?')
    zt_n = b.get('limit_up','?')
    dt_n = b.get('limit_down','?')
    ratio = f"{up_n/(max(down_n,1) if isinstance(down_n,int) else 1):.2f}" if isinstance(up_n,int) and isinstance(down_n,int) else "?"
    lines.append(f"涨 **{up_n}** | 跌 {down_n} | "
                 f"涨停 **{zt_n}** | 跌停 {dt_n} | "
                 f"涨跌比 {ratio}")
    lines.append("")

    # ── 资金攻击方向 ──
    lines.append("## 资金攻击方向")
    sectors = snapshot.get("sectors", [])
    if sectors:
        top_sec = sectors[:5]
        lines.append("| 行业 | 涨幅 | 资金(亿) | 龙头 |")
        lines.append("|------|------|----------|------|")
        for s in top_sec:
            net = s.get("net_inflow", 0)
            lines.append(f"| {s['name']} | {pct_str(s['chg_pct'])} "
                         f"| {net:+.2f} | {s.get('leader','')} |")
    lines.append("")

    # ── 题材催化 (新闻→市场) ──
    lines.append("## 题材催化 (新闻→涨幅)")
    if catalysts:
        for cat in catalysts[:5]:
            c = cat["concept"]
            lines.append(
                f"- **{c['name']}** {pct_str(c['chg_pct'])} "
                f"龙头 {c.get('leader','')} | "
                f"相关新闻 {cat['news_count']} 条"
            )
            for nt in cat["news_titles"][:2]:
                lines.append(f"  · {nt}")
    else:
        lines.append("无显著新闻催化题材")
    lines.append("")

    # ── 热门题材 ──
    lines.append("## 热门题材 TOP6")
    concepts = snapshot.get("concepts", [])
    for c in concepts[:6]:
        lines.append(f"- {c['name']}: {pct_str(c['chg_pct'])} "
                     f"(龙头 {c.get('leader','')})")
    lines.append("")

    # ── 成交额 TOP5 ──
    lines.append("## 成交额 TOP5")
    for s in snapshot.get("top_amount", [])[:5]:
        lines.append(f"- {s['name']}({s['code']}) {s['price']:.2f} "
                     f"{pct_str(s['chg_pct'])} | {s['amount']:.1f}亿 "
                     f"量比{s['vol_ratio']:.1f}")
    lines.append("")

    # ── 涨停观察 ──
    zt = snapshot.get("limit_up", [])
    if zt:
        lines.append(f"## 涨停股 ({len(zt)}只筛选)")
        for s in zt[:8]:
            lines.append(f"- **{s['name']}**(涨停) 换手{s['turnover']:.1f}% "
                         f"量比{s['vol_ratio']:.1f} | 成交{s['amount']:.1f}亿")
    lines.append("")

    # ── 跌停 ──
    dt = snapshot.get("limit_down", [])
    if dt:
        lines.append("## 跌停股")
        for s in dt:
            lines.append(f"- {s['name']}: {s['chg_pct']:.1f}%")
        lines.append("")

    # ── 持仓 ──
    if portfolio:
        lines.append("## 持仓")
        lines.append("| 股票 | 现价 | 日内 | 盈亏 | 量比 |")
        lines.append("|------|------|------|------|------|")
        for h in portfolio:
            lines.append(
                f"| {h['name']}({h['code']}) | {h['price']:.2f} | "
                f"{pct_str(h['chg_pct'])} | {pct_str(h['pnl_pct'])} | "
                f"{h['vol_ratio']:.1f} |"
            )
        lines.append("")

    # ── 快讯 ──
    if news:
        lines.append(f"## 快讯 ({len(news)}条)")
        for n in news[:8]:
            t_str = n.get("time", n.get("pub_time", ""))
            if len(t_str) >= 16:
                t_str = t_str[11:16]
            lines.append(f"- [{t_str}] {n['title'][:80]}")
        lines.append("")

    lines.append(f"---")
    lines.append(f"*自动采集 | {t.strftime('%m/%d %H:%M:%S')}*")

    return "\n".join(lines)


# ── 6. 飞书推送 ─────────────────────────────────────────

def send_to_feishu(report: str) -> bool:
    if not _FEISHU_OK and not FEISHU_BOT_CHAT_ID:
        return False
    t = now()
    title = f"盘中情报 | {t.strftime('%m/%d %H:%M')}"
    try:
        ok = send_feishu_message(title=title, content=report)
        return ok
    except Exception as e:
        logger.error(f"飞书推送失败: {e}")
        return False


# ── 主入口 ──────────────────────────────────────────────

def main():
    start = time.time()
    t = now()

    # 交易日检查
    if t.weekday() >= 5:
        logger.info("非交易日，跳过")
        return

    # 交易时段检查 (9:30-11:30, 13:00-15:00)
    ti = t.time()
    from datetime import time as dt_time
    in_morning = dt_time(9, 0) <= ti <= dt_time(11, 30)
    in_afternoon = dt_time(13, 0) <= ti <= dt_time(15, 10)
    if not (in_morning or in_afternoon):
        logger.info(f"非交易时段 ({t.strftime('%H:%M')})，跳过")
        return

    logger.info(f"盘中情报采集启动 | {t.strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 市场快照
    snapshot = fetch_market_snapshot()
    time.sleep(0.3)

    # 2. 新闻: 优先 DB，备用 API
    news_db = fetch_recent_news(minutes=60)
    news_api = fetch_cls_live() if len(news_db) < 10 else []
    # 合并去重
    seen = set(n.get("title", "") for n in news_db)
    all_news = news_db + [n for n in news_api if n["title"] not in seen]

    # 3. 交叉分析
    catalysts = find_catalysts(all_news, snapshot.get("concepts", []))
    hot_themes = extract_themes(all_news)

    # 4. 持仓
    holdings = load_portfolio()
    portfolio_status = fetch_portfolio_status(holdings)

    # 5. 生成报告
    report = generate_report(snapshot, catalysts, all_news, portfolio_status, hot_themes)

    # 6. 飞书推送
    ok = send_to_feishu(report)
    logger.info(f"飞书: {'成功' if ok else '失败'}")

    # 7. 存 JSON
    STOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    fname = f"intel_report_{t.strftime('%Y%m%d_%H%M')}.json"
    json_path = STOCK_DATA_DIR / fname
    json_path.write_text(json.dumps({
        "time": t.strftime("%Y-%m-%d %H:%M:%S"),
        "indices": snapshot["indices"],
        "breadth": snapshot["breadth"],
        "catalysts": [{"concept": c["concept"]["name"],
                       "news_count": c["news_count"]} for c in catalysts],
        "holdings": portfolio_status,
        "news_count": len(all_news),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.time() - start
    logger.info(f"完成 | 耗时 {elapsed:.1f}s | 新闻{len(all_news)}条 | "
                f"涨停{snapshot['breadth'].get('limit_up','?')}只")

    # 也输出到控制台 (给 Claude Code cron 展示)
    print(report)


if __name__ == "__main__":
    main()
