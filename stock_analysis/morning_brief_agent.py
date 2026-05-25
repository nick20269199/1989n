"""
morning_brief_agent.py — DeepSeek 驱动的盘前晨报 v2

数据源:
  - news_scheduler 08:00 采集的 CLS 新闻
  - akshare 美股隔夜数据
  - akshare 行业板块/概念板块涨跌排名
  - akshare 行业资金流向排名
  - akshare 大盘资金流向
  - call_auction 今日集合竞价数据
  - market_calendar 市场趋势状态
  - hot_stocks 热门股票
  - 持仓数据

触发: 08:37 (Windows Task Scheduler)
依赖: news_scheduler 08:00 先完成
"""

import json
import logging
import sqlite3
import sys
import time
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from data_quality_gate import preflight_scan
from morning_brief import (
    load_latest_news, fetch_us_market, load_stock_lookup,
    load_concept_map, load_holdings, annotate_news_with_stocks,
    detect_topics, extract_announcements_v2, assess_holding_impact_v2,
)
from cognitive_engine import load_context, deepseek_reason, send_output, save_output
from vv_insights import load_vv_insights, format_vv_for_prompt
from config import STOCK_DATA_DIR, PORTFOLIO_FILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s %(message)s")
logger = logging.getLogger("morning_brief_agent")

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path(STOCK_DATA_DIR)
OUTPUT_MD = STOCK_DATA / "morning_brief_agent_latest.md"
OUTPUT_JSON = STOCK_DATA / "morning_brief_agent_latest.json"
DB_PATH = STOCK_DATA / "stock.db"


# ═══════════════════════════════════════════════════════════════
# 1. DB TREND DATA (查数据库, 不受实时API限制)
# ═══════════════════════════════════════════════════════════════

def query_db(sql: str, params: tuple = ()) -> list:
    """查询 stock.db，返回 rows。"""
    try:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.warning(f"DB查询失败: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def load_hot_stocks_trend() -> str:
    """从 DB 获取近30天热门股票趋势 → 提炼板块轮动信号。

    Returns:
        格式化文本描述近期热门板块轮动
    """
    rows = query_db("""
        SELECT date, stock_code, stock_name, rank, change_pct
        FROM hot_stocks
        WHERE date >= date('now', '-30 days')
        ORDER BY date DESC, rank ASC
    """)
    if not rows:
        return "（数据库无近期热门股票数据）"

    # 按日期分组
    by_date = defaultdict(list)
    for r in rows:
        by_date[r["date"]].append(r)

    lines = []
    lines.append(f"近30日热门股票记录 ({len(rows)}条, {len(by_date)}个交易日)")
    for date in sorted(by_date.keys(), reverse=True):
        day = by_date[date]
        top5 = day[:5]
        # 提取涨幅极端值
        extremes = [r for r in day if abs(r["change_pct"]) > 15]
        extra = f", {len(extremes)}只涨跌幅>15%" if extremes else ""
        lines.append(f"  {date}: TOP={top5[0]['stock_name']}({top5[0]['change_pct']:+.1f}%) "
                     f"#{top5[1]['stock_name']}({top5[1]['change_pct']:+.1f}%){extra}")

    # 统计出现次数最多的股票（持续热门）
    codes_count = Counter(r["stock_code"] for r in rows)
    repeat = [code for code, cnt in codes_count.most_common(10) if cnt >= 3]
    if repeat:
        names = {r["stock_code"]: r["stock_name"] for r in rows}
        repeat_names = [f"{names[c]}({c})" for c in repeat if c in names]
        lines.append(f"  持续上榜个股: {', '.join(repeat_names)}")

    return "\n".join(lines)


def load_recent_news_themes() -> str:
    """从 DB 获取近5天新闻 → 主题聚类。

    Returns:
        格式化文本描述近期新闻主题分布
    """
    rows = query_db("""
        SELECT title, pub_time, related_stocks, category
        FROM news
        WHERE pub_time >= date('now', '-5 days')
          AND title != ''
        ORDER BY pub_time DESC
        LIMIT 200
    """)
    if not rows:
        return "（数据库无近期新闻数据）"
    # 关键词主题聚类
    themes = {
        "AI/算力/半导体": ["AI", "算力", "芯片", "半导体", "大模型", "智能", "算力", "光模块", "HVDC", "服务器"],
        "新能源/车/锂电": ["新能源", "锂电", "碳酸锂", "电动车", "储能", "光伏", "固态电池"],
        "机器人/自动化": ["机器人", "人形机器人", "自动化", "灵巧手", "智能制造"],
        "政策/宏观": ["央行", "降息", "降准", "利率", "国债", "财政", "证监会", "政策"],
        "电力/电网设备": ["电力", "电网", "虚拟电厂", "特高压", "变压器"],
        "消费/白酒/医药": ["消费", "白酒", "医药", "医疗", "零售", "免税"],
        "航天/低空/军工": ["航天", "低空", "军工", "商业航天", "卫星"],
        "地产/基建": ["房地产", "楼市", "基建", "土拍", "城中村"],
    }

    cnt = Counter()
    for r in rows:
        title = r.get("title", "")
        for theme, kws in themes.items():
            if any(kw in title for kw in kws):
                cnt[theme] += 1
                break

    lines = ["近5日新闻主题分布:"]
    for theme, count in cnt.most_common(15):
        lines.append(f"  {theme}: {count}条")
    lines.append(f"  总: {len(rows)}条 (最后5天)")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 2. REAL-TIME DATA (akshare, 交易时段活跃)
# ═══════════════════════════════════════════════════════════════

def load_sector_rankings() -> dict:
    """加载行业板块涨跌排名 + 资金流向排名。

    用 akshare 实时获取，不依赖缓存。
    Returns:
        {"industry_top": [...], "concept_top": [...], "fund_flow_top": [...], "fund_flow_bottom": [...]}
    """
    import akshare as ak
    from data_source_router import safe_akshare_call
    result = {"industry_top": [], "concept_top": [], "fund_flow_top": [], "fund_flow_bottom": []}

    try:
        df = safe_akshare_call(ak.stock_board_industry_name_em)
        if df is not None and not df.empty:
            cols = ["板块名称", "涨跌幅", "上涨家数", "下跌家数", "领涨股票"]
            available = [c for c in cols if c in df.columns]
            top = df.nlargest(8, "涨跌幅")[available].to_dict("records")
            result["industry_top"] = [{k: str(v)[:30] for k, v in row.items()} for row in top]
            logger.info(f"行业板块: {len(df)}条, 取前8")
    except Exception as e:
        logger.warning(f"行业板块获取失败: {e}")

    try:
        df = safe_akshare_call(ak.stock_board_concept_name_em)
        if df is not None and not df.empty:
            cols = ["板块名称", "涨跌幅", "上涨家数", "下跌家数"]
            available = [c for c in cols if c in df.columns]
            top = df.nlargest(10, "涨跌幅")[available].to_dict("records")
            result["concept_top"] = [{k: str(v)[:30] for k, v in row.items()} for row in top]
            logger.info(f"概念板块: {len(df)}条, 取前10")
    except Exception as e:
        logger.warning(f"概念板块获取失败: {e}")

    try:
        df = safe_akshare_call(ak.stock_sector_fund_flow_rank, indicator="今日", sector_type="行业资金流向")
        if df is not None and not df.empty:
            cols = ["名称", "主力净流入-净额", "主力净流入-净占比", "今日涨跌幅"]
            available = [c for c in cols if c in df.columns]
            top = df.nlargest(6, "主力净流入-净额")[available].to_dict("records")
            bottom = df.nsmallest(6, "主力净流入-净额")[available].to_dict("records")
            result["fund_flow_top"] = [{k: str(v)[:25] for k, v in row.items()} for row in top]
            result["fund_flow_bottom"] = [{k: str(v)[:25] for k, v in row.items()} for row in bottom]
            logger.info(f"资金流向: {len(df)}条")
    except Exception as e:
        logger.warning(f"资金流向获取失败: {e}")

    return result


def load_call_auction() -> dict:
    """加载今日最新集合竞价数据。

    Returns: {} 或 {"market_breadth": {}, "limit_orders": [], "portfolio": []}
    """
    today = datetime.now(CST).strftime("%Y%m%d")
    files = sorted(STOCK_DATA.glob(f"call_auction_{today}_*.json"))
    if not files:
        logger.info("今日无集合竞价数据（非交易日或未采集）")
        return {}

    data = json.loads(files[-1].read_text(encoding="utf-8"))
    result = {}

    breadth = data.get("market_breadth", {})
    if breadth:
        result["market_breadth"] = breadth

    limit_orders = data.get("limit_orders", [])
    if limit_orders:
        try:
            result["limit_orders"] = limit_orders[:10]
        except Exception:
            result["limit_orders"] = []

    portfolio = data.get("portfolio_auction", {})
    if portfolio:
        result["portfolio"] = portfolio

    logger.info(f"集合竞价: {files[-1].name}")
    return result


def load_market_calendar() -> dict:
    """加载最近交易日市场状态。"""
    cal_file = STOCK_DATA / "market_calendar.json"
    if not cal_file.exists():
        return {}
    try:
        data = json.loads(cal_file.read_text(encoding="utf-8"))
        dates = sorted(data.keys(), reverse=True)
        if dates:
            latest = data[dates[0]]
            logger.info(f"市场日历: {dates[0]} {latest.get('trend','')}")
            return {"date": dates[0], **latest}
    except Exception as e:
        logger.warning(f"市场日历读取失败: {e}")
    return {}


def load_hot_stocks() -> list:
    """加载热门股票排名。"""
    hs_file = STOCK_DATA / "hot_stocks.json"
    if not hs_file.exists():
        return []
    try:
        data = json.loads(hs_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data[:15]
        return []
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
# 2. PROMPT BUILDER (数据全面版)
# ═══════════════════════════════════════════════════════════════

def format_sector_data(sectors: dict) -> str:
    """格式化板块数据为文本。"""
    lines = []
    if sectors.get("industry_top"):
        lines.append("【行业板块涨幅 TOP8】")
        for s in sectors["industry_top"]:
            name = s.get("板块名称", "?")
            chg = s.get("涨跌幅", "")
            leader = s.get("领涨股票", "")
            up = s.get("上涨家数", "")
            dn = s.get("下跌家数", "")
            lines.append(f"  {name}: {chg}% | 涨{up}跌{dn} | 领涨:{leader}")
    if sectors.get("concept_top"):
        lines.append("【概念板块涨幅 TOP10】")
        for s in sectors["concept_top"]:
            name = s.get("板块名称", "?")
            chg = s.get("涨跌幅", "")
            up = s.get("上涨家数", "")
            dn = s.get("下跌家数", "")
            lines.append(f"  {name}: {chg}% | 涨{up}跌{dn}")
    if sectors.get("fund_flow_top"):
        lines.append("【主力净流入 TOP6】")
        for s in sectors["fund_flow_top"]:
            lines.append(f"  {s.get('名称','?')}: 净流入{s.get('主力净流入-净额','?')} ({s.get('主力净流入-净占比','?')})")
    if sectors.get("fund_flow_bottom"):
        lines.append("【主力净流出 TOP6】")
        for s in sectors["fund_flow_bottom"]:
            lines.append(f"  {s.get('名称','?')}: 净流出{s.get('主力净流入-净额','?')} ({s.get('主力净流入-净占比','?')})")
    return "\n".join(lines)


def format_auction_data(auction: dict) -> str:
    """格式化竞价数据。"""
    if not auction:
        return "（今日无竞价数据）"
    lines = []
    b = auction.get("market_breadth", {})
    if b:
        lines.append(f"竞价涨跌分布: 涨{b.get('up','?')} 平{b.get('flat','?')} 跌{b.get('down','?')}")
        lines.append(f"  涨停{b.get('limit_up','?')} 跌停{b.get('limit_down','?')}")
    lo = auction.get("limit_orders", [])
    if lo:
        lines.append("涨停封单:")
        for item in lo[:5]:
            lines.append(f"  {item}")
    po = auction.get("portfolio", {})
    if po:
        lines.append("持仓竞价:")
        if isinstance(po, dict):
            for code, info in po.items():
                lines.append(f"  {code}: {info}")
        elif isinstance(po, list):
            for item in po[:5]:
                lines.append(f"  {item}")
    return "\n".join(lines)


def build_market_prompt(
    news_data: dict, us_data: dict, holdings: dict,
    holding_impact: list, sector_rank: dict,
    auction: dict, market_state: dict, hot_stocks: list,
    hot_trend: str = "", news_themes: str = "",
    vv_prompt: str = "", recon_report: str = "",
) -> str:
    """构建给 DeepSeek 的完整 prompt，含所有市场温度数据。"""
    today = datetime.now(CST)
    lines = []
    lines.append(f"# 盘前晨报生成任务 | {today.strftime('%Y-%m-%d %A')}")
    lines.append("")

    # ── 〇、近期市场趋势（数据库） ──
    if hot_trend:
        lines.append("## 〇、近期市场趋势（数据库）")
        lines.append(hot_trend)
        lines.append("")
    if news_themes:
        lines.append("## 〇、近期新闻主题分布（数据库）")
        lines.append(news_themes)
        lines.append("")

    # ── 一、大盘状态 ──
    lines.append("## 一、大盘状态")
    if market_state:
        lines.append(f"日期: {market_state.get('date','?')}")
        lines.append(f"收盘: {market_state.get('close','?')} ({market_state.get('pct_chg','?')}%)")
        lines.append(f"趋势: {market_state.get('trend','?')}")
        lines.append(f"量能: {market_state.get('volume_state','?')}")
        lines.append(f"情绪: {market_state.get('sentiment','?')}")
    else:
        lines.append("（数据获取失败）")
    lines.append("")

    # ── 二、隔夜美股 ──
    for idx in us_data.get("indices", []):
        lines.append(f"- {idx['name']}: {idx.get('price','?')} ({idx.get('change_pct',0):+.2f}%)")
    leaders = us_data.get("sector_leaders", [])
    movers = [l for l in leaders if abs(l.get("change_pct", 0)) > 0.5]
    if movers:
        lines.append("龙头股:")
        for l in movers[:8]:
            lines.append(f"  {l['name']}({l.get('concept','')}): {l.get('change_pct',0):+.1f}%")
    lines.append("")

    # ── 三、A股板块温度 ──
    lines.append("## 三、A股板块温度")
    lines.append(format_sector_data(sector_rank))
    lines.append("")

    # ── 四、集合竞价 ──
    lines.append("## 四、集合竞价 (今日)")
    lines.append(format_auction_data(auction))
    lines.append("")

    # ── 五、热门股票 ──
    if hot_stocks:
        lines.append("## 五、热门股票")
        for s in hot_stocks[:10]:
            if isinstance(s, dict):
                lines.append(f"- {s.get('name','?')}({s.get('code','?')}): "
                             f"{s.get('price','?')} {s.get('change_pct','?')}%")
            else:
                lines.append(f"- {s}")
        lines.append("")

    # ── 五B、大V雷达（观点摘要，需验证可靠性） ──
    if vv_prompt and vv_prompt != "（近48小时无大V视频）":
        lines.append(vv_prompt)
        lines.append("")

    # ── 五C、情报部侦察 + 侦查日报 ──
    if recon_report:
        lines.append("## 情报部侦察 + 侦查日报")
        lines.append(recon_report)
        lines.append("")

    # ── 六、新闻列表 ──
    lines.append("## 六、重要新闻")
    for i, item in enumerate(news_data["items"], 1):
        title = item.get("title", "")
        content = item.get("content", "") or ""
        importance = item.get("importance", 1)
        category_group = item.get("category_group", "")
        stocks = item.get("matched_stocks", [])
        sstr = ", ".join(f"{s['name']}({s['code']})" for s in stocks[:4]) if stocks else "无"

        # 分类标签
        tag = f"[{category_group}]" if category_group and category_group != "industry" else ""

        line = f"{i}. {tag}[重要度:{importance}] **{title}**"
        lines.append(line)

        # 正文: 持仓相关/重要性高 → 全文; 其他 → 精简
        matched_sectors = item.get("matched_sectors") or []
        if matched_sectors or importance >= 5:
            show = content[:600] if content else ""
        elif importance >= 3:
            show = content[:200] if content else ""
        else:
            show = content[:80] if content else ""

        if show:
            lines.append(f"   {show}")
        if matched_sectors and len(matched_sectors) <= 5:
            lines.append(f"   关联持仓: {' '.join(matched_sectors)}")
        else:
            lines.append(f"   标的: {sstr}")
        if i >= 25:
            total = news_data.get("total", len(news_data["items"]))
            lines.append(f"   ...共{total}条，仅显示前25条")
            break
    lines.append("")

    # ── 七、热点主题 ──
    if news_data.get("topics"):
        lines.append("## 七、热点主题")
        for t in news_data["topics"][:5]:
            lines.append(f"- {t['topic']}: {len(t['news'])}条新闻, {len(t['stocks'])}只标的")
        lines.append("")

    # ── 八、公告精选 ──
    ann = news_data["announcements"]
    if ann.get("decreases") or ann.get("contracts") or ann.get("unusual"):
        lines.append("## 八、公告精选")
        if ann.get("decreases"):
            lines.append(f"### 减持预警 ({len(ann['decreases'])}条)")
            for item in ann["decreases"][:6]:
                lines.append(f"- {item.get('title','')[:80]}")
        if ann.get("contracts"):
            lines.append(f"### 合同/中标 ({len(ann['contracts'])}条)")
            for item in ann["contracts"][:5]:
                lines.append(f"- {item.get('title','')[:80]}")
        if ann.get("unusual"):
            lines.append(f"### 异动澄清")
            for item in ann["unusual"][:3]:
                lines.append(f"- {item.get('title','')[:80]}")
        lines.append("")

    # ── 九、持仓影响 ──
    lines.append("## 九、持仓影响 (规则评分)")
    if holding_impact:
        lines.append("| 代码 | 名称 | 方向 | 评分 | 理由 |")
        lines.append("|------|------|------|------|------|")
        for h in holding_impact:
            lines.append(f"| {h['code']} | {h['name']} | {h['direction']} | {h['score']} | {h['reason']} |")
        lines.append("")
        # 持仓完整信息
        lines.append("持仓明细:")
        for code, info in holdings.items():
            name = info.get("name", code)
            lines.append(f"- {name}({code})")
    lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 3. MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    start = time.time()
    logger.info("Morning Brief Agent v2 starting...")

    # 周末守卫
    if datetime.now(CST).weekday() >= 5:
        logger.info("非交易日，跳过")
        return

    # ── 知识上下文 ──
    context = load_context(["knowledge/stocks/morning-brief-architecture.md"])

    # ── 采集全部数据 ──
    logger.info("采集数据...")
    news = load_latest_news()
    if not news:
        logger.warning("无新闻，跳过")
        return

    us_data = fetch_us_market()
    lookup = load_stock_lookup()
    concept_map = load_concept_map()
    holdings = load_holdings()

    annotated = annotate_news_with_stocks(news, lookup)
    topics = detect_topics(annotated)
    announcements = extract_announcements_v2(annotated)
    holding_impact = assess_holding_impact_v2(annotated, us_data, holdings)

    # 新增数据源
    sector_rank = load_sector_rankings()
    auction = load_call_auction()
    market_state = load_market_calendar()
    hot_stocks_list = load_hot_stocks()

    # 数据库趋势数据（不受实时API限制）
    hot_trend = load_hot_stocks_trend()
    news_themes = load_recent_news_themes()

    # 大V雷达（近期观点，需 DeepSeek 验证可靠性）
    vv_data = load_vv_insights(hours=96)
    vv_prompt = format_vv_for_prompt(vv_data)
    if vv_data["total_videos"] > 0:
        logger.info(f"大V雷达: {vv_data['author_count']}位大V, {vv_data['total_videos']}条视频")

    # 情报部侦察信号（intel_recon 08:32产出，包含新闻→概念→VCP共振信号）
    recon_report = ""
    try:
        intel_dir = STOCK_DATA / "intel"
        date_str = datetime.now(CST).strftime("%Y-%m-%d")
        intel_path = intel_dir / f"intel_recon_{date_str}.md"
        if not intel_path.exists():
            intel_path = intel_dir / f"intel_recon_{(datetime.now(CST) - timedelta(days=1)).strftime('%Y-%m-%d')}.md"
        if intel_path.exists():
            recon_report = intel_path.read_text(encoding="utf-8").strip()
            if "---" in recon_report:
                recon_report = recon_report.split("---")[0].strip()
            logger.info(f"情报部侦察: 引用 {intel_path.name}")
    except Exception as e:
        logger.warning(f"情报部侦察加载失败: {e}")

    # 侦查日报（recon_daily 15:30产出，DeepSeek 驱动的机会发现）
    recon_extra = ""
    try:
        date_y4 = datetime.now(CST).strftime("%Y%m%d")
        rr_path = STOCK_DATA / f"recon_report_{date_y4}.md"
        if not rr_path.exists():
            rr_path = STOCK_DATA / f"recon_report_{(datetime.now(CST) - timedelta(days=1)).strftime('%Y%m%d')}.md"
        if rr_path.exists():
            rr_text = rr_path.read_text(encoding="utf-8").strip()
            # 去掉头部的 # 侦查日报 标题行和尾部签名行
            lines = rr_text.split("\n")
            body = [l for l in lines if not l.startswith("---") and not l.startswith("*数据源")]
            recon_extra = "\n".join(body).strip()
            logger.info(f"侦查日报: 引用 {rr_path.name}")
    except Exception as e:
        logger.warning(f"侦查日报加载失败: {e}")

    annotated_count = sum(1 for n in annotated if n["matched_stocks"])
    logger.info(
        f"数据完成: {len(annotated)}新闻 {annotated_count}标注 "
        f"{len(topics)}主题 | 板块{len(sector_rank.get('industry_top',[]))} "
        f"竞价{'有' if auction else '无'} "
        f"市场状态{'有' if market_state else '无'}"
    )

    # 合并情报部侦察 + 侦查日报
    if recon_extra:
        recon_report = (recon_report + "\n\n" + recon_extra) if recon_report else recon_extra

    # ── 构建 prompt ──
    news_data = {
        "total": len(annotated), "annotated": annotated_count,
        "items": annotated, "topics": topics,
        "announcements": announcements,
    }
    data_block = build_market_prompt(
        news_data, us_data, holdings, holding_impact,
        sector_rank, auction, market_state, hot_stocks_list,
        hot_trend=hot_trend, news_themes=news_themes,
        vv_prompt=vv_prompt, recon_report=recon_report,
    )

    system_prompt = f"""你是专业 A 股盘前分析师。你的核心能力是：
1. **刷选重要消息** — 大量新闻里只有3-5条真正影响今日盘面，甄别出来
2. **板块温度判断** — 结合板块涨幅排名+资金流向+竞价数据，判断今日主线
3. **持仓映射** — 8只持仓中哪些受益/受损于今日板块格局
4. **给出可操作判断** — 不只是罗列数据，要给出今日态度
5. **引用情报部侦察** — 如果有「情报部侦察」板块，将其中的多源交叉验证信号纳入今日判断，但你的判断优先级更高

晨报架构参考:
{context}

写作规范:
- 数据精确：不用模糊词，涨跌幅用具体数值
- 按主题聚合：不要"第1条新闻是...第2条新闻是..."，按主题分组呈现
- **涉及股票必须标注代码**，如 数据港(603881)，不只有名称
- 有态度：每个板块/新闻给出你的判断（利多/利空/中性）
- 持仓优先：对持仓的影响放在突出位置
- 简洁：每段不超过3句
- 不编造：不确定的标注"待确认"

输出格式：Markdown，7个板块。"""

    prompt = f"""生成今日盘前晨报。以下是全部市场数据：

{data_block}

要求：
1. **今日导读**（4-5条）：选今日最重要的几条，每条附受益标的，**带股票代码**
2. **大盘状态**：结合趋势/量能/情绪/外围，判断今日方向
3. **全球市场**：隔夜美股指数+龙头股涨跌，判断外围影响方向
4. **板块温度**：结合板块涨幅+资金流向，判断今日主线题材。**要给出判断，不止列数据**
5. **持仓影响**：逐只评估8只持仓，结合板块位置+新闻+美股信号
6. **公告精选**：减持/合同/异动分类
7. **今日策略**：关注什么、回避什么、操作思路
8. **大V观点验证**：对「大V雷达」中的板块/标的逐条判断——基于你已有的市场数据，大V的看多/看空是否站得住脚。认可的打✓，质疑的打✗并说明原因。不要盲信大V观点。"""

    logger.info("调用 DeepSeek...")
    result = deepseek_reason(
        channel="review", prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.4, max_tokens=8192,
    )

    if result.startswith("[错误]"):
        logger.error(f"失败: {result}")
        print(result)
        return

    # ── 产出 ──
    json.dump({
        "date": datetime.now(CST).strftime("%Y-%m-%d"),
        "time": datetime.now(CST).strftime("%H:%M:%S"),
        "data_sources": {
            "news": len(annotated), "annotated": annotated_count,
            "sectors": len(sector_rank.get("industry_top", [])),
            "auction": bool(auction), "market_state": bool(market_state),
        },
        "agent_version": "v2",
    }, OUTPUT_JSON.open("w", encoding="utf-8"), ensure_ascii=False, indent=2)

    OUTPUT_MD.write_text(result, encoding="utf-8")
    save_output("morning_brief", result)

    # 发送前保鲜检查
    preflight = preflight_scan(["morning_brief_agent_latest.json", "portfolio.json"])
    if preflight["healthy"] or datetime.now(CST).hour < 10:
        # 早间 10:00 之前即使数据略旧也发送（隔夜数据在开盘前无更新）
        send_output("盘前晨报", result, route="main")
    else:
        logger.warning(f"盘前晨报跳过发送: {preflight['summary']}")
        send_output("盘前晨报(数据过期)", f"数据保鲜检查未通过:\n{preflight['summary']}", route="alerts")

    elapsed = time.time() - start
    logger.info(f"完成 | {elapsed:.1f}s | {len(result)} chars")
    print(result[:600])


if __name__ == "__main__":
    main()
