#!D:/Python314/python
"""
财经新闻采集调度器 - Financial News Collection Scheduler
========================================================
由 cron 定时任务调用，支持四种模式:
  morning   - 盘前新闻汇总 (早间)
  intraday  - 盘中实时快讯 (每30分钟)
  evening   - 盘后新闻汇总 (晚间22:00)
  auto      - 自动检测当前时间和市场状态，选择合适模式

数据来源: 财联社 (cls.cn) 电报快讯
存储: JSON 文件 + SQLite 数据库
通知: 飞书 Webhook (morning/evening 模式)
"""

from error_capture import trap; trap()

import json
import logging
import os
import sqlite3
import sys
import time
import traceback
from datetime import datetime, time as dt_time, timezone, timedelta
from pathlib import Path
from typing import Optional

import requests

# === 项目导入 ===
from config import (
    CLS_NEWS_FLASH_URL,
    HEADERS,
    PROJECT_DIR,
    STOCK_DATA_DIR,
    NEWS_INTRADAY_INTERVAL_MINUTES,
    NEWS_MARKET_OPEN,
    NEWS_MARKET_CLOSE,
    FEISHU_BOT_CHAT_ID,
    FEISHU_ROUTES,
    DATABASE_PATH,
    SINA_NEWS_ROLL_URL,
)
from database import save_news, get_db
from data_source_router import EASTMONEY_BLOCKED

# 飞书发送器 (可选依赖)
try:
    from feishu_sender import send_feishu_message
except ImportError:
    send_feishu_message = None
    logging.warning("feishu_sender 未安装，飞书通知功能不可用")

# === 日志配置 ===
LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("news_scheduler")
logger.setLevel(logging.DEBUG)

# 文件 handler
fh = logging.FileHandler(LOG_DIR / "news_scheduler.log", encoding="utf-8")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

# 控制台 handler
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logger.addHandler(fh)
logger.addHandler(ch)

# === 常量 ===
CST = timezone(timedelta(hours=8))  # 中国标准时间 UTC+8
MAX_RETRIES = 3
RETRY_DELAY_BASE = 2  # 基础重试延迟 (秒)，每次重试翻倍
REQUEST_TIMEOUT = 20  # 请求超时 (秒)
CLS_API_RN = 50  # 每次拉取新闻条数
DEDUP_WINDOW_HOURS = 24  # 去重窗口 (小时)

# 盘中交易时间
MARKET_OPEN_TIME = dt_time(9, 30)
MARKET_CLOSE_TIME = dt_time(15, 0)
LUNCH_START = dt_time(11, 30)
LUNCH_END = dt_time(13, 0)


# ============================================================================
#  工具函数
# ============================================================================

def now_cst() -> datetime:
    """返回当前北京时间 (UTC+8)。"""
    return datetime.now(CST)


def today_str() -> str:
    """返回当前北京时间的日期字符串 YYYY-MM-DD。"""
    return now_cst().strftime("%Y-%m-%d")


def timestamp_str() -> str:
    """返回当前北京时间的完整时间戳字符串 YYYY-MM-DD HH:MM:SS。"""
    return now_cst().strftime("%Y-%m-%d %H:%M:%S")


def ts_to_str(ts: int) -> str:
    """将 Unix 时间戳 (秒) 转为北京时间字符串 YYYY-MM-DD HH:MM:SS。"""
    return datetime.fromtimestamp(ts, tz=CST).strftime("%Y-%m-%d %H:%M:%S")


def is_trading_day(dt_obj: datetime) -> bool:
    """判断是否为交易日 (周一至周五，不含中国法定节假日)。"""
    # 基础判断: 周一至周五
    if dt_obj.weekday() >= 5:
        return False
    # TODO: 接入中国法定节假日日历，排除春节/国庆等长假
    return True


def is_market_open() -> bool:
    """判断当前是否在 A 股盘中交易时间 (9:30-11:30, 13:00-15:00)。"""
    now = now_cst()
    if not is_trading_day(now):
        return False
    t = now.time()
    # 上午盘: 9:30 - 11:30
    if MARKET_OPEN_TIME <= t < LUNCH_START:
        return True
    # 下午盘: 13:00 - 15:00
    if LUNCH_END <= t <= MARKET_CLOSE_TIME:
        return True
    return False


def is_pre_market() -> bool:
    """判断当前是否在盘前 (交易日的 0:00-9:30)。"""
    now = now_cst()
    if not is_trading_day(now):
        return False
    return now.time() < MARKET_OPEN_TIME


def is_post_market_evening() -> bool:
    """判断当前是否在晚间摘要时段 (21:00 之后)。"""
    return now_cst().hour >= 21


def deduce_auto_mode() -> str:
    """根据当前时间和市场状态自动判断应执行的模式。"""
    if is_market_open():
        logger.info("[自动模式] 当前处于盘中交易时段 -> intraday")
        return "intraday"
    if is_pre_market():
        logger.info("[自动模式] 当前处于盘前时段 -> morning")
        return "morning"
    if is_post_market_evening():
        logger.info("[自动模式] 当前处于晚间时段 -> evening")
        return "evening"
    # 默认: 盘后但未到晚间 (15:00-21:00) 或非交易日 -> 执行早间模式收集近期新闻
    logger.info("[自动模式] 盘后/非交易日 -> morning (收集近期新闻)")
    return "morning"


# ============================================================================
#  CLS API 数据获取
# ============================================================================

def _clean_html(raw: str) -> str:
    """清理 HTML 标签和实体，保留纯文本。"""
    import re
    text = raw.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def fetch_cls_telegraph(rn: int = CLS_API_RN, pn: int = 0) -> list[dict]:
    """
    从财联社 API 拉取电报快讯。

    尝试两种端点路径:
      1. nodeapi/telegraphList (GET, 更稳定)
      2. api/sw (POST, 备选)

    Returns:
        list[dict]: 新闻条目列表，每项含 id/title/ctime/level/stock_list/subject
    """
    headers = {**HEADERS, "Referer": "https://www.cls.cn/telegraph"}

    # --- 方法1: nodeapi GET ---
    for attempt in range(MAX_RETRIES):
        try:
            url = "https://www.cls.cn/nodeapi/telegraphList"
            params = {"rn": rn, "pn": pn, "subscribed": 0}
            resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            body = resp.json()
            if body.get("error") == 0 and body.get("data", {}).get("roll_data"):
                data = body["data"]["roll_data"]
                logger.info(f"[CLS API] nodeapi 获取成功: {len(data)} 条新闻")
                return data
            else:
                logger.warning(f"[CLS API] nodeapi 返回异常: error={body.get('error')}, msg={body.get('msg', '')}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"[CLS API] nodeapi 请求失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_DELAY_BASE * (2 ** attempt)
                time.sleep(delay)
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[CLS API] nodeapi 响应解析失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE * (2 ** attempt))

    # --- 方法2: api/sw POST (备选) ---
    logger.info("[CLS API] 切换到 SW API 备选端点...")
    for attempt in range(MAX_RETRIES):
        try:
            payload = {
                "app": "CailianpressWeb",
                "os": "web",
                "sv": "8.4.6",
                "type": "telegraph",
                "rn": rn,
                "pn": pn,
            }
            resp = requests.post(
                CLS_NEWS_FLASH_URL,
                json=payload,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") == 200 and body.get("data", {}).get("roll_data"):
                data = body["data"]["roll_data"]
                logger.info(f"[CLS API] SW API 获取成功: {len(data)} 条新闻")
                return data
            else:
                logger.warning(f"[CLS API] SW API 返回异常: code={body.get('code')}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"[CLS API] SW API 请求失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE * (2 ** attempt))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[CLS API] SW API 响应解析失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE * (2 ** attempt))

    logger.error("[CLS API] 所有端点尝试均失败，返回空列表")
    return []


# ============================================================================
#  新浪财经滚动新闻
# ============================================================================

def fetch_sina_news(knum: int = 50) -> list[dict]:
    """
    从新浪财经滚动新闻 API 拉取新闻。

    API: feed.mix.sina.com.cn/api/roll/get
    Params: pageid=153, lid=2516 (国内财经), knum=N

    Returns:
        list[dict]: 统一格式新闻列表
    """
    headers = {**HEADERS, "Referer": "https://finance.sina.com.cn/"}
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                SINA_NEWS_ROLL_URL,
                params={"pageid": 153, "lid": 2516, "knum": knum},
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            result = body.get("result", {})
            data = result.get("data", [])
            if not isinstance(data, list) or not data:
                logger.warning(f"[新浪] API 返回空数据 (尝试 {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_BASE * (2 ** attempt))
                continue

            items = []
            for item in data:
                title = item.get("title", "").strip()
                if not title:
                    continue
                ctime = item.get("ctime", "")
                # ctime 格式为 "2026-05-23 21:35:00"
                pub_time = ctime if ctime else ""
                link = item.get("link", "")
                items.append({
                    "title": _clean_html(title),
                    "source": "新浪财经",
                    "url": link if link.startswith("http") else "",
                    "sentiment": "",
                    "related_stocks": "",
                    "category": item.get("cat", ""),
                    "pub_time": pub_time,
                })

            logger.info(f"[新浪] 获取成功: {len(items)} 条新闻")
            return items

        except (requests.exceptions.RequestException, json.JSONDecodeError, ValueError) as e:
            logger.warning(f"[新浪] 请求失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE * (2 ** attempt))

    logger.error("[新浪] 所有尝试均失败，返回空列表")
    return []


# ============================================================================
#  东方财富快讯 (受 WAF 限制，可能不可用)
# ============================================================================

def fetch_eastmoney_news() -> list[dict]:
    """
    从东方财富获取财经快讯/资讯。

    受 WAF 封锁影响 (EASTMONEY_BLOCKED)，如果已封锁则直接跳过。
    使用 push2 行情接口的公告字段作为替代。

    Returns:
        list[dict]: 统一格式新闻列表
    """
    if EASTMONEY_BLOCKED:
        logger.debug("[东方财富] WAF 封锁中，跳过")
        return []

    headers = {**HEADERS, "Referer": "https://www.eastmoney.com/"}
    items = []

    for attempt in range(MAX_RETRIES):
        try:
            # 使用东方财富 push2 快讯接口
            resp = requests.get(
                "https://push2.eastmoney.com/api/qt/ulist.np/get",
                params={
                    "fltt": 2,
                    "fields": "f2,f3,f4,f12,f14",
                    "secids": "1.000001,0.399001,0.399006",
                    "ut": "fa5fd1943c7b386f172d6893dbf38dc7",
                },
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            data = body.get("data", {})
            diff = data.get("diff", [])
            if not diff:
                logger.warning(f"[东方财富] 无返回数据 (尝试 {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_BASE * (2 ** attempt))
                continue

            # 这个接口返回的是指数行情，不是新闻
            # 尝试另一个接口获取快讯
            break
        except requests.exceptions.RequestException as e:
            logger.warning(f"[东方财富] API 请求失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if "403" in str(e) or "WAF" in str(e):
                logger.warning("[东方财富] 触发 WAF 封锁，标记为不可用")
                # 注意：这里不修改全局 EASTMONEY_BLOCKED，避免影响行情模块
                return []
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE * (2 ** attempt))

    # 尝试东方财富资讯列表接口
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                "https://push2ex.eastmoney.com/getStockNews",
                params={
                    "code": "000001",
                    "market": 1,
                    "pagesize": 50,
                    "pageindex": 0,
                },
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            body = resp.json()
            news_list = body.get("data", {}).get("list", []) if isinstance(body, dict) else []
            if not news_list:
                logger.warning(f"[东方财富-资讯] 无返回数据 (尝试 {attempt + 1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY_BASE * (2 ** attempt))
                continue

            for item in news_list:
                title = item.get("title", item.get("Art_Title", "")).strip()
                if not title:
                    continue
                pub_time = item.get("ShowDate", item.get("Art_CreateTime", ""))
                art_code = item.get("Art_Code", item.get("art_code", ""))
                items.append({
                    "title": _clean_html(title),
                    "source": "东方财富",
                    "url": f"https://www.eastmoney.com/a/{art_code}.html" if art_code else "",
                    "sentiment": "",
                    "related_stocks": "",
                    "category": item.get("categories", ""),
                    "pub_time": str(pub_time) if pub_time else "",
                })

            logger.info(f"[东方财富] 获取成功: {len(items)} 条新闻")
            return items

        except requests.exceptions.RequestException as e:
            logger.warning(f"[东方财富-资讯] 请求失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if "403" in str(e):
                return []  # WAF 封锁，不重试
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE * (2 ** attempt))
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            logger.warning(f"[东方财富-资讯] 解析失败 (尝试 {attempt + 1}/{MAX_RETRIES}): {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY_BASE * (2 ** attempt))

    logger.warning("[东方财富] 所有接口尝试均失败")
    return []


# ============================================================================
#  多源聚合
# ============================================================================

def collect_from_all_sources() -> tuple[list[dict], list[str]]:
    """
    从所有可用新闻源采集，合并返回。

    顺序: 财联社 → 新浪财经 → 东方财富 (未封锁时)
    每个源独立 try/except，一个源失败不影响其他源。

    Returns:
        tuple: (all_news_items, source_names)
        - all_news_items: 合并后的新闻列表（未去重）
        - source_names: 成功采集的源名称列表
    """
    all_items: list[dict] = []
    sources: list[str] = []

    # 1. 财联社 (主源)
    try:
        cls_raw = fetch_cls_telegraph(rn=CLS_API_RN)
        if cls_raw:
            cls_items = transform_news(cls_raw)
            all_items.extend(cls_items)
            sources.append("财联社")
            logger.info(f"[多源] 财联社: {len(cls_items)} 条")
    except Exception as e:
        logger.warning(f"[多源] 财联社采集异常: {e}")

    # 2. 新浪财经
    try:
        sina_items = fetch_sina_news()
        if sina_items:
            all_items.extend(sina_items)
            sources.append("新浪财经")
            logger.info(f"[多源] 新浪财经: {len(sina_items)} 条")
    except Exception as e:
        logger.warning(f"[多源] 新浪财经采集异常: {e}")

    # 3. 东方财富 (仅当未被 WAF 封锁)
    if not EASTMONEY_BLOCKED:
        try:
            em_items = fetch_eastmoney_news()
            if em_items:
                all_items.extend(em_items)
                sources.append("东方财富")
                logger.info(f"[多源] 东方财富: {len(em_items)} 条")
        except Exception as e:
            logger.warning(f"[多源] 东方财富采集异常: {e}")
    else:
        logger.info("[多源] 东方财富 WAF 封锁中，跳过")

    logger.info(f"[多源] 共采集 {len(all_items)} 条, 来源: {sources}")
    return all_items, sources


# ============================================================================
#  去重逻辑
# ============================================================================

def get_existing_titles(hours: int = DEDUP_WINDOW_HOURS) -> set[str]:
    """从数据库获取最近 N 小时内的新闻标题集合，用于去重。"""
    try:
        with get_db() as db:
            rows = db.execute(
                "SELECT title FROM news WHERE collected_at > datetime('now', 'localtime', ?)",
                (f"-{hours} hours",),
            ).fetchall()
        titles = {row[0] for row in rows}
        logger.debug(f"[去重] 数据库现有 {len(titles)} 条近期标题")
        return titles
    except sqlite3.OperationalError as e:
        logger.warning(f"[去重] 数据库查询失败 (可能表不存在): {e}")
        return set()
    except Exception as e:
        logger.error(f"[去重] 获取现有标题失败: {e}")
        return set()


def deduplicate_news(raw_items: list[dict], existing_titles: set[str]) -> list[dict]:
    """去除已在数据库中的重复新闻 (按标题匹配)。"""
    unique = []
    for item in raw_items:
        title = item.get("title", "")
        if title not in existing_titles:
            unique.append(item)
        else:
            logger.debug(f"[去重] 跳过重复: {title[:80]}...")
    skipped = len(raw_items) - len(unique)
    if skipped > 0:
        logger.info(f"[去重] 过滤 {skipped} 条重复新闻，保留 {len(unique)} 条")
    return unique


# ============================================================================
#  数据转换与存储
# ============================================================================

def transform_news(cls_items: list[dict]) -> list[dict]:
    """
    将 CLS API 原始数据转换为数据库和 JSON 输出格式。

    CLS 输入字段:
      id, title, brief, content, ctime (unix秒), level, subject[], stock_list[]
    输出字段:
      title, source="cls.cn", url, sentiment, related_stocks, category, pub_time
    """
    results = []
    for item in cls_items:
        title = _clean_html(item.get("title", "") or item.get("brief", ""))
        if not title:
            continue

        news_id = item.get("id", "")
        ctime = item.get("ctime", 0)
        pub_time = ts_to_str(ctime) if ctime else ""

        # 关联股票 — CLS StockID 格式: "sz002031" 或 "sh603986"
        stock_list = item.get("stock_list") or []
        if isinstance(stock_list, list):
            codes = []
            for s in stock_list:
                if isinstance(s, dict):
                    sid = s.get("StockID", "") or s.get("code", "")
                    # 去掉 sz/sh 前缀，保留纯数字代码
                    clean = sid.replace("sz", "").replace("sh", "").replace("bj", "")
                    if clean.isdigit():
                        codes.append(clean)
                elif s and str(s).strip():
                    codes.append(str(s).strip())
            related_stocks = ",".join(codes)
        else:
            related_stocks = ""

        # 题材/主题
        subjects = item.get("subject") or item.get("subjects") or []
        if isinstance(subjects, list):
            category = ",".join(str(s) for s in subjects)
        else:
            category = str(subjects) if subjects else ""

        results.append({
            "title": title,
            "source": "cls.cn",
            "url": f"https://www.cls.cn/detail/{news_id}" if news_id else "",
            "sentiment": "",  # 快讯不含情绪标签
            "related_stocks": related_stocks,
            "category": category,
            "pub_time": pub_time,
        })
    return results


def save_news_json(news_items: list[dict], mode: str) -> str:
    """
    将新闻保存为 JSON 文件。

    文件名格式: news_{mode}_{YYYYMMDD_HHMM}.json
    Returns: 文件路径
    """
    now = now_cst()

    # morning 模式文件名使用 manual 前缀 (匹配现有文件命名)
    mode_fname = "manual" if mode == "morning" else mode
    fname = f"news_{mode_fname}_{now.strftime('%Y%m%d_%H%M')}.json"
    filepath = STOCK_DATA_DIR / fname

    # 构建输出格式 (匹配现有文件格式)
    market_status = "trading" if is_market_open() else "closed"

    type_map = {
        "morning": "财经快讯-manual",
        "intraday": "财经快讯-intraday",
        "evening": "财经快讯-evening",
    }
    news_type = type_map.get(mode, "财经快讯")

    # 保留完整字段：title + time + related_stocks + category
    rich_data = []
    for item in news_items:
        entry = {
            "title": item["title"],
            "time": item["pub_time"],
        }
        # CLS API 自带的股票标注（免费数据已有）
        if item.get("related_stocks"):
            entry["related_stocks"] = item["related_stocks"]
        if item.get("category"):
            entry["category"] = item["category"]
        if item.get("url"):
            entry["url"] = item["url"]
        rich_data.append(entry)

    output = {
        "type": news_type,
        "time": timestamp_str(),
        "market_status": market_status,
        "count": len(rich_data),
        "data": rich_data,
        "fields": "title,time,related_stocks,category,url",
    }

    STOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    logger.info(f"[JSON] 保存到 {filepath} ({len(rich_data)} 条)")
    return str(filepath)


# ============================================================================
#  摘要生成与飞书推送
# ============================================================================

def _is_important(news_item: dict) -> bool:
    """判断新闻是否重要 (含【】标记、或特定关键词)。"""
    title = news_item.get("title", "")
    if title.startswith("【"):
        return True
    keywords = ["涨停", "跌停", "突发", "紧急", "重大", "刷新", "突破", "警告"]
    for kw in keywords:
        if kw in title:
            return True
    return False


# A股相关性过滤 — 盘中快讯只展示对A股交易有参考价值的消息
_A_SHARE_POSITIVE_KEYWORDS = [
    # A股市场
    "A股", "沪深", "上证", "深证", "创业板", "科创板", "北交所",
    "沪指", "深成指", "创业板指",
    # 监管/政策
    "证监会", "交易所", "发改委", "央行", "国务院", "工信部", "商务部",
    "财政部", "银保监会", "金融监管", "政策性", "国家大基金",
    "十五五", "中医药", "国产",
    # 市场信号
    "涨停", "跌停", "连板", "炸板", "封板", "开板", "地天板",
    "北向资金", "南向资金", "主力资金", "净流入", "净流出",
    "龙虎榜", "机构买入", "游资",
    "停牌", "复牌", "异动", "公告",
    "成交额", "放量", "缩量", "万亿",
    # A股概念板块（常见前缀）
    "概念", "板块", "题材",
    # A股常见市场动作
    "涨超", "跌超", "涨近", "持续活跃", "持续走高",
    "震荡回升", "午后拉升", "午后异动", "盘中拉升",
    # A股大市值标的
    "中芯国际", "华虹", "宁德时代", "贵州茅台", "比亚迪",
    # 泛A股行业/题材
    "国产替代", "自主可控", "新质生产力", "数字经济", "人工智能",
    "阿里云", "华为云", "腾讯云", "大模型", "AI",
    # 制造业细分（大量A股标的）
    "机床", "数控", "五轴", "机器人", "智能制造",
    # 中特估/央企
    "央企", "国企改革", "中字头",
    # 持仓相关行业 — 半导体/芯片/封测/基建/房地产/氢能源/电商/消费电子
    "半导体", "芯片", "封测", "集成电路", "光刻",
    "房地产", "基建", "建筑工程",
    "氢能源", "氢能", "储能", "锂电池",
    "汽车零部件", "新能源汽车",
    "消费电子", "射频", "天线",
    "电商", "数字营销", "鸿蒙", "金融科技",
    "气体储运", "装备",
    # 市场活动
    "机构调研", "机构预测", "研报", "券商", "分析师",
]

_A_SHARE_HOLDING_NAMES = [
    "山子高科", "宁波建工", "通富微电", "合肥城建",
    "京城股份", "壹网壹创", "润和软件", "信维通信",
    "000981", "601789", "002156", "002208",
    "600860", "300792", "300339", "300136",
]

# 明确非A股信号 — 仅提及外股/外企/外市的新闻
_A_SHARE_NEGATIVE_PATTERNS = [
    # 仅外市、外企、外债，无A股关联
    "日本30年期国债", "日本国债", "韩国总统府", "韩国副", "韩国外交", "印尼股市",
    "欧盟冯德莱恩", "冯德莱恩",
    "杰富瑞将", "杰富瑞",
    "英特尔陈立武", "英特尔CEO",
    "巴斯夫", "丰田",
    "首艘韩国", "霍尔木兹", "超级油轮",
    "三星电子", "SK海力士", "台积电.*美股",
]


def is_a_share_relevant(title: str) -> bool:
    """
    判断一条新闻标题是否对A股交易有参考价值。
    规则：命中负面模式 → 排除（外企/外市新闻即使含泛AI等词也无A股交易价值）
          命中正面词表 或 关联持仓代码 → 保留
          【】开头的通常已是财经精选 → 保留
    """
    # 【】开头的通常是财经精选，直接保留
    if title.startswith("【"):
        return True

    # 负面模式先行 — 外企/外市/外债等，明确非A股信号
    for p in _A_SHARE_NEGATIVE_PATTERNS:
        if p in title:
            return False

    # 持仓股代码/名称直接保留
    for name in _A_SHARE_HOLDING_NAMES:
        if name in title:
            return True

    # 正面关键词 → 保留
    for kw in _A_SHARE_POSITIVE_KEYWORDS:
        if kw in title:
            return True

    return False


def _format_brief_time(pub_time: str) -> str:
    """从完整时间戳提取简短的 HH:MM 时间。"""
    if len(pub_time) >= 16:
        return pub_time[11:16]
    return pub_time or "--:--"


def _truncate_title(title: str, max_len: int = 100) -> str:
    """截断过长标题。"""
    if len(title) <= max_len:
        return title
    return title[:max_len - 3] + "..."


def generate_markdown_summary(news_items: list[dict], mode: str) -> str:
    """生成 Markdown 格式的新闻摘要，用于飞书推送。"""
    now = now_cst()
    mode_label = {"morning": "盘前早报", "intraday": "盘中快讯", "evening": "盘后晚报"}.get(mode, "新闻快讯")

    # A股相关性过滤
    total_before = len(news_items)
    news_items = [n for n in news_items if is_a_share_relevant(n.get("title", ""))]
    filtered = total_before - len(news_items)

    lines = [
        f"**采集时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}",
        f"**模式**: {mode_label}",
        f"**市场状态**: {'交易中' if is_market_open() else '休市'}",
        f"**新闻数量**: {len(news_items)} 条" + (f" (已过滤 {filtered} 条无关快讯)" if filtered else ""),
        "",
        "---",
        "",
    ]

    # 分类: 重要新闻 vs 一般新闻
    important = [n for n in news_items if _is_important(n)]
    regular = [n for n in news_items if not _is_important(n)]

    if important:
        lines.append("**重要新闻**:")
        lines.append("")
        for item in important[:20]:  # 最多20条重要新闻
            t = _format_brief_time(item.get("pub_time", ""))
            title = _truncate_title(item.get("title", ""))
            lines.append(f"- [{t}] {title}")
        lines.append("")

    if regular:
        lines.append("**其他快讯**:")
        lines.append("")
        # 普通新闻最多显示15条
        for item in regular[:15]:
            t = _format_brief_time(item.get("pub_time", ""))
            title = _truncate_title(item.get("title", ""))
            lines.append(f"- [{t}] {title}")

        remaining = len(regular) - 15
        if remaining > 0:
            lines.append(f"  *...还有 {remaining} 条新闻，完整数据已保存至数据库*")
        lines.append("")

    lines.append("---")
    lines.append(f"数据来源: 财联社 (cls.cn) | 自动采集于 {now.strftime('%Y-%m-%d %H:%M')}")

    return "\n".join(lines)


def send_summary_via_feishu(news_items: list[dict], mode: str, chat_id: str = "") -> bool:
    """通过飞书推送新闻摘要。可指定群聊（路由名或原始 chat_id）。"""
    target = FEISHU_ROUTES.get(chat_id) or chat_id or FEISHU_BOT_CHAT_ID
    if not target:
        logger.info("[飞书] 目标群未配置，跳过推送")
        return False

    if send_feishu_message is None:
        logger.warning("[飞书] feishu_sender 模块不可用，跳过推送")
        return False

    mode_label = {"morning": "盘前早报", "intraday": "盘中快讯", "evening": "盘后晚报"}.get(mode, mode)
    title = f"财经快讯 - {mode_label} - {now_cst().strftime('%m/%d %H:%M')}"
    content = generate_markdown_summary(news_items, mode)

    try:
        ok = send_feishu_message(title=title, content=content, chat_id=target)
        if ok:
            logger.info(f"[飞书] {mode_label} 推送成功 ({len(news_items)} 条)")
        else:
            logger.error(f"[飞书] {mode_label} 推送失败")
        return ok
    except Exception as e:
        logger.error(f"[飞书] 推送异常: {e}")
        traceback.print_exc()
        return False


# ============================================================================
#  模式执行
# ============================================================================

def run_morning() -> bool:
    """
    早间模式: 采集盘前新闻摘要。
    - 多源采集 (财联社 + 新浪财经 + 东方财富)
    - 去重后保存 JSON 和数据库
    - 生成 Markdown 摘要并推送飞书
    """
    logger.info("=" * 60)
    logger.info("[morning] 开始执行盘前新闻采集")
    start_ts = time.time()

    try:
        # 1. 多源采集
        all_items, sources = collect_from_all_sources()
        if not all_items:
            logger.warning("[morning] 所有数据源均未返回数据")
            return False

        logger.info(f"[morning] 多源采集: {len(all_items)} 条, 来源: {sources}")

        # 2. 去重
        existing_titles = get_existing_titles(hours=DEDUP_WINDOW_HOURS)
        unique_news = deduplicate_news(all_items, existing_titles)

        if not unique_news:
            logger.info("[morning] 无新新闻 (全部已存在)")
            return True

        # 3. 保存 JSON
        save_news_json(unique_news, "morning")

        # 4. 存入数据库
        try:
            save_news(unique_news)
            logger.info(f"[morning] 保存 {len(unique_news)} 条到数据库")
        except Exception as e:
            logger.error(f"[morning] 数据库保存失败: {e}")
            traceback.print_exc()

        # 5. 飞书推送摘要
        send_summary_via_feishu(unique_news, "morning", sources, chat_id="news")

        elapsed = time.time() - start_ts
        logger.info(f"[morning] 执行完成，耗时 {elapsed:.1f}s, 采集 {len(unique_news)} 条")
        return True

    except Exception as e:
        logger.error(f"[morning] 执行失败: {e}")
        traceback.print_exc()
        return False


# 盘中推送时间门控（避免每30分钟轰炸）
_INTRADAY_PUSH_INTERVAL = 7200  # 2小时
_INTRADAY_PUSH_FILE = PROJECT_DIR / "data" / "intraday_push_stamp"


def _intraday_should_push() -> bool:
    """检查距上次盘中推送是否超过间隔，未超时则不推送"""
    if not _INTRADAY_PUSH_FILE.exists():
        return True
    try:
        last = float(_INTRADAY_PUSH_FILE.read_text(encoding="utf-8").strip())
        return (time.time() - last) >= _INTRADAY_PUSH_INTERVAL
    except Exception:
        return True


def _intraday_mark_pushed():
    _INTRADAY_PUSH_FILE.parent.mkdir(parents=True, exist_ok=True)
    _INTRADAY_PUSH_FILE.write_text(str(time.time()), encoding="utf-8")


def run_intraday() -> bool:
    """
    盘中模式: 采集实时快讯。
    - 检查市场是否开盘，休市则跳过
    - 拉取最新 50 条电报
    - 去重后保存 JSON 和数据库
    - 每2小时推送一次飞书 (盘中频率高，避免消息轰炸)
    """
    logger.info("=" * 60)
    logger.info("[intraday] 开始执行盘中快讯采集")

    # 检查市场状态
    if not is_market_open():
        logger.info("[intraday] 当前非交易时间，跳过采集")
        return True

    start_ts = time.time()

    try:
        # 1. 拉取数据
        raw_items = fetch_cls_telegraph(rn=CLS_API_RN, pn=0)
        if not raw_items:
            logger.warning("[intraday] CLS API 未返回数据")
            return False

        # 2. 转换格式
        transformed = transform_news(raw_items)
        logger.debug(f"[intraday] 转换 {len(transformed)} 条新闻")

        # 3. 去重 (盘中只检查最近2小时，避免漏过不同时段的相同标题)
        existing_titles = get_existing_titles(hours=2)
        unique_news = deduplicate_news(transformed, existing_titles)

        if not unique_news:
            logger.info("[intraday] 无新新闻")
            return True

        # 4. 保存 JSON
        save_news_json(unique_news, "intraday")

        # 5. 存入数据库
        try:
            save_news(unique_news)
            logger.info(f"[intraday] 保存 {len(unique_news)} 条到数据库")
        except Exception as e:
            logger.error(f"[intraday] 数据库保存失败: {e}")
            traceback.print_exc()

        # 6. 飞书推送（每2小时推送一次汇总）
        if _intraday_should_push():
            send_summary_via_feishu(unique_news, "intraday", chat_id="news")
            _intraday_mark_pushed()
        else:
            logger.info("[intraday] 距上次推送不足2小时，跳过飞书推送")

        elapsed = time.time() - start_ts
        logger.info(f"[intraday] 执行完成，耗时 {elapsed:.1f}s, 新增 {len(unique_news)} 条")
        return True

    except Exception as e:
        logger.error(f"[intraday] 执行失败: {e}")
        traceback.print_exc()
        return False


def run_evening() -> bool:
    """
    晚间模式: 采集盘后/晚间新闻摘要。
    - 拉取 cls.cn 最新 50 条电报
    - 去重后保存 JSON 和数据库
    - 生成 Markdown 摘要并推送飞书
    """
    logger.info("=" * 60)
    logger.info("[evening] 开始执行晚间新闻采集")
    start_ts = time.time()

    try:
        # 1. 拉取数据
        raw_items = fetch_cls_telegraph(rn=CLS_API_RN, pn=0)
        if not raw_items:
            logger.warning("[evening] CLS API 未返回数据")
            return False

        # 2. 转换格式
        transformed = transform_news(raw_items)
        logger.info(f"[evening] 转换 {len(transformed)} 条新闻")

        # 3. 去重
        existing_titles = get_existing_titles(hours=DEDUP_WINDOW_HOURS)
        unique_news = deduplicate_news(transformed, existing_titles)

        if not unique_news:
            logger.info("[evening] 无新新闻 (全部已存在)")
            return True

        # 4. 保存 JSON
        save_news_json(unique_news, "evening")

        # 5. 存入数据库
        try:
            save_news(unique_news)
            logger.info(f"[evening] 保存 {len(unique_news)} 条到数据库")
        except Exception as e:
            logger.error(f"[evening] 数据库保存失败: {e}")
            traceback.print_exc()

        # 6. 飞书推送摘要
        send_summary_via_feishu(unique_news, "evening", chat_id="news")

        elapsed = time.time() - start_ts
        logger.info(f"[evening] 执行完成，耗时 {elapsed:.1f}s, 采集 {len(unique_news)} 条")
        return True

    except Exception as e:
        logger.error(f"[evening] 执行失败: {e}")
        traceback.print_exc()
        return False


# ============================================================================
#  主入口
# ============================================================================

def main(mode: str = "auto") -> int:
    """
    主调度函数。

    Args:
        mode: 执行模式 (morning / intraday / evening / auto)

    Returns:
        int: 0 成功, 1 失败
    """
    # 将 stderr 重定向到日志文件，定时任务直接跑 Python 时 crash traceback 不会丢失
    _log_dir = STOCK_DATA_DIR / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _log_file = _log_dir / f"news_{mode}.log"
    _orig_stderr = sys.stderr
    try:
        import io
        _log_fh = open(_log_file, "a", encoding="utf-8")
        _stderr_buf = io.TextIOWrapper(_log_fh.buffer, encoding="utf-8", line_buffering=True)
        class _TeeStderr:
            def write(self, text):
                _orig_stderr.write(text)
                _stderr_buf.write(text)
            def flush(self):
                _orig_stderr.flush()
                _stderr_buf.flush()
        sys.stderr = _TeeStderr()
    except Exception:
        pass

    logger.info(f"News Scheduler 启动 | 模式: {mode} | 时间: {timestamp_str()}")

    # auto 模式: 自动判断
    if mode == "auto":
        mode = deduce_auto_mode()

    # 硬守卫: intraday 模式拒绝在非交易时段执行 (8:00-18:00 以外直接拒绝)
    if mode == "intraday":
        hour = now_cst().hour
        if hour < 8 or hour > 18:
            logger.warning(f"[intraday] 拒绝在非交易时段执行 (当前 {hour}:00, 允许 8:00-18:00)")
            sys.stderr = _orig_stderr
            return 0

    # 路由到对应处理器
    handlers = {
        "morning": run_morning,
        "intraday": run_intraday,
        "evening": run_evening,
    }

    handler = handlers.get(mode)
    if handler is None:
        logger.error(f"未知模式: {mode}，支持: morning / intraday / evening / auto")
        sys.stderr = _orig_stderr
        return 1

    try:
        success = handler()
        sys.stderr = _orig_stderr
        return 0 if success else 1
    except Exception as e:
        logger.error(f"模式 {mode} 执行崩溃: {e}")
        traceback.print_exc()
        sys.stderr = _orig_stderr
        return 1


if __name__ == "__main__":
    # 解析命令行参数
    if len(sys.argv) > 1:
        mode_arg = sys.argv[1].strip().lower()
    else:
        mode_arg = "auto"

    exit_code = main(mode_arg)
    sys.exit(exit_code)
