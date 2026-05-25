"""
巨潮资讯公告采集 — A股上市公司官方披露
===========================================
数据来源: cninfo.com.cn (证监会指定信息披露平台)
采集方式: hisAnnouncement/query API → 公告标题+PDF链接

设计原则:
  1. 仅早间模式调用 (run_morning 后置), 不影响盘中快讯
  2. 独立 try/except, 崩了不传染主流程
  3. 输出独立 JSON 文件, 不修改现有 news JSON 结构
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger("news_cninfo")

# === 路径 ===
STOCK_DATA_DIR = Path("D:/1989n/stock_data")
CONCEPT_MAPPING_PATH = STOCK_DATA_DIR / "concept_mapping.json"

# === API ===
CNINFO_QUERY_URL = "https://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_DISCLOSURE_URL = "https://www.cninfo.com.cn/new/disclosure"
CNINFO_PAGE_SIZE = 50
CNINFO_TIMEOUT = 15

CST = timezone(timedelta(hours=8))

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Content-Type": "application/x-www-form-urlencoded",
}


# ====================================================================
#  数据获取
# ====================================================================

def fetch_announcements(days: int = 1) -> list[dict]:
    """
    从巨潮API获取最近N天的上市公司公告。

    Returns:
        list[dict]: 每条含 code, name, title, time(unix秒), type, url, pdf_url
    """
    end_date = datetime.now(CST)
    start_date = end_date - timedelta(days=days)

    payload = {
        "pageNum": 1,
        "pageSize": CNINFO_PAGE_SIZE,
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": "",
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": f"{start_date.strftime('%Y-%m-%d')}~{end_date.strftime('%Y-%m-%d')}",
        "sortName": "",
        "sortType": "desc",
        "isHLtitle": "true",
    }

    try:
        resp = requests.post(
            CNINFO_QUERY_URL, data=payload, headers=_HEADERS, timeout=CNINFO_TIMEOUT
        )
        resp.raise_for_status()
        body = resp.json()

    except Exception as e:
        logger.error(f"[巨潮] API请求失败: {e}")
        return []

    raw = body.get("announcements") or []
    total = body.get("totalAnnouncement", 0)
    logger.info(f"[巨潮] API返回 {len(raw)} 条 (共 {total} 条)")

    items = []
    for a in raw:
        ts_ms = a.get("announcementTime", 0)
        pub_time = int(ts_ms / 1000) if ts_ms else 0
        adjunct = a.get("adjunctUrl", "")
        pdf_url = f"{CNINFO_DISCLOSURE_URL}/{adjunct}" if adjunct else ""

        items.append({
            "code": a.get("secCode", ""),
            "name": a.get("secName", ""),
            "title": a.get("announcementTitle", ""),
            "time": pub_time,
            "type": a.get("announcementType", ""),
            "url": pdf_url,
        })

    return items


# ====================================================================
#  持仓过滤
# ====================================================================

def _load_holdings_codes() -> list[str]:
    """从 concept_mapping.json 获取当前持仓代码列表。"""
    try:
        if CONCEPT_MAPPING_PATH.exists():
            data = json.loads(CONCEPT_MAPPING_PATH.read_text(encoding="utf-8"))
            return list(data.get("holdings", {}).keys())
    except Exception as e:
        logger.warning(f"[巨潮] 加载持仓映射失败: {e}")
    return []


def filter_by_holdings(items: list[dict], codes: list[str]) -> list[dict]:
    """只保留持仓股的公告。"""
    code_set = set(codes)
    return [i for i in items if i["code"] in code_set]


# ====================================================================
#  保存
# ====================================================================

def save_announcements(items: list[dict], holdings_items: list[dict]) -> str:
    """
    保存公告到 JSON 文件。

    Returns:
        str: 文件路径
    """
    now = datetime.now(CST)
    fname = f"cninfo_{now.strftime('%Y%m%d_%H%M')}.json"
    filepath = STOCK_DATA_DIR / fname

    output = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "total_count": len(items),
        "holdings_count": len(holdings_items),
        "holdings": holdings_items,
    }

    STOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    filepath.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if holdings_items:
        logger.info(
            f"[巨潮] 保存 {filepath.name}"
            f" ({len(holdings_items)} 条持仓公告 / {len(items)} 条总量)"
        )
    else:
        logger.info(f"[巨潮] 保存 {filepath.name} (持仓无公告)")
    return str(filepath)


# ====================================================================
#  对外接口
# ====================================================================

def fetch_and_save(days: int = 1) -> bool:
    """
    采集巨潮公告 → 过滤持仓 → 保存JSON。

    设计为主流程的后置钩子:
    - 独立 try/except, 异常不抛给调用方
    - 保存到独立 JSON 文件, 不影响现有管线

    Returns:
        bool: True=执行成功(含0条), False=异常
    """
    try:
        items = fetch_announcements(days=days)
        codes = _load_holdings_codes()
        if codes:
            holdings_items = filter_by_holdings(items, codes)
        else:
            holdings_items = []

        save_announcements(items, holdings_items)
        return True

    except Exception as e:
        logger.error(f"[巨潮] 执行异常: {e}")
        return False
