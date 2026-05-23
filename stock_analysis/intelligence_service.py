"""
intelligence_service.py — 情报部侦察/推演引擎

情报部定位：战场侦察部队。消费现有数据做交叉验证推演，不采集新数据。

用法:
    python intelligence_service.py recon     # 盘前侦察 (08:50)
    python intelligence_service.py deduce    # 收盘推演 (15:45)
    python intelligence_service.py status    # 更新部门状态
"""

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

from dept_status_protocol import publish_status, read_status

CST = timezone(timedelta(hours=8))
STOCK_DATA = Path("D:/1989n/stock_data")
INTEL_DIR = STOCK_DATA / "intel"
LATEST_JSON = INTEL_DIR / "intel_latest.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("intel")

HOLDINGS_JSON = STOCK_DATA / "concept_mapping.json"

# ── 数据加载 ───────────────────────────────────────────────────────────

def _load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("读取 %s 失败: %s", path.name, e)
        return default or {}


def _latest_file(pattern: str) -> Optional[Path]:
    """找到匹配 pattern 的最新文件。"""
    matches = sorted(STOCK_DATA.glob(pattern))
    return matches[-1] if matches else None


def _load_latest_news() -> list[dict]:
    """加载最近一期新闻。"""
    for pattern in ["news_intraday_*.json", "news_manual_*.json", "news_evening_*.json"]:
        fp = _latest_file(pattern)
        if fp:
            data = _load_json(fp, {}).get("data", [])
            if data:
                logger.info("  新闻: %s (%d条)", fp.name, len(data))
                return data
    return []


def _load_concepts() -> tuple[dict, dict]:
    """加载概念→成分股 和 关键词→持仓 映射。"""
    concept_stocks = _load_json(STOCK_DATA / "concept_stocks.json", {})
    holdings_data = _load_json(HOLDINGS_JSON, {})
    keyword_map = holdings_data.get("keyword_to_holdings", {})
    return concept_stocks, keyword_map


def _load_fund_flow() -> dict:
    """加载最新市场资金流向。"""
    d = _load_json(STOCK_DATA / "market_fund_flow_cache.json", {})
    items = d.get("data", {}).get("市场资金流向", [])
    return items[-1] if items else {}


def _load_vcp() -> list[dict]:
    """加载VCP技术扫描结果。"""
    d = _load_json(STOCK_DATA / "scan_vcp_default.json", {})
    return d.get("results", [])


def _load_portfolio() -> dict:
    """加载当前持仓。"""
    d = _load_json(HOLDINGS_JSON, {})
    return d.get("holdings", {})


def _load_sector() -> dict:
    """加载最新板块日数据。"""
    fp = _latest_file("sector_daily/*.json")
    if fp:
        d = _load_json(fp, {})
        return {
            "date": d.get("date"),
            "industry_boards": d.get("industry_boards", [])[:5],
            "concept_boards": d.get("concept_boards", [])[:5],
        }
    return {}


# ── 推理引擎 ───────────────────────────────────────────────────────────

# 常见A股概念关键词 → concept_stocks.json 中的概念名
_CONCEPT_KEYWORDS = {
    "半导体": "半导体", "芯片": "半导体", "集成电路": "半导体",
    "AI": "AI/算力", "人工智能": "AI/算力", "算力": "AI/算力",
    "光伏": "光伏/新能源", "新能源": "光伏/新能源",
    "新能源车": "新能源车", "电动车": "新能源车", "锂电": "新能源车",
    "机器人": "机器人", "智能制造": "机器人",
    "信创": "国产软件/信创", "软件": "国产软件/信创", "操作系统": "国产软件/信创",
    "军工": "军工", "航天": "军工", "国防": "军工",
    "医药": "医药", "创新药": "医药", "医疗": "医药",
    "消费": "大消费", "白酒": "大消费", "食品": "大消费",
    "地产": "房地产", "房地产": "房地产", "基建": "基建/建材",
    "储能": "储能", "氢能": "储能",
    "5G": "5G/6G", "6G": "5G/6G", "通信": "5G/6G",
    "金融": "大金融", "券商": "大金融", "银行": "大金融",
    "AI应用": "AI应用", "大模型": "AI应用", "AIGC": "AI应用",
    "低空经济": "低空经济",
}


def _extract_concepts(news_items: list[dict]) -> dict[str, int]:
    """从新闻标题提取概念词频。"""
    freq = {}
    for item in news_items:
        title = item.get("title", "")
        for keyword, concept in _CONCEPT_KEYWORDS.items():
            if keyword in title:
                freq[concept] = freq.get(concept, 0) + 1
    return dict(sorted(freq.items(), key=lambda x: -x[1]))


def _build_recon_signals(news_items: list[dict]) -> list[dict]:
    """盘前侦察：新闻→概念→技术共振→信号。"""
    signals = []

    concept_stocks, keyword_map = _load_concepts()
    concept_freq = _extract_concepts(news_items)
    fund_flow = _load_fund_flow()
    vcp_results = _load_vcp()
    portfolio = _load_portfolio()

    logger.info("  概念词频: %s", dict(list(concept_freq.items())[:8]))

    # 信号1: 高热度概念 + 有VCP形态的成分股
    hot_concepts = [c for c, f in concept_freq.items() if f >= 2]
    vcp_codes = {r["code"] for r in vcp_results}

    for concept in hot_concepts[:5]:
        stocks = concept_stocks.get(concept, [])
        if not stocks:
            continue

        # 找该概念下有VCP形态的股票
        vcp_in_concept = [s for s in stocks if s.get("code") in vcp_codes]
        # 找该概念中在持仓的股票
        in_portfolio = [s for s in stocks if s.get("code") in portfolio]

        if vcp_in_concept or in_portfolio:
            sig = {
                "signal": f"{concept} 概念活跃",
                "confidence": "high" if vcp_in_concept else "medium",
                "logic_chain": [],
                "related_stocks": [s["code"] for s in (vcp_in_concept or stocks[:3])],
                "in_portfolio": bool(in_portfolio),
            }
            if vcp_in_concept:
                sig["logic_chain"].append(f"新闻高频提及{concept}({concept_freq[concept]}次)")
                sig["logic_chain"].append(f"{len(vcp_in_concept)}只成分股出现VCP形态")
                sig["logic_chain"].append(f"VCP标的: {', '.join(s['name'] for s in vcp_in_concept[:3])}")
            if in_portfolio:
                sig["logic_chain"].append(f"持仓股: {', '.join(s['name'] for s in in_portfolio)}")
            if in_portfolio and vcp_in_concept:
                sig["confidence"] = "high"
            signals.append(sig)

    # 信号2: 主力资金方向（如有）
    if fund_flow:
        main_net = fund_flow.get("主力净流入-净额", 0)
        direction = "流入" if main_net > 0 else "流出"
        sig = {
            "signal": f"昨日主力资金{direction}",
            "confidence": "medium",
            "logic_chain": [
                f"主力净{direction}: {abs(main_net)/1e8:.1f}亿",
                f"超大单: {fund_flow.get('超大单净流入-净额', 0)/1e8:.1f}亿",
            ],
            "related_stocks": [],
            "in_portfolio": False,
        }
        signals.append(sig)

    # 信号3: 持仓股相关新闻
    for item in news_items:
        title = item.get("title", "")
        for code, info in portfolio.items():
            name = info.get("name", "")
            if name and name in title:
                signals.append({
                    "signal": f"持仓 {name}({code}) 出现新闻",
                    "confidence": "medium",
                    "logic_chain": [f"新闻: {title[:60]}"],
                    "related_stocks": [code],
                    "in_portfolio": True,
                })

    return signals


def _build_deduce_signals(news_items: list[dict], sector_data: dict) -> list[dict]:
    """收盘推演：新闻兑现度 + 资金验证 + VCP后续潜力。"""
    signals = []

    concept_stocks, keyword_map = _load_concepts()
    concept_freq = _extract_concepts(news_items)
    fund_flow = _load_fund_flow()
    vcp_results = _load_vcp()
    portfolio = _load_portfolio()

    logger.info("  日内概念词频: %s", dict(list(concept_freq.items())[:8]))

    # 信号1: 资金 vs 概念 — 资金是否兑现了新闻方向
    if fund_flow and concept_freq:
        top_concepts = list(concept_freq.keys())[:3]
        main_net = fund_flow.get("主力净流入-净额", 0)
        direction = "流入" if main_net > 0 else "流出"

        sig = {
            "signal": f"今日资金{direction} vs 热点({', '.join(top_concepts[:2])})",
            "confidence": "medium",
            "logic_chain": [
                f"主力净{direction}: {abs(main_net)/1e8:.1f}亿",
                f"新闻高频: {top_concepts[0]}({concept_freq[top_concepts[0]]}次)",
            ],
            "related_stocks": [],
            "in_portfolio": False,
        }
        # 主线信号辅助判断
        if main_net > 0 and len(concept_freq) >= 3:
            sig["confidence"] = "high"
            sig["logic_chain"].append("主力流入+多概念共振 → 短线环境偏暖")
        elif main_net < 0 and len(concept_freq) < 3:
            sig["confidence"] = "high"
            sig["logic_chain"].append("主力流出+无主线 → 明日谨慎")
        signals.append(sig)

    # 信号2: 板块表现
    if sector_data:
        boards = sector_data.get("industry_boards", [])
        if boards:
            top_board = boards[0]
            sig = {
                "signal": f"领涨板块: {top_board.get('board_name', '?')}",
                "confidence": "medium",
                "logic_chain": [f"涨幅: {top_board.get('change_pct', '?')}%",
                                f"主力净流入: {top_board.get('net_inflow', 0)/1e8:.1f}亿"],
                "related_stocks": [],
                "in_portfolio": False,
            }
            signals.append(sig)

    # 信号3: VCP形态股后续潜力
    for r in vcp_results:
        code = r.get("code", "")
        name = r.get("name", "")
        phase = r.get("phase", "")
        score = r.get("score", 0)
        if score >= 60:
            sig = {
                "signal": f"{name}({code}) VCP形态 {phase}",
                "confidence": "high" if score >= 75 else "medium",
                "logic_chain": [
                    f"VCP评分: {score}",
                    f"阶段: {phase}",
                    f"20日均线: {'上方' if r.get('above_ma20') else '下方'}",
                ],
                "related_stocks": [code],
                "in_portfolio": code in portfolio,
            }
            signals.append(sig)

    return signals


# ── 输出 ───────────────────────────────────────────────────────────────

def _write_reports(kind: str, signals: list[dict]):
    """写入 JSON + Markdown 简报。"""
    now = datetime.now(CST)
    date_str = now.strftime("%Y-%m-%d")
    timestamp = now.isoformat()

    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "kind": kind,
        "timestamp": timestamp,
        "signal_count": len(signals),
        "signals": signals,
    }

    # JSON 结构化
    fp_json = INTEL_DIR / f"intel_{kind}_{date_str}.json"
    fp_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    # 最新快照
    LATEST_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("  JSON -> %s", fp_json.name)

    # Markdown 简报
    title = "盘前侦察" if kind == "recon" else "收盘推演"
    lines = [
        f"# 情报部 {title} | {now.strftime('%m/%d %H:%M')}",
        "",
    ]
    if not signals:
        lines.append("无显著信号。")
    else:
        for i, s in enumerate(signals, 1):
            conf_icon = {"high": "★★★", "medium": "★★", "low": "★"}.get(s["confidence"], "★")
            pf_tag = " [持仓]" if s.get("in_portfolio") else ""
            lines.append(f"### {conf_icon} 信号{i}: {s['signal']}{pf_tag}")
            for step in s.get("logic_chain", []):
                lines.append(f"- {step}")
            if s.get("related_stocks"):
                lines.append(f"- 相关: {', '.join(s['related_stocks'][:5])}")
            lines.append("")

    lines.append(f"---\n*情报部 · {timestamp}*")
    md = "\n".join(lines)

    fp_md = INTEL_DIR / f"intel_{kind}_{date_str}.md"
    fp_md.write_text(md, encoding="utf-8")
    logger.info("  MD -> %s", fp_md.name)

    return md


def _publish_status(health: str, issues: list[str] = None):
    """通过 dept_status_protocol 发布部门状态。"""
    status = {
        "health": health,
        "timestamp": datetime.now(CST).isoformat(),
        "issues": [{"message": m, "severity": "warning"} for m in (issues or [])],
    }
    publish_status("intelligence", status)
    logger.info("  状态已发布: %s", health)


# ── 入口 ───────────────────────────────────────────────────────────────

def run_recon():
    """盘前侦察入口。"""
    logger.info("[情报部] 盘前侦察启动...")
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    news = _load_latest_news()
    if not news:
        logger.warning("  无新闻数据可用")
        _publish_status("degraded", ["无新闻数据"])
        return 1

    signals = _build_recon_signals(news)
    md = _write_reports("recon", signals)

    issues = [] if signals else ["无信号产出"]
    _publish_status("healthy" if signals else "degraded", issues)
    print(md)
    return 0


def run_deduce():
    """收盘推演入口。"""
    logger.info("[情报部] 收盘推演启动...")
    INTEL_DIR.mkdir(parents=True, exist_ok=True)

    news = _load_latest_news()
    sector = _load_sector()

    if not news:
        logger.warning("  无新闻数据")
        _publish_status("degraded", ["无新闻数据"])
        return 1

    signals = _build_deduce_signals(news, sector)
    md = _write_reports("deduce", signals)

    issues = [] if signals else ["无信号产出"]
    _publish_status("healthy" if signals else "degraded", issues)
    print(md)
    return 0


def run_status():
    """更新部门状态（无推理，仅健康检查）。"""
    _publish_status("healthy")
    print("情报部状态已更新")
    return 0


def main():
    parser = argparse.ArgumentParser(description="情报部侦察/推演引擎")
    parser.add_argument("command", choices=["recon", "deduce", "status"],
                        help="recon=盘前侦察  deduce=收盘推演  status=更新状态")
    args = parser.parse_args()

    fn = {"recon": run_recon, "deduce": run_deduce, "status": run_status}[args.command]
    sys.exit(fn())


if __name__ == "__main__":
    main()
