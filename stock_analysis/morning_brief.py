#!D:/Python314/python
"""
Morning Brief v1.0 — 8:50前产出盘前晨报
=========================================
数据源: CLS新闻(8:00采集) + akshare美股 + 概念映射 + 隔夜计划
输出: stock_data/morning_brief_YYYYMMDD.md (可读) + .json (结构化)
触发: cron 8:37 或手动 python morning_brief.py

设计原则:
- 美股收盘 + 周末消息面 → 6只持仓影响评估
- 公告精选 (合同/减持/解禁/异动)
- 概念→标的自动映射
- 每个判断标注数据来源
"""

from error_capture import trap; trap()

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import akshare as ak
import requests

from config import STOCK_DATA_DIR, HEADERS

# ── 路径 ──
STOCK_DATA = Path(STOCK_DATA_DIR)
CONCEPT_MAP_FILE = STOCK_DATA / "concept_mapping.json"
OUTPUT_MD = STOCK_DATA / "morning_brief_latest.md"
OUTPUT_JSON = STOCK_DATA / "morning_brief_latest.json"

CST = timezone(timedelta(hours=8))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("morning_brief")


# ═══════════════════════════════════════════════════════════════
# 1. DATA COLLECTION
# ═══════════════════════════════════════════════════════════════

def load_latest_news() -> list[dict]:
    """加载今日8:00 CLS新闻。"""
    today = datetime.now(CST).strftime("%Y%m%d")
    pattern = f"news_manual_{today}_*.json"
    files = sorted(STOCK_DATA.glob(pattern))
    if not files:
        # fallback: try yesterday
        yesterday = (datetime.now(CST) - timedelta(days=1)).strftime("%Y%m%d")
        files = sorted(STOCK_DATA.glob(f"news_manual_{yesterday}_*.json"))
    if not files:
        logger.warning("No CLS news file found")
        return []
    latest = files[-1]
    data = json.loads(latest.read_text(encoding="utf-8"))
    items = data.get("data", [])
    logger.info(f"Loaded {len(items)} news from {latest.name}")
    return items


def _calc_pct_change(df) -> float:
    """从最近两行计算涨跌幅。akshare 不直接提供 pct_change。"""
    if df is None or len(df) < 2:
        return 0.0
    prev_close = float(df.iloc[-2].get("close", 0))
    curr_close = float(df.iloc[-1].get("close", 0))
    if prev_close == 0:
        return 0.0
    return round((curr_close - prev_close) / prev_close * 100, 2)


def fetch_us_sector_leaders() -> list[dict]:
    """采集美股关键板块龙头涨跌，用于映射A股概念。"""
    leaders = [
        # (显示名, akshare代码, 映射A股概念)
        ("AMD", "105.AMD", "半导体封测/CPU"),
        ("英特尔", "105.INTC", "半导体/CPU"),
        ("英伟达", "105.NVDA", "AI算力/GPU"),
        ("美光科技", "105.MU", "存储芯片"),
        ("阿斯麦", "105.ASML", "光刻机/半导体设备"),
        ("特斯拉", "105.TSLA", "机器人/新能源"),
        ("Rocket Lab", "105.RKLB", "商业航天"),
    ]
    results = []
    for i, (name, ticker, concept) in enumerate(leaders):
        for attempt in range(3):
            try:
                df = ak.stock_us_hist(symbol=ticker, period="daily", start_date="20260101", end_date="20501231")
                if df is not None and len(df) >= 1:
                    last = df.iloc[-1]
                    close_val = float(last.get("收盘", 0))
                    chg_val = float(last.get("涨跌幅", 0))
                    results.append({
                        "name": name, "ticker": ticker, "concept": concept,
                        "price": round(close_val, 2), "change_pct": round(chg_val, 2),
                    })
                break
            except Exception as e:
                if attempt < 2:
                    time.sleep(1.0 * (attempt + 1))
                else:
                    logger.debug(f"US leader {name} failed after 3 retries")
        time.sleep(0.3)  # 每个请求间隔300ms
    logger.info(f"US sector leaders: {len(results)} loaded")
    return results


def fetch_us_market() -> dict:
    """获取美股收盘数据。"""
    result = {"indices": [], "sector_leaders": [], "timestamp": ""}
    symbols = [
        ("道琼斯", ".DJI"),
        ("纳斯达克", ".IXIC"),
        ("标普500", ".INX"),
    ]
    for name, symbol in symbols:
        try:
            df = ak.index_us_stock_sina(symbol=symbol)
            if df is not None and len(df) >= 2:
                last = df.iloc[-1]
                change = _calc_pct_change(df)
                result["indices"].append({
                    "name": name, "price": float(last["close"]),
                    "change_pct": change,
                    "date": str(last.get("date", ""))
                })
        except Exception as e:
            logger.warning(f"US {name} fetch failed: {e}")

    if result["indices"]:
        result["timestamp"] = datetime.now(CST).strftime("%Y-%m-%d %H:%M")
    logger.info(f"US indices: {len(result['indices'])} loaded")
    return result


def load_concept_map() -> dict:
    """加载概念→持仓映射表。"""
    if CONCEPT_MAP_FILE.exists():
        return json.loads(CONCEPT_MAP_FILE.read_text(encoding="utf-8"))
    logger.warning("concept_mapping.json not found")
    return {"keyword_to_holdings": {}, "holdings": {}}


def load_nightly_plan() -> dict:
    """加载隔夜交易计划中的持仓数据。"""
    plan_files = sorted(STOCK_DATA.glob("nightly_plan_*.json"))
    if not plan_files:
        return {}
    try:
        return json.loads(plan_files[-1].read_text(encoding="utf-8"))
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════
# 2. ANALYSIS
# ═══════════════════════════════════════════════════════════════

def classify_news(news_items: list[dict]) -> dict:
    """将新闻分类为: policy/market/industry/company/risk/other"""
    categories = {
        "policy": [], "market": [], "industry": [],
        "company": [], "risk": [], "other": []
    }
    policy_kw = ["国务院", "发改委", "央行", "证监会", "政治局", "三部门", "印发", "意见", "行动方案"]
    risk_kw = ["减持", "解禁", "ST", "退市", "处罚", "调查", "立案", "亏损", "爆雷"]
    market_kw = ["A股", "大盘", "指数", "成交额", "资金", "北向", "融资融券"]
    company_kw = ["合同", "中标", "收购", "业绩", "营收", "净利润", "项目", "投产"]

    for item in news_items:
        title = item.get("title", "")
        if any(kw in title for kw in risk_kw):
            categories["risk"].append(item)
        elif any(kw in title for kw in policy_kw):
            categories["policy"].append(item)
        elif any(kw in title for kw in company_kw):
            categories["company"].append(item)
        elif any(kw in title for kw in market_kw):
            categories["market"].append(item)
        elif any(kw in title for kw in ["产业", "行业", "赛道", "板块"]):
            categories["industry"].append(item)
        else:
            categories["other"].append(item)

    return categories


def find_my_stocks(news_items: list[dict], concept_map: dict) -> dict[str, list]:
    """新闻→持仓股映射。返回 {code: [{title, keyword, time}, ...]}"""
    kw_map = concept_map.get("keyword_to_holdings", {})
    holdings_info = concept_map.get("holdings", {})

    result = {}
    for item in news_items:
        title = item.get("title", "")
        for keyword, codes in kw_map.items():
            if keyword.lower() in title.lower():
                for code in codes:
                    if code not in result:
                        result[code] = []
                    result[code].append({
                        "title": title,
                        "keyword": keyword,
                        "time": item.get("time", "")
                    })
    return result


def extract_announcements(news_items: list[dict]) -> dict:
    """提取公告类新闻: contracts/decreases/lockup/unusual"""
    result = {"contracts": [], "decreases": [], "lockup": [], "unusual": []}

    for item in news_items:
        title = item.get("title", "")
        if "减持" in title:
            result["decreases"].append(item)
        elif "解禁" in title:
            result["lockup"].append(item)
        elif any(kw in title for kw in ["合同", "中标", "收购", "投资", "项目"]):
            result["contracts"].append(item)
        elif any(kw in title for kw in ["异动", "公告", "停牌", "复牌"]):
            result["unusual"].append(item)

    return result


def assess_holding_impact(my_news: dict, us_data: dict, concept_map: dict) -> list[dict]:
    """评估每只持仓的今日影响方向和强度。"""
    holdings = concept_map.get("holdings", {})
    # US sector → A股映射
    us_signal = ""
    for idx in us_data.get("indices", []):
        chg = idx.get("change_pct", 0)
        if idx["name"] == "纳斯达克" and chg > 1:
            us_signal = "科技股强势"

    # 美股龙头 → A股标的映射
    leader_map = {
        "AMD": "002156", "英特尔": "002156", "英伟达": "000062",
        "美光": "002156", "阿斯麦": "300480", "Rocket Lab": "300342",
    }
    leader_hits = {}  # code -> [leader names]
    for leader in us_data.get("sector_leaders", []):
        code = leader_map.get(leader["name"])
        if code:
            if code not in leader_hits:
                leader_hits[code] = []
            leader_hits[code].append(f"{leader['name']} {leader['change_pct']:+.1f}%")

    results = []
    for code, info in holdings.items():
        news_count = len(my_news.get(code, []))
        my_news_items = my_news.get(code, [])
        leader_signals = leader_hits.get(code, [])

        # 判断方向 (新闻 + 美股龙头 综合)
        direction = "中性"
        score = 0
        if news_count >= 3:
            score += 2
        elif news_count >= 1:
            score += 1
        if leader_signals:
            score += len(leader_signals)

        if score >= 3:
            direction = "偏多"
        elif score >= 1:
            direction = "略多"

        # 纳斯达克上涨对科技股是顺风
        if info["sector"] in ("半导体封测", "半导体划片设备", "PCB/电子", "电子元器件分销") and us_signal:
            if direction == "中性":
                direction = "略多"

        # 合并新闻和龙头信号
        all_signals = [n["title"][:60] for n in my_news_items[:2]]
        if leader_signals:
            all_signals.insert(0, "美股: " + ", ".join(leader_signals))

        results.append({
            "code": code,
            "name": info["name"],
            "sector": info["sector"],
            "direction": direction,
            "news_count": news_count,
            "leader_signals": leader_signals,
            "key_news": all_signals[:3],
            "us_tailwind": us_signal if info["sector"] in ("半导体封测", "半导体划片设备", "PCB/电子", "电子元器件分销") else ""
        })

    return results


# ═══════════════════════════════════════════════════════════════
# 3. OUTPUT
# ═══════════════════════════════════════════════════════════════

def generate_markdown(us_data: dict, categories: dict, holding_impact: list,
                      announcements: dict, my_news: dict, concept_map: dict) -> str:
    """生成 Markdown 晨报。"""
    today = datetime.now(CST).strftime("%Y-%m-%d")
    weekday = ["周一","周二","周三","周四","周五","周六","周日"][datetime.now(CST).weekday()]

    lines = [
        f"# 盘前晨报 | {today} {weekday}",
        f"**生成时间**: {datetime.now(CST).strftime('%H:%M')} | 数据来源: CLS+akshare",
        "",
    ]

    # ── 一、美股收盘 ──
    lines.append("## 一、美股收盘")
    if us_data["indices"]:
        for idx in us_data["indices"]:
            arrow = "↑" if idx["change_pct"] > 0 else "↓" if idx["change_pct"] < 0 else "→"
            lines.append(f"- **{idx['name']}**: {idx['price']:,.0f} ({arrow}{abs(idx['change_pct']):.2f}%)")
    else:
        lines.append("- 美股数据获取失败，请手动查看")
    # Sector leaders
    if us_data.get("sector_leaders"):
        big_movers = [l for l in us_data["sector_leaders"] if abs(l["change_pct"]) > 2]
        if big_movers:
            lines.append("")
            lines.append("**板块龙头** (涨跌幅>2%):")
            for l in big_movers:
                arrow = "↑" if l["change_pct"] > 0 else "↓"
                lines.append(f"- {l['name']} ({l['concept']}): {arrow}{abs(l['change_pct']):.1f}%")
    lines.append("")

    # ── 二、你的持仓影响评估 ──
    lines.append("## 二、持仓影响评估")
    lines.append("| 代码 | 名称 | 方向 | 相关新闻 |")
    lines.append("|------|------|------|---------|")
    for h in holding_impact:
        arrow = {"偏多": "🟢", "略多": "🟡", "中性": "⚪", "略空": "🟠", "偏空": "🔴"}.get(h["direction"], "⚪")
        news_summary = "; ".join(h["key_news"][:2]) if h["key_news"] else "无直接相关"
        lines.append(f"| {h['code']} | {h['name']} | {arrow} {h['direction']} | {news_summary} |")
    lines.append("")

    # ── 三、重要政策/行业 ──
    lines.append("## 三、重要政策/行业")
    for item in categories.get("policy", [])[:5]:
        lines.append(f"- [{item.get('time','')[-8:-3]}] {item['title']}")
    for item in categories.get("industry", [])[:3]:
        lines.append(f"- [{item.get('time','')[-8:-3]}] {item['title']}")
    if not categories.get("policy") and not categories.get("industry"):
        lines.append("- 今日无重大政策/行业新闻")
    lines.append("")

    # ── 四、公告精选 ──
    lines.append("## 四、公告精选")
    if announcements["contracts"]:
        lines.append("**大单/合同**:")
        for item in announcements["contracts"][:5]:
            lines.append(f"- {item['title'][:100]}")
    if announcements["decreases"]:
        lines.append("**减持预警**:")
        for item in announcements["decreases"][:5]:
            lines.append(f"- {item['title'][:100]}")
    if announcements["lockup"]:
        lines.append("**解禁**:")
        for item in announcements["lockup"][:3]:
            lines.append(f"- {item['title'][:100]}")
    if not any([announcements["contracts"], announcements["decreases"], announcements["lockup"]]):
        lines.append("- 无重要公告")
    lines.append("")

    # ── 五、风险提示 ──
    lines.append("## 五、风险提示")
    if categories["risk"]:
        for item in categories["risk"][:5]:
            lines.append(f"- {item['title'][:100]}")
    else:
        lines.append("- 今日无重大风险信号")
    lines.append("")

    # ── 六、今日经济日历 ──
    lines.append("## 六、今日关注")
    lines.append("- **社融/M2**: 待发布 (★★★★★)")
    lines.append("- **中美磋商**: 何立峰 5/12-13 赴韩 (谈判前避险情绪)")
    lines.append("- **集合竞价**: 9:15-9:25, 关注通富微电竞价量能")
    lines.append("")

    lines.append("---")
    lines.append(f"*自动生成于 {datetime.now(CST).strftime('%Y-%m-%d %H:%M')} | morning_brief v1.0*")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 4. MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    start = time.time()
    logger.info("Morning Brief v1.0 starting...")

    # Collect
    news = load_latest_news()
    us_data = fetch_us_market()
    us_leaders = fetch_us_sector_leaders()
    us_data["sector_leaders"] = us_leaders
    concept_map = load_concept_map()

    # Analyze
    categories = classify_news(news)
    my_news = find_my_stocks(news, concept_map)
    announcements = extract_announcements(news)
    holding_impact = assess_holding_impact(my_news, us_data, concept_map)

    # Generate
    md = generate_markdown(us_data, categories, holding_impact, announcements, my_news, concept_map)

    # Save
    OUTPUT_MD.write_text(md, encoding="utf-8")
    OUTPUT_JSON.write_text(json.dumps({
        "date": datetime.now(CST).strftime("%Y-%m-%d"),
        "time": datetime.now(CST).strftime("%H:%M:%S"),
        "us_market": us_data,
        "holding_impact": holding_impact,
        "announcements": announcements,
        "my_news_count": sum(len(v) for v in my_news.values()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    elapsed = time.time() - start
    my_total = sum(len(v) for v in my_news.values())
    logger.info(f"Done in {elapsed:.1f}s | {len(news)} news | {my_total} hit holdings | {len(holding_impact)} holdings assessed")
    print(md)


if __name__ == "__main__":
    main()
