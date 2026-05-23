"""
侦查日报 v1 — 收盘后探索层：发现新机会，喂给明天晨报

运行: 交易日 15:30-16:00
依赖: hot_stocks.json / vv_radar.db / tech_scan / akshare 板块数据
产出: stock_data/recon_report_{date}.md + 飞书推送
消费: 隔日 morning_brief_agent.py 自动引用
"""

import json
import logging
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import akshare as ak
from cognitive_engine import deepseek_reason, send_output, save_output
from config import STOCK_DATA_DIR
from data_source_router import safe_akshare_call
from vv_insights import load_vv_insights, format_vv_for_prompt

logger = logging.getLogger("recon_daily")

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path(STOCK_DATA_DIR)
PORTFOLIO_FILE = Path(__file__).parent / "data" / "portfolio.json"
DB_PATH = STOCK_DATA / "stock.db"
RADAR_DB = STOCK_DATA / "vv_radar.db"

RECON_OUTPUT = STOCK_DATA / "recon_report_{date}.md"

# 板块关键词映射（同 morning_brief_agent）
THEMES = {
    "AI/算力/半导体": ["AI", "算力", "芯片", "半导体", "大模型", "光模块", "HVDC", "服务器", "CPO", "光通信"],
    "新能源/车/锂电": ["新能源", "锂电", "碳酸锂", "电动车", "储能", "光伏", "固态电池"],
    "机器人/自动化": ["机器人", "人形机器人", "自动化", "灵巧手", "智能制造"],
    "航天/低空/军工": ["航天", "低空", "军工", "商业航天", "卫星", "SpaceX"],
    "消费电子/AI PC": ["消费电子", "AI PC", "PC", "折叠屏", "MR", "VR"],
    "电力/电网设备": ["电力", "电网", "虚拟电厂", "特高压", "变压器"],
    "医药/医疗": ["医药", "医疗", "创新药", "医疗器械", "CXO"],
}


def load_portfolio_codes() -> list[str]:
    """返回持仓代码列表（用于过滤"已有" vs "新增"）。"""
    try:
        data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [h["code"] for h in data if h.get("shares", 0) > 0]
        if isinstance(data, dict) and "holdings" in data:
            return [h["code"] for h in data["holdings"] if h.get("shares", 0) > 0]
    except Exception:
        pass
    return []


def load_hot_stocks_recent(days: int = 5) -> dict:
    """从 DB 获取近期热门股票趋势，按频率排序。"""
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()
    cur.execute("""
        SELECT stock_code, stock_name, COUNT(*) as appear_count,
               MAX(rank) as best_rank, AVG(change_pct) as avg_chg
        FROM hot_stocks
        WHERE date >= date('now', ?)
        GROUP BY stock_code
        ORDER BY appear_count DESC, best_rank ASC
        LIMIT 30
    """, (f'-{days}',))
    rows = cur.fetchall()
    conn.close()
    return {"total": len(rows), "items": [
        {"code": r[0], "name": r[1], "appear": r[2], "best_rank": r[3], "avg_chg": round(r[4], 2) if r[4] else 0}
        for r in rows
    ]}


def load_tech_scan_signals() -> dict:
    """加载今日技术扫描信号。"""
    data = {"vcp": [], "watchlist": []}
    for fname, key in [("scan_vcp_default.json", "vcp"), ("scan_watchlist_tech_default.json", "watchlist")]:
        path = STOCK_DATA / fname
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                data[key] = raw.get("results", [])
            except Exception as e:
                logger.warning(f"{fname} 解析失败: {e}")
    return data


def load_sector_momentum() -> dict:
    """用 akshare 获取今日板块涨幅 + 主力资金流向。"""
    result = {"industry_top": [], "fund_inflow": [], "fund_outflow": []}
    try:
        df = safe_akshare_call(ak.stock_board_industry_name_em)
        if df is not None and not df.empty:
            cols = ["板块名称", "涨跌幅"]
            available = [c for c in cols if c in df.columns]
            top = df.nlargest(8, "涨跌幅")[available].to_dict("records")
            result["industry_top"] = [{k: str(v)[:30] for k, v in row.items()} for row in top]
    except Exception:
        pass
    try:
        df = safe_akshare_call(ak.stock_sector_fund_flow_rank, indicator="今日", sector_type="行业资金流向")
        if df is not None and not df.empty:
            top = df.nlargest(5, "主力净流入-净额")[["名称", "主力净流入-净额", "主力净流入-净占比"]].to_dict("records")
            bottom = df.nsmallest(5, "主力净流入-净额")[["名称", "主力净流入-净额", "主力净流入-净占比"]].to_dict("records")
            result["fund_inflow"] = [{k: str(v)[:25] for k, v in row.items()} for row in top]
            result["fund_outflow"] = [{k: str(v)[:25] for k, v in row.items()} for row in bottom]
    except Exception:
        pass
    return result


def collect_all() -> dict:
    """采集所有数据源，返回结构化 dict。"""
    start = time.time()
    logger.info("侦查日报: 采集数据...")

    portfolio_codes = load_portfolio_codes()
    hot_stocks = load_hot_stocks_recent(days=5)
    tech_scan = load_tech_scan_signals()
    sector_momentum = load_sector_momentum()
    vv_data = load_vv_insights(hours=96)

    logger.info(f"采集完成: {hot_stocks['total']}只热股 {len(sector_momentum['industry_top'])}个板块 "
                f"{len(tech_scan['vcp'])}个VCP {vv_data['total_videos']}条大V视频 | {time.time()-start:.1f}s")

    return {
        "portfolio_codes": portfolio_codes,
        "hot_stocks": hot_stocks,
        "tech_scan": tech_scan,
        "sector_momentum": sector_momentum,
        "vv_data": vv_data,
    }


def build_prompt(data: dict) -> str:
    """将所有数据格式化为 DeepSeek prompt。"""
    today = datetime.now(CST)
    portfolio_codes = data["portfolio_codes"]
    holding_str = ", ".join(portfolio_codes) if portfolio_codes else "空仓"

    lines = [f"# 侦查日报生成任务 | {today.strftime('%Y-%m-%d %A')}", ""]

    # 当前持仓（用于排除已有标的，聚焦新发现）
    lines.append(f"## 当前持仓代码: {holding_str}")
    lines.append("")

    # 板块动量
    sm = data["sector_momentum"]
    if sm["industry_top"]:
        lines.append("## 今日板块涨幅 TOP8")
        for s in sm["industry_top"]:
            lines.append(f"  {s['板块名称']}: {s['涨跌幅']}%")
        lines.append("")
    if sm["fund_inflow"]:
        lines.append("## 主力净流入 TOP5")
        for s in sm["fund_inflow"]:
            lines.append(f"  {s['名称']}: {s.get('主力净流入-净额','?')} ({s.get('主力净流入-净占比','?')})")
        lines.append("")

    # 热门股票趋势（近5日频繁上榜的）
    hs = data["hot_stocks"]
    if hs["items"]:
        lines.append("## 近5日热股频次排名")
        lines.append("| 代码 | 名称 | 上榜次数 | 最佳排名 | 平均涨幅 |")
        lines.append("|------|------|---------|---------|---------|")
        for s in hs["items"][:15]:
            lines.append(f"| {s['code']} | {s['name']} | {s['appear']} | {s['best_rank']} | {s['avg_chg']:+.1f}% |")
        lines.append("")

    # 技术扫描信号
    ts = data["tech_scan"]
    if ts["vcp"]:
        lines.append("## VCP 形态扫描")
        for s in ts["vcp"]:
            tag = "【已有持仓】" if s.get("code") in portfolio_codes else ""
            lines.append(f"  {tag}{s.get('code','?')}({s.get('price','?')}) 阶段:{s.get('phase','?')} 评分:{s.get('score','?')}")
        lines.append("")
    if ts["watchlist"]:
        lines.append("## 技术面评分 TOP")
        for s in ts["watchlist"][:8]:
            tag = "【已有持仓】" if s.get("code") in portfolio_codes else ""
            lines.append(f"  {tag}{s.get('code','?')} 评分:{s.get('score','?')} 均线:{s.get('ma_alignment','?')} MACD:{s.get('macd_signal','?')}")
        lines.append("")

    # 大V雷达
    vv_text = format_vv_for_prompt(data["vv_data"])
    if "无大V视频" not in vv_text:
        lines.append(vv_text)
        lines.append("")

    return "\n".join(lines)


def parse_insights(result: str) -> list[dict]:
    """从 DeepSeek 输出中结构化解析机会信号。"""
    insights = []
    current = {}
    for line in result.split("\n"):
        line = line.strip()
        # 匹配 "1. 标题 —— 信号强度 ★★★" 模式
        if line and line[0].isdigit() and ". " in line[:5]:
            if current:
                insights.append(current)
            current = {"title": line, "detail": "", "risk": ""}
        elif line.startswith("风险"):
            current["risk"] = line
        elif line.startswith("→"):
            current["detail"] = line
        elif current and line:
            if not current.get("detail"):
                current["detail"] = line
    if current:
        insights.append(current)
    return insights if insights else [{"title": result[:200], "detail": "", "risk": ""}]


def save_report(report_md: str, feishu_content: str) -> Path:
    """保存完整报告到文件。"""
    date_str = datetime.now(CST).strftime("%Y%m%d")
    out_path = STOCK_DATA / f"recon_report_{date_str}.md"
    out_path.write_text(report_md, encoding="utf-8")
    logger.info(f"报告已保存: {out_path}")
    return out_path


def format_feishu(insights: list[dict], sector_heat: dict, portfolio_codes: list[str]) -> str:
    """格式化为飞书短消息（10-15行）。"""
    lines = []
    if sector_heat:
        top = list(sector_heat.items())[:5]
        lines.append("板块温度: " + " ".join(f"{s}({c})" for s, c in top))
        lines.append("")

    for ins in insights:
        title = ins.get("title", "")
        detail = ins.get("detail", "")
        risk = ins.get("risk", "")
        # 检查是否涉及持仓
        has_holding = any(code in title + detail for code in portfolio_codes)
        prefix = "🔴 " if has_holding else ""
        lines.append(f"{prefix}{title}")
        if detail:
            lines.append(f"  {detail}")
        if risk:
            lines.append(f"  {risk}")

    return "\n".join(lines)


def main():
    start = time.time()
    logger.info("=" * 50)
    logger.info("侦查日报 v1 启动")

    # 1. 采集所有数据
    data = collect_all()

    # 2. 构建 prompt → DeepSeek 推理
    logger.info("构建 prompt...")
    prompt_data = build_prompt(data)

    system_prompt = """你是专业 A 股侦察兵。你的任务：
1. 基于今日收盘后的数据，找出明天值得关注的板块和个股
2. 重点发掘"不在当前持仓中"的新机会
3. 每条机会标注信号强度（★★★/★★/★）
4. 每个标的必须关联到板块
5. 与持仓冲突的标红说明

输出格式（Markdown）：
1. **[板块/标的]** — 核心理由 —— 信号强度
   → 侦查依据: [数据来源交叉印证]
   风险: [一句话风险提示]

每条都要有依据：是 hot_stocks 连续上榜？板块资金流入？大V提及 + 技术面共振？"""

    prompt = f"""生成今日侦查报告。以下是全部收盘数据：

{prompt_data}

要求：
1. **机会发现**（2-4条）：明天值得关注的板块和标的，必须标注信号强度
   - ★★★ = 多源交叉验证（板块+资金+技术+大V共振）
   - ★★ = 2个数据源支持
   - ★ = 单一数据源提示
2. **已有持仓关联**：持仓中出现了上述信号的标红提醒
3. **明日盯盘清单**：3-5个明天开盘需要观察的板块/标的
4. **风险提示**：板块过热/追高风险
"""
    logger.info("调用 DeepSeek 推理...")
    result = deepseek_reason(
        channel="review", prompt=prompt,
        system_prompt=system_prompt,
        temperature=0.4, max_tokens=4096,
    )

    if result.startswith("[错误]"):
        logger.error(f"DeepSeek 失败: {result}")
        # Fallback: 生成纯数据版
        result = _fallback_report(data)

    # 3. 格式化输出
    portfolio_codes = data["portfolio_codes"]
    vv_data = data["vv_data"]
    sector_heat = vv_data.get("sector_heat", {})

    report_md = f"""# 侦查日报 | {datetime.now(CST).strftime('%Y-%m-%d %H:%M')}

{result}

---

*数据源: HotStocks/板块资金/技术扫描/大V雷达 | 生成于 {datetime.now(CST).strftime('%H:%M')}*
"""
    save_report(report_md, "")

    # 4. 飞书推送
    try:
        insights = parse_insights(result)
        feishu_text = f"**侦查日报** | {datetime.now(CST).strftime('%m/%d')}\n\n"
        feishu_text += format_feishu(insights, sector_heat, portfolio_codes)
        ok = send_output("侦查日报", feishu_text, route="main", title=f"侦查日报 | {datetime.now(CST).strftime('%m/%d')}")
        logger.info(f"飞书发送: {'成功' if ok else '失败'}")
    except Exception as e:
        logger.warning(f"飞书发送失败: {e}")

    logger.info(f"侦查日报完成 | {time.time()-start:.1f}s")


def _fallback_report(data: dict) -> str:
    """DeepSeek 不可用时的纯数据回退版本。"""
    lines = []
    hs = data["hot_stocks"]
    if hs["items"]:
        lines.append("## 近5日高频上榜（非持仓）")
        portfolio = data["portfolio_codes"]
        for s in hs["items"][:10]:
            if s["code"] not in portfolio:
                lines.append(f"- {s['name']}({s['code']}): 上榜{s['appear']}次, 最佳排名#{s['best_rank']}")
    sm = data["sector_momentum"]
    if sm["fund_inflow"]:
        lines.append("\n## 资金净流入板块")
        for s in sm["fund_inflow"][:5]:
            lines.append(f"- {s['名称']}: {s.get('主力净流入-净额','?')}")
    vv = data["vv_data"]
    if vv.get("sector_heat"):
        lines.append("\n## 大V热议板块")
        for s, c in list(vv["sector_heat"].items())[:5]:
            lines.append(f"- {s}: {c}次提及")
    return "\n".join(lines)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s %(message)s")
    main()
