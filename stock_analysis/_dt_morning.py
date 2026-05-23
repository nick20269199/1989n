"""Daily task command: morning_enhanced — run_morning_enhanced"""
import glob
import json
from datetime import datetime

from daily_task import (
    logger, ensure_data_dir, date_today,
    is_pre_market, is_market_hours,
    fetch_global_markets, fetch_economic_calendar,
    load_portfolio, fetch_quotes_batch, fetch_news_for_holdings,
    _SKILL_AVAILABLE, scan_watchlist_tech,
    send_feishu_message, format_indices_feishu, format_holdings_feishu,
)


def _load_latest_trade_plan():
    """加载最新的隔夜交易计划"""
    plan_dir = ensure_data_dir() / "trade_plans"
    if not plan_dir.exists():
        return None
    files = sorted(glob.glob(str(plan_dir / "plan_*.json")))
    if not files:
        return None
    try:
        with open(files[-1], "r", encoding="utf-8") as f:
            plan = json.load(f)
        slim = {
            "for_date": plan.get("for_date", ""),
            "generated_at": plan.get("generated_at", ""),
            "can_open_new": plan["summary"].get("can_open_new", True),
            "emergency_count": plan["summary"].get("emergency_count", 0),
            "total_pnl_pct": plan["summary"].get("total_pnl_pct", 0),
            "positions": [],
        }
        for p in plan.get("positions", []):
            slim["positions"].append({
                "code": p["code"],
                "name": p["name"],
                "pnl_pct": p["pnl_pct"],
                "hold_days": p["hold_days"],
                "priority": p["priority"],
                "danger_zone": p.get("danger_zone", False),
                "trail_active": p.get("trail_active", False),
                "key_action": p["scenarios"][2]["action"] if len(p["scenarios"]) > 2 else "",
            })
        return slim
    except Exception as e:
        logger.warning(f"加载交易计划失败: {e}")
        return None


# 题材→受益标的映射表 (持续扩充)
THEME_STOCK_MAP: dict[str, str] = {
    "量子计算": "国盾量子、科大国创、格尔软件、吉大正元、神州信息",
    "量子科技": "国盾量子、科大国创、格尔软件、吉大正元、神州信息",
    "FSD": "四维图新、中科创达、德赛西威、华阳集团、经纬恒润",
    "自动驾驶": "中科创达、德赛西威、华阳集团、经纬恒润",
    "特斯拉": "拓普集团、三花智控、旭升集团、岱美股份",
    "SpaceX": "西部材料、再升科技、通宇通讯、天银机电、信维通信",
    "星舰": "西部材料、天银机电",
    "算力租赁": "润建股份、利通电子、中嘉博创、协创数据",
    "算力": "润建股份、利通电子、中嘉博创、协创数据",
    "GPU": "胜宏科技、沪电股份、兴森科技",
    "PCB": "胜宏科技、沪电股份、深南电路、鹏鼎控股",
    "MLCC": "风华高科、三环集团、洁美科技",
    "ABF": "兴森科技、华正新材",
    "存储芯片": "德明利、兆易创新、佰维存储、江波龙",
    "HBM": "华海诚科、联瑞新材、雅克科技",
    "液冷": "英维克、高澜股份、申菱环境",
    "服务器": "中科曙光、浪潮信息、紫光股份、工业富联",
    "英伟达": "胜宏科技、沪电股份、兴森科技、中际旭创",
    "Rubin": "胜宏科技、沪电股份、兴森科技",
    "半导体": "北方华创、中芯国际、华虹公司、中微公司",
    "光刻机": "张江高科、茂莱光学、福晶科技",
    "封测": "通富微电、长电科技、华天科技",
    "金刚石": "黄河旋风、四方达、沃尔德、力量钻石",
    "光伏": "隆基绿能、通威股份、阳光电源、晶澳科技",
    "Enphase": "阳光电源、锦浪科技、固德威",
    "SolarEdge": "阳光电源、锦浪科技、固德威",
    "机器人": "埃斯顿、汇川技术、绿的谐波、拓普集团",
    "人形机器人": "拓普集团、三花智控、绿的谐波",
    "低空经济": "中信海直、莱斯信息、纵横股份、亿航智能",
    "军工": "中航沈飞、航发动力、中航光电、航天电器",
    "大飞机": "成飞集成、中航西飞、中航沈飞",
    "统一大市场": "飞力达、新宁物流、中国外运、华贸物流",
    "防汛": "青龙管业、韩建河山、钱江水利",
    "油轮": "招商南油、中远海能、招商轮船",
    "房地产": "保利发展、万科A、招商蛇口、华发股份",
    "鸿蒙": "润和软件、软通动力、诚迈科技",
    "数字货币": "广电运通、宇信科技、长亮科技",
    "创新药": "恒瑞医药、百济神州、信达生物",
    "中药": "片仔癀、云南白药、同仁堂",
}

_RISK_KEYWORDS = [
    "减持", "减持计划", "拟减持", "立案", "调查",
    "监管", "问询函", "关注函", "警示", "ST",
    "退市", "解禁", "业绩变脸", "亏损", "停牌",
]


def _match_themes_from_news(news_items: list[dict]) -> list[dict]:
    """从今日新闻中匹配活跃题材，返回题材→受益标的列表"""
    if not news_items:
        return []
    combined_text = " ".join(
        n.get("title", "") + " " + n.get("content", "")
        for n in news_items
    )
    sorted_themes = sorted(THEME_STOCK_MAP.items(), key=lambda x: -len(x[0]))
    active = []
    for theme, stocks in sorted_themes:
        if theme not in combined_text:
            continue
        if any(theme in existing["theme"] and stocks == existing["stocks"]
               for existing in active):
            continue
        active.append({"theme": theme, "stocks": stocks})
    return active


def _get_risk_highlights(news_items: list[dict]) -> list[str]:
    """从新闻中提取风险信息（减持/立案/监管等），去重"""
    seen = set()
    risks = []
    for n in news_items:
        text = n.get("title", "") + " " + n.get("content", "")
        for kw in _RISK_KEYWORDS:
            if kw in text:
                idx = text.find(kw)
                start = max(0, idx - 20)
                snippet = text[start:start + 80]
                if snippet not in seen:
                    risks.append(snippet)
                    seen.add(snippet)
                break
    return risks


def _ashare_mapping_for_global(global_data: dict) -> list[str]:
    """对全球市场数据生成A股映射传导链"""
    mappings = []
    for idx in global_data.get("indices", []):
        name = idx.get("name", "")
        chg = idx.get("change_pct", 0)
        if "纳斯达克" in name and chg > 1:
            mappings.append(f"纳斯达克 涨{chg:.1f}% → 映射A股科技/半导体")
        elif "纳斯达克" in name and chg < -1:
            mappings.append(f"纳斯达克 跌{chg:.1f}% → A股科技可能承压")
        elif "标普" in name and chg > 1:
            mappings.append(f"标普500 涨{chg:.1f}% → 映射A股核心资产")
        elif "标普" in name and chg < -1:
            mappings.append(f"标普500 跌{chg:.1f}% → 情绪传导偏空")
        elif "道琼斯" in name and abs(chg) > 1:
            mappings.append(f"道琼斯 {chg:+.1f}% → 映射A股金融/消费")
    return mappings


def run_morning_enhanced():
    """盘前增强简报 (09:00 执行)"""
    logger.info("=" * 50)
    logger.info("执行 morning_enhanced — 盘前增强简报")
    ensure_data_dir()

    dt = datetime.now()
    date_str = date_today()
    market_status = "盘前" if is_pre_market(dt) else ("交易中" if is_market_hours(dt) else "休市")

    # 1) 全球市场
    logger.info("获取全球市场数据...")
    global_data = fetch_global_markets()

    # 2) 经济日历
    logger.info("获取经济日历...")
    eco_cal = fetch_economic_calendar()

    # 3) 持仓行情
    logger.info("获取持仓行情...")
    holdings = load_portfolio()
    portfolio_scan = {"holdings": [], "total": 0}
    total_value = 0

    codes = [h["code"] for h in holdings]
    quotes = fetch_quotes_batch(codes)

    now_dt = datetime.now()
    today_str = date_today()
    cal_data = {}
    cal_path = ensure_data_dir() / "market_calendar_full.json"
    alt_path = ensure_data_dir() / "market_calendar.json"
    if cal_path.exists():
        cal_data = json.loads(cal_path.read_text(encoding="utf-8"))
    elif alt_path.exists():
        cal_data = json.loads(alt_path.read_text(encoding="utf-8"))

    for h in holdings:
        q = quotes.get(h["code"])
        cost = h["cost"]

        if q is None or q.get("price", 0) <= 0:
            portfolio_scan["holdings"].append({
                "code": h["code"],
                "name": h.get("name", ""),
                "shares": h["shares"],
                "cost": cost,
                "price": None,
                "change_pct": None,
                "pnl_pct": None,
                "sector": h.get("sector", ""),
                "alerts": ["🔴 行情数据暂缺"],
            })
            continue

        price = q.get("price", 0)
        pnl_pct = round(((price - cost) / cost * 100), 2) if cost > 0 else 0
        mv = price * h["shares"]
        total_value += mv

        alerts = []
        if pnl_pct <= -7:
            alerts.append(f"⛔ 硬止损触发 {pnl_pct:.1f}%")
        elif pnl_pct <= -5:
            alerts.append(f"⚠ 接近硬止损 {pnl_pct:.1f}%")
        elif pnl_pct <= -3:
            alerts.append(f"⚡ 软止损触发 {pnl_pct:.1f}%")
        if h.get("first_buy"):
            try:
                bd = datetime.strptime(h["first_buy"], "%Y-%m-%d")
                nd = datetime.strptime(today_str, "%Y-%m-%d")
                hold_days = (nd - bd).days
            except Exception:
                hold_days = 0
            if 3 <= hold_days <= 5 and pnl_pct < 2:
                alerts.append(f"🔶 危险区 D{hold_days} {pnl_pct:+.1f}%")
            if hold_days > 10:
                alerts.append(f"⏰ 超时 D{hold_days}")
        if pnl_pct >= 15:
            alerts.append(f"💰 +15%全止盈")
        elif pnl_pct >= 8:
            alerts.append(f"💰 +8%止盈一半")
        if pnl_pct >= 5:
            alerts.append(f"📈 移动止损激活 {pnl_pct:.1f}%")

        portfolio_scan["holdings"].append({
            "code": h["code"],
            "name": h.get("name", ""),
            "shares": h["shares"],
            "cost": cost,
            "price": price,
            "change_pct": q.get("change_pct", 0),
            "pnl_pct": pnl_pct,
            "sector": h.get("sector", ""),
            "alerts": alerts,
        })
    portfolio_scan["total"] = round(total_value, 2)

    # 4) 新闻
    logger.info("获取相关新闻...")
    news_alerts = fetch_news_for_holdings(codes, limit=20)

    # 5) 技术信号
    logger.info("运行技术扫描...")
    if _SKILL_AVAILABLE:
        tech_signals = scan_watchlist_tech(codes).get("results", [])
    else:
        tech_signals = []

    # 6) 加载最新交易计划
    trade_plan = _load_latest_trade_plan()
    if trade_plan:
        logger.info(f"加载交易计划: {trade_plan.get('for_date', '?')}")

    # 7) 构建输出
    output = {
        "title": f"盘前简报 | {date_str}日",
        "date": date_str,
        "time": dt.strftime("%H:%M:%S"),
        "market_status": market_status,
        "economic_calendar": eco_cal,
        "global_overnight": global_data,
        "portfolio_scan": portfolio_scan,
        "today_focus": {
            "top_news": news_alerts[:10],
            "signals": tech_signals,
            "risks": [],
        },
        "trade_plan": trade_plan,
    }

    # 写入JSON
    json_path = ensure_data_dir() / "morning_enhanced.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    # 生成并写入 Markdown
    md_path = ensure_data_dir() / "morning_enhanced.md"
    md_lines = []
    md_lines.append(f"# 盘前简报 | {date_str}\n")
    md_lines.append(f"**时间**: {dt.strftime('%H:%M:%S')} | **状态**: {market_status}\n")

    md_lines.append("## 全球市场\n")
    for idx in global_data.get("indices", []):
        sign = "+" if idx.get("change_pct", 0) >= 0 else ""
        md_lines.append(f"- {idx['name']}: {idx.get('price', '-')} ({sign}{idx.get('change_pct', 0):.2f}%)\n")

    ashare_map = _ashare_mapping_for_global(global_data)
    if ashare_map:
        md_lines.append("\n**A股映射**:\n")
        for m in ashare_map:
            md_lines.append(f"- {m}\n")

    risks = _get_risk_highlights(news_alerts)
    if risks:
        md_lines.append("\n## ⚠ 风险监测\n")
        for r in risks[:5]:
            md_lines.append(f"- {r}\n")

    md_lines.append("\n## 持仓概览\n")
    md_lines.append("| 股票 | 现价 | 涨跌 | 盈亏 | 告警 |")
    md_lines.append("|------|------|------|------|------|")
    alert_count = 0
    for h_ in portfolio_scan["holdings"]:
        if h_["pnl_pct"] is None:
            alert_str = ", ".join(h_["alerts"]) if h_["alerts"] else "数据暂缺"
            md_lines.append(f"| {h_['name']}({h_['code']}) | 数据暂缺 | 数据暂缺 | 数据暂缺 | {alert_str} |")
            continue
        sign = "+" if h_["pnl_pct"] >= 0 else ""
        alert_str = ", ".join(h_["alerts"]) if h_["alerts"] else "-"
        if h_["alerts"]:
            alert_count += 1
        md_lines.append(f"| {h_['name']}({h_['code']}) | {h_['price']} | {h_['change_pct']:.1f}% | {sign}{h_['pnl_pct']:.1f}% | {alert_str} |")
    md_lines.append(f"\n**持仓总市值: {portfolio_scan['total']:,.0f}元**")
    if alert_count > 0:
        md_lines.append(f"\n**⚠ {alert_count} 只持仓有告警**\n")
    else:
        md_lines.append("\n")

    if trade_plan:
        md_lines.append(f"\n## 今日交易剧本 ({trade_plan['for_date']})\n")
        md_lines.append(f"- 可开新仓: {'是' if trade_plan['can_open_new'] else '否'}")
        md_lines.append(f"- 紧急处理: {trade_plan['emergency_count']}只")
        md_lines.append(f"- 总盈亏: {trade_plan['total_pnl_pct']:+.2f}%\n")
        md_lines.append("| 股票 | 盈亏 | 天数 | 状态 | 平开操作 |")
        md_lines.append("|------|------|------|------|----------|")
        for p in trade_plan["positions"]:
            tags = []
            if p["priority"] == "紧急":
                tags.append("紧急")
            if p["danger_zone"]:
                tags.append(f"D{p['hold_days']}")
            if p["trail_active"]:
                tags.append("移动止损")
            tag_str = ",".join(tags) if tags else "-"
            md_lines.append(f"| {p['name']}({p['code']}) | {p['pnl_pct']:+.1f}% | {p['hold_days']}天 | {tag_str} | {p['key_action']} |")
        md_lines.append("")

    active_themes = _match_themes_from_news(news_alerts)
    if active_themes:
        md_lines.append("\n## 今日题材映射\n")
        for t in active_themes[:8]:
            md_lines.append(f"- **{t['theme']}**: {t['stocks']}\n")

    if news_alerts:
        md_lines.append("\n## 重要新闻\n")
        for n in news_alerts[:10]:
            md_lines.append(f"- [{n.get('source', '')}] {n.get('title', '')}\n")

    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown 输出: {md_path}")

    # 发送飞书
    feishu_content = format_indices_feishu(global_data.get("indices", []))
    feishu_content += "\n\n" + format_holdings_feishu(portfolio_scan["holdings"])
    urgent_alerts = [h for h in portfolio_scan["holdings"] if h["alerts"]]
    if urgent_alerts:
        feishu_content += "\n\n**⚠ 持仓告警**\n"
        for h in urgent_alerts:
            for a in h["alerts"]:
                feishu_content += f"- {h['name']}({h['code']}): {a}\n"
    risks = _get_risk_highlights(news_alerts)
    if risks:
        feishu_content += "\n**⚠ 市场风险**\n"
        for r in risks[:3]:
            feishu_content += f"- {r[:60]}\n"
    active_themes = _match_themes_from_news(news_alerts)
    if active_themes:
        feishu_content += "\n**今日题材**\n"
        for t in active_themes[:4]:
            feishu_content += f"- {t['theme']}: {t['stocks']}\n"
    if news_alerts:
        feishu_content += "\n**重要新闻**\n"
        for n in news_alerts[:5]:
            feishu_content += f"- {n.get('title', '')[:80]}\n"

    ok = send_feishu_message(f"盘前简报 | {date_str}", feishu_content)
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("morning_enhanced 完成")
    return output
