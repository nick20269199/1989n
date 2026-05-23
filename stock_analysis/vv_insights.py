"""
vv_insights.py — 大V雷达数据查询 + 板块/标的提取

供 morning_brief_agent.py 和 daily_task.py 调用，获取近期大V观点摘要。
"""

import logging
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

logger = logging.getLogger("vv_insights")

RADAR_DB = Path("D:/1989n/stock_data/vv_radar.db")
CST = timezone(timedelta(hours=8))

# 常见板块关键词映射（描述中的 #标签 → 板块名）
SECTOR_ALIASES = {
    "cpo": "CPO/光通信",
    "光纤": "光纤光缆",
    "航天": "航天军工",
    "马斯克": "马斯克概念",
    "机器人": "人形机器人",
    "ai": "AI",
    "人工智能": "AI",
    "芯片": "半导体/芯片",
    "半导体": "半导体/芯片",
    "算力": "算力",
    "低空": "低空经济",
    "光伏": "光伏",
    "储能": "储能",
    "新能源": "新能源",
    "汽车": "汽车/新能源车",
    "消费电子": "消费电子",
    "医药": "医药",
    "医疗": "医药",
    "通讯": "通信",
    "5g": "5G/通信",
    "军工": "军工",
    "证券": "券商",
    "银行": "银行",
    "地产": "房地产",
    "基建": "基建",
    "消费": "消费",
    "煤炭": "煤炭",
    "有色": "有色金属",
    "黄金": "黄金",
}


def _get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(RADAR_DB))
    conn.row_factory = sqlite3.Row
    return conn


def extract_sectors(text: str) -> list[str]:
    """从视频描述中提取涉及板块（基于 #标签 + 关键词匹配）。"""
    found = set()
    # 提取 #标签
    tags = re.findall(r"#(\w+)", text)
    for tag in tags:
        tag_lower = tag.lower()
        for alias, sector in SECTOR_ALIASES.items():
            if alias in tag_lower or tag_lower in alias:
                found.add(sector)
    # 全文关键词匹配
    text_lower = text.lower()
    for alias, sector in SECTOR_ALIASES.items():
        if alias in text_lower:
            found.add(sector)
    return sorted(found)


def extract_tickers(text: str) -> list[str]:
    """从视频描述中提取疑似股票代码（6位数字）。"""
    return re.findall(r"\b(\d{6})\b", text)


def load_vv_insights(hours: int = 96, max_per_author: int = 3) -> dict:
    """查询最近 N 小时的大V视频观点摘要。

    Args:
        hours: 回溯小时数
        max_per_author: 每个大V最多取几条

    Returns:
        {
            "total_videos": int,
            "author_count": int,
            "insights": [
                {
                    "vv_name": str,
                    "vv_id": str,
                    "sectors": [str, ...],
                    "tickers": [str, ...],
                    "summary": str,
                    "posted_at": str,
                },
                ...
            ],
            "sector_heat": {板块: 提及次数, ...},
        }
    """
    cutoff = datetime.now(CST).timestamp() - hours * 3600

    conn = _get_db()
    cur = conn.cursor()

    # 查询近期转录过的视频（有描述文本的）
    cur.execute("""
        SELECT v.aweme_id, v.vv_id, v.desc, v.create_time,
               f.name AS vv_name
        FROM vv_videos v
        LEFT JOIN vv_follows f ON v.vv_id = f.id
        WHERE v.push_status = 'transcribed'
          AND v.create_time >= ?
          AND v.desc IS NOT NULL
          AND v.desc != ''
        ORDER BY v.create_time DESC
    """, (int(cutoff),))
    rows = cur.fetchall()
    conn.close()

    if not rows:
        logger.info(f"近{hours}小时无大V视频")
        return {"total_videos": 0, "author_count": 0, "insights": [], "sector_heat": {}}

    # 按大V分组，每V限流
    by_author = defaultdict(list)
    for r in rows:
        by_author[r["vv_id"]].append(r)

    insights = []
    sector_counter = defaultdict(int)

    for vv_id, videos in by_author.items():
        vv_name = videos[0]["vv_name"] or vv_id
        for v in videos[:max_per_author]:
            desc = v["desc"].strip()
            sectors = extract_sectors(desc)
            tickers = extract_tickers(desc)
            ts = datetime.fromtimestamp(v["create_time"], tz=CST).strftime("%m-%d %H:%M")
            summary = desc[:120]

            for s in sectors:
                sector_counter[s] += 1

            insights.append({
                "vv_name": vv_name,
                "vv_id": vv_id,
                "sectors": sectors,
                "tickers": tickers,
                "summary": summary,
                "posted_at": ts,
            })

    # 按热度排序
    insights.sort(key=lambda x: x["posted_at"], reverse=True)
    sector_heat = dict(sorted(sector_counter.items(), key=lambda x: -x[1]))

    return {
        "total_videos": len(rows),
        "author_count": len(by_author),
        "insights": insights,
        "sector_heat": sector_heat,
    }


def format_vv_for_prompt(vv_data: dict) -> str:
    """将大V洞察格式化为 prompt 可用的文本块。"""
    if not vv_data or vv_data["total_videos"] == 0:
        return "（近48小时无大V视频）"

    hours = 96  # 默认窗口
    lines = []
    lines.append(f"## 大V雷达（近{hours//24}d {vv_data['author_count']}位大V, {vv_data['total_videos']}条视频）")
    lines.append("")

    if vv_data.get("sector_heat"):
        lines.append("【板块热度】")
        for sector, count in list(vv_data["sector_heat"].items())[:8]:
            bar = "■" * min(count, 5)
            lines.append(f"  {sector}: {bar} ({count}次)")
        lines.append("")

    lines.append("【逐条观点】")
    for ins in vv_data["insights"]:
        tag_str = " ".join(f"#{s}" for s in ins["sectors"][:3]) if ins["sectors"] else ""
        tick_str = f" 标的:{','.join(ins['tickers'][:3])}" if ins["tickers"] else ""
        lines.append(f"- [{ins['posted_at']}] {ins['vv_name']}")
        lines.append(f"  {ins['summary']}")
        if tag_str:
            lines.append(f"  {tag_str}{tick_str}")

    return "\n".join(lines)


def format_vv_for_feishu(vv_data: dict, max_items: int = 5) -> str:
    """将大V洞察格式化为飞书短消息。"""
    if not vv_data or vv_data["total_videos"] == 0:
        return ""

    lines = [f"**大V雷达** ({vv_data['author_count']}位大V, {vv_data['total_videos']}条)"]

    if vv_data.get("sector_heat"):
        top = list(vv_data["sector_heat"].items())[:5]
        lines.append("热议板块: " + " ".join(f"{s}({c})" for s, c in top))

    for ins in vv_data["insights"][:max_items]:
        tag_str = " ".join(f"#{s}" for s in ins["sectors"][:2]) if ins["sectors"] else ""
        lines.append(f"- [{ins['vv_name']}] {ins['summary'][:60]} {tag_str}")

    return "\n".join(lines)
