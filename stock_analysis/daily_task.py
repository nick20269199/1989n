#!/usr/bin/env python3
"""
每日股票分析任务编排器 (Daily Task Orchestrator)

由 .bat 文件以 mode 参数调用，统一协调各个子模块执行:
  morning_enhanced  (09:00) — 盘前增强简报
  closing_review    (15:15) — 收盘复盘
  intraday_analysis (11:30 / 15:00) — 30分钟快照
  hot_stocks        (09:15, 每小时重复) — 热门股票采集
  evening           (22:00) — 晚间总结
  overnight         (23:30) — 隔夜分析
  tech_scan         (15:30) — 技术形态扫描
"""

from error_capture import trap; trap()

import json
import logging
import os
import sys
import time
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Optional

import requests
import akshare as ak

from config import (
    STOCK_DATA_DIR,
    PORTFOLIO_FILE,
    FEISHU_WEBHOOK_URL,
    FEISHU_ROUTES,
    HEADERS,
    EASTMONEY_QUOTE_URL,
    TENCENT_KLINE_URL,
    THS_HOT_STOCKS_URL,
    SINA_QUOTE_URL,
)

# ── 多源数据路由 (自动健康检查 + 回退) ──
from data_source_router import get_quotes as router_get_quotes
from data_source_router import get_index_quotes as router_get_index_quotes
from data_source_router import get_us_index_quotes, check_channels, EASTMONEY_BLOCKED, safe_akshare_call
from data_quality_gate import preflight_scan, freshness_check, require_fresh
from dept_status_protocol import publish_status
from vv_insights import load_vv_insights, format_vv_for_feishu

# 启动时检测通道健康状态
_channels_ok = check_channels()
logger = logging.getLogger("daily_task")
logger.info("数据通道状态: %s", {k: "✅" if v else "❌" for k, v in _channels_ok.items()})

# ── 可选依赖（尚在开发中的模块使用 fallback） ──────────────────────────

try:
    from database import get_portfolio as db_get_portfolio
    from database import save_market_data, save_hot_stocks as db_save_hot_stocks
    from database import get_market_history
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

    def db_get_portfolio() -> list[dict]:
        return []

    def save_market_data(data: list[dict]) -> None:
        pass

    def db_save_hot_stocks(stocks: list[dict]) -> None:
        pass

    def get_market_history(code: str, days: int = 60) -> list[dict]:
        return []


try:
    from feishu_sender import send_feishu_message
    _FEISHU_AVAILABLE = True
except ImportError:

    def send_feishu_message(title: str, content: str, chat_id: str = "") -> bool:
        """Fallback: webhook 发送飞书卡片（chat_id 参数接收但忽略，webhook 去固定群）"""
        if not FEISHU_WEBHOOK_URL:
            logger.warning("FEISHU_WEBHOOK_URL 未配置，跳过飞书发送")
            return False
        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": title},
                    "template": "blue",
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": content}}
                ],
            },
        }
        try:
            r = requests.post(FEISHU_WEBHOOK_URL, json=payload, timeout=15)
            return r.status_code == 200
        except Exception:
            return False


try:
    from stock_skill import scan_vcp, scan_watchlist_tech, analyze_holdings
    _SKILL_AVAILABLE = True
except ImportError:
    _SKILL_AVAILABLE = False

    def scan_vcp(codes: list) -> dict:
        return {"scan_type": "vcp", "results": [], "count": 0}

    def scan_watchlist_tech(codes: list) -> dict:
        return {"scan_type": "watchlist_tech", "results": [], "count": 0}

    def analyze_holdings(codes: list) -> dict:
        return {"holdings": [], "total": 0}


try:
    from position_manager import PositionManager, HOLDINGS as PM_HOLDINGS
    _POSITION_MGR_AVAILABLE = True
except ImportError:
    _POSITION_MGR_AVAILABLE = False
    PositionManager = None
    PM_HOLDINGS = []


# ── 日志 ─────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily_task")

# ── 常量 ─────────────────────────────────────────────────────────

MARKET_OPEN_MORNING = dt_time(9, 30)
MARKET_CLOSE_MORNING = dt_time(11, 30)
MARKET_OPEN_AFTERNOON = dt_time(13, 0)
MARKET_CLOSE_AFTERNOON = dt_time(15, 0)

# 默认止损比例 5%
DEFAULT_STOP_LOSS_PCT = 0.05

# ── 工具函数 ─────────────────────────────────────────────────────


def ensure_data_dir() -> Path:
    """确保数据目录存在"""
    STOCK_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return STOCK_DATA_DIR


# 去重哨兵目录
_SENTINEL_DIR = STOCK_DATA_DIR / ".sentinel"


def _already_ran_today(key: str) -> bool:
    """检查哨兵文件是否存在（同日同任务只跑一次）。"""
    _SENTINEL_DIR.mkdir(parents=True, exist_ok=True)
    sentinel = _SENTINEL_DIR / f"{key}.lock"
    if sentinel.exists():
        return True
    sentinel.write_text(datetime.now().isoformat())
    return False


def is_trading_day(dt: Optional[datetime] = None) -> bool:
    """判断是否为交易日（A股：周一至周五，排除节假日近似）"""
    if dt is None:
        dt = datetime.now()
    return dt.weekday() < 5


def is_market_hours(dt: Optional[datetime] = None) -> bool:
    """判断当前是否处于A股交易时段"""
    if dt is None:
        dt = datetime.now()
    if not is_trading_day(dt):
        return False
    t = dt.time()
    return (MARKET_OPEN_MORNING <= t <= MARKET_CLOSE_MORNING) or (
        MARKET_OPEN_AFTERNOON <= t <= MARKET_CLOSE_AFTERNOON
    )


def is_pre_market(dt: Optional[datetime] = None) -> bool:
    """判断当前是否为盘前（交易日 9:30 之前）"""
    if dt is None:
        dt = datetime.now()
    if not is_trading_day(dt):
        return False
    return dt.time() < MARKET_OPEN_MORNING


def timestamp_now() -> str:
    """返回当前时间字符串 YYYY-MM-DD HH:MM:SS"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def date_today() -> str:
    """返回当前日期字符串 YYYY-MM-DD"""
    return datetime.now().strftime("%Y-%m-%d")


def date_now_compact() -> str:
    """返回紧凑时间戳 YYYYMMDD_HHMM"""
    return datetime.now().strftime("%Y%m%d_%H%M")


def safe_request(url: str, params: dict = None, timeout: int = 15, retries: int = 2) -> Optional[requests.Response]:
    """带重试的 HTTP GET 请求"""
    for attempt in range(retries + 1):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt < retries:
                logger.warning(f"请求失败 (第{attempt+1}次): {url[:80]} — {e}")
                time.sleep(1 * (attempt + 1))
            else:
                logger.error(f"请求最终失败: {url[:80]} — {e}")
                return None


# ── 持仓加载 ─────────────────────────────────────────────────────


def load_portfolio() -> list[dict]:
    """加载持仓数据: 优先从 PORTFOLIO_FILE 读取，其次数据库"""
    holdings = []

    # 1) 尝试 JSON 文件
    if PORTFOLIO_FILE.exists():
        try:
            data = json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                holdings = data
            elif isinstance(data, dict):
                holdings = data.get("holdings", data.get("data", []))
                if not holdings and "code" in data:
                    holdings = [data]
            if holdings:
                logger.info(f"从 {PORTFOLIO_FILE} 加载 {len(holdings)} 条持仓")
                return _normalize_holdings(holdings)
        except Exception as e:
            logger.warning(f"读取 {PORTFOLIO_FILE} 失败: {e}")

    # 2) 尝试数据库
    if _DB_AVAILABLE:
        try:
            rows = db_get_portfolio()
            if rows:
                mapped = []
                for r in rows:
                    mapped.append({
                        "code": r.get("stock_code", ""),
                        "shares": r.get("shares", 0),
                        "cost": r.get("cost", 0.0),
                        "sector": r.get("sector", ""),
                    })
                holdings = mapped
                logger.info(f"从数据库加载 {len(holdings)} 条持仓")
                return _normalize_holdings(holdings)
        except Exception as e:
            logger.warning(f"数据库读取持仓失败: {e}")

    logger.warning("未找到持仓数据，使用硬编码后备数据")
    return _fallback_holdings()


def _normalize_holdings(raw: list[dict]) -> list[dict]:
    """统一持仓字段名"""
    out = []
    for h in raw:
        out.append({
            "code": str(h.get("code", h.get("stock_code", ""))).zfill(6),
            "name": str(h.get("name", h.get("stock_name", ""))),
            "shares": int(h.get("shares", 0)),
            "cost": float(h.get("cost", 0.0)),
            "sector": str(h.get("sector", "")),
            "first_buy": str(h.get("first_buy", "")),
            "latest_buy": str(h.get("latest_buy", "")),
        })
    return [h for h in out if h["code"] and h["shares"] > 0]


def _fallback_holdings() -> list[dict]:
    """硬编码后备持仓（与 portfolio.json 一致的应急备份）"""
    return [
        {"code": "002156", "name": "通富微电", "shares": 100, "cost": 51.679, "sector": "半导体封测", "first_buy": "2026-04-27", "latest_buy": "2026-05-15"},
        {"code": "300136", "name": "信维通信", "shares": 300, "cost": 111.145, "sector": "消费电子/射频", "first_buy": "2026-05-18", "latest_buy": "2026-05-22"},
        {"code": "600498", "name": "烽火通信", "shares": 800, "cost": 57.132, "sector": "通信设备", "first_buy": "2026-05-20", "latest_buy": "2026-05-22"},
        {"code": "002077", "name": "大港股份", "shares": 1700, "cost": 18.684, "sector": "半导体/EDA", "first_buy": "2026-05-21", "latest_buy": "2026-05-21"},
        {"code": "300058", "name": "蓝色光标", "shares": 800, "cost": 18.240, "sector": "AI营销/出海", "first_buy": "2026-05-21", "latest_buy": "2026-05-21"},
        {"code": "002050", "name": "三花智控", "shares": 300, "cost": 53.830, "sector": "", "first_buy": "2026-05-25", "latest_buy": "2026-05-25"},
        {"code": "600183", "name": "生益科技", "shares": 400, "cost": 114.145, "sector": "", "first_buy": "2026-05-25", "latest_buy": "2026-05-25"},
    ]

def _market_prefix(code: str) -> str:
    """根据代码返回交易所前缀: sz 或 sh"""
    if code.startswith(("0", "3")):
        return "sz"
    return "sh"


def fetch_quote_tencent(code: str) -> Optional[dict]:
    """通过腾讯接口获取个股实时行情"""
    prefix = _market_prefix(code)
    full_code = f"{prefix}{code}"
    try:
        url = f"{TENCENT_KLINE_URL}?param={full_code},day,,,1"
        r = safe_request(url, timeout=10)
        if r is None:
            return None
        data = r.json()
        if data.get("code") != 0:
            return None
        day_list = data.get("data", {}).get(full_code, {}).get("day", [])
        if not day_list:
            return None
        latest = day_list[-1]
        # 腾讯K线格式: [date, open, close, high, low, volume]
        if len(latest) >= 6:
            return {
                "code": code,
                "price": float(latest[2]),
                "open": float(latest[1]),
                "high": float(latest[3]),
                "low": float(latest[4]),
                "volume": float(latest[5]),
                "source": "tencent",
            }
    except Exception as e:
        logger.warning(f"腾讯行情 {code} 失败: {e}")
    return None


def fetch_quote_sina(codes: list[str]) -> list[dict]:
    """通过新浪接口批量获取行情（备选）"""
    if not codes:
        return []
    results = []
    code_str = ",".join(f"{_market_prefix(c)}{c}" for c in codes)
    sina_headers = {**HEADERS, "Referer": "https://finance.sina.com.cn/"}
    try:
        r = requests.get(
            f"{SINA_QUOTE_URL}{code_str}",
            headers=sina_headers,
            timeout=10,
        )
        if r is None or not r.text or r.status_code != 200:
            return []
        # 新浪返回 GBK 编码，逐行解析
        r.encoding = "gbk"
        lines = r.text.strip().split("\n")
        for line in lines:
            if "=" not in line:
                continue
            try:
                var_name, raw = line.split("=", 1)
                raw = raw.strip('" ;')
                parts = raw.split(",")
                if len(parts) < 4:
                    continue
                code = var_name.split("_")[-1]
                name = parts[0]
                price = float(parts[3]) if parts[3] else 0.0
                prev_close = float(parts[2]) if parts[2] else price
                change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
                results.append({
                    "code": code,
                    "name": name,
                    "price": price,
                    "change_pct": round(change_pct, 2),
                    "high": float(parts[4]) if len(parts) > 4 and parts[4] else price,
                    "low": float(parts[5]) if len(parts) > 5 and parts[5] else price,
                    "volume": float(parts[8]) if len(parts) > 8 and parts[8] else 0.0,
                    "source": "sina",
                })
            except (ValueError, IndexError):
                continue
    except Exception as e:
        logger.warning(f"新浪行情批量获取失败: {e}")
    return results


def fetch_quote_eastmoney(code: str) -> Optional[dict]:
    """通过东方财富接口获取个股/指数行情"""
    # 如果 code 已含 "." 则视为完整 secid (如 1.000001, 0.399001)
    if "." in code:
        secid = code
    else:
        prefix = "0" if code.startswith(("0", "3")) else "1"
        secid = f"{prefix}.{code}"
    try:
        params = {
            "ut": "fa5fd1943c7b386f172d6893dbf38dc7",
            "secid": secid,
            "fields": "f43,f44,f45,f46,f47,f48,f50,f51,f52,f57,f58,f60,f116,f117,f162,f167,f168,f169,f170,f171",
            "forcect": 1,
        }
        r = safe_request(EASTMONEY_QUOTE_URL, params=params, timeout=10)
        if r is None:
            return None
        data = r.json()
        if not data.get("data"):
            return None
        d = data["data"]
        price = d.get("f43", 0) / 100 if d.get("f43") else 0.0
        prev_close = d.get("f60", price * 100) / 100 if d.get("f60") else price
        change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0.0
        return {
            "code": code,
            "name": d.get("f57", ""),
            "price": price,
            "change_pct": round(change_pct, 2),
            "high": d.get("f44", 0) / 100 if d.get("f44") else 0.0,
            "low": d.get("f45", 0) / 100 if d.get("f45") else 0.0,
            "volume": d.get("f47", 0),
            "amount": d.get("f48", 0),
            "turnover_rate": d.get("f168", 0) / 100 if d.get("f168") else 0.0,
            "pe": d.get("f162", 0) / 100 if d.get("f162") else 0.0,
            "source": "eastmoney",
        }
    except Exception as e:
        logger.warning(f"东方财富行情 {code} 失败: {e}")
    return None


def fetch_quote(code: str) -> Optional[dict]:
    """获取个股行情: 数据源路由器 → 遗留接口回退"""
    # 1) 路由器
    result = router_get_quotes([code]).get(code)
    if result and result.get("current", 0) > 0:
        return {
            "code": code,
            "name": result.get("name", ""),
            "price": result["current"],
            "change_pct": result.get("change_pct", 0),
            "high": result.get("high", 0),
            "low": result.get("low", 0),
            "volume": result.get("volume", 0),
            "source": result.get("source", "router"),
        }

    # 2) 遗留: 东方财富 (如果已恢复)
    if not EASTMONEY_BLOCKED:
        result = fetch_quote_eastmoney(code)
        if result and result.get("price", 0) > 0:
            return result

    # 3) 腾讯单只
    result = fetch_quote_tencent(code)
    if result and result.get("price", 0) > 0:
        return result

    logger.error("所有行情源均无法获取 %s", code)
    return None


def fetch_quotes_ulist_batch(codes: list[str]) -> dict[str, dict]:
    """通过东方财富 ulist 批量接口获取行情（最稳定，一次拿所有）"""
    if not codes:
        return {}
    secids = []
    for c in codes:
        prefix = "0" if c.startswith(("0", "3")) else "1"
        secids.append(f"{prefix}.{c}")
    try:
        params = {
            "fltt": 2, "invt": 2,
            "fields": "f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18",
            "secids": ",".join(secids),
        }
        r = safe_request(
            "https://push2.eastmoney.com/api/qt/ulist.np/get",
            params=params, timeout=10, retries=3,
        )
        if r is None:
            return {}
        data = r.json()
        results: dict[str, dict] = {}
        for item in data.get("data", {}).get("diff", []):
            code = item.get("f12", "")
            price = item.get("f2", 0)
            if not price or price <= 0:
                continue
            prev_close = item.get("f18", price)
            change_pct = item.get("f3", 0)
            results[code] = {
                "code": code,
                "name": item.get("f14", ""),
                "price": price,
                "change_pct": round(change_pct, 2),
                "high": item.get("f15", price),
                "low": item.get("f16", price),
                "open": item.get("f17", price),
                "prev_close": prev_close,
                "volume": item.get("f5", 0),
                "amount": item.get("f6", 0),
                "source": "eastmoney_ulist",
            }
        logger.info(f"ulist批量行情: 获取 {len(results)}/{len(codes)} 只")
        return results
    except Exception as e:
        logger.warning(f"ulist批量行情失败: {e}")
    return {}


def fetch_quotes_batch(codes: list[str]) -> dict[str, dict]:
    """批量获取行情: 数据源路由器(新浪主→腾讯备), 东方财富WAF封锁中则跳过。"""
    results: dict[str, dict] = {}

    # 1) 路由器统一获取 (新浪 → 腾讯回退)
    router_data = router_get_quotes(codes)
    for code, q in router_data.items():
        if q.get("current", 0) > 0:
            results[code] = {
                "code": code,
                "name": q.get("name", ""),
                "price": q["current"],
                "change_pct": q.get("change_pct", 0),
                "high": q.get("high", 0),
                "low": q.get("low", 0),
                "open": q.get("open", 0),
                "prev_close": q.get("prev_close", 0),
                "volume": q.get("volume", 0),
                "amount": q.get("amount", 0),
                "source": q.get("source", "router"),
            }

    remaining = [c for c in codes if c not in results]
    if remaining:
        logger.info("路由器剩余 %d 只, 尝试遗留接口...", len(remaining))
        # 2) 遗留: 东方财富单只 (如果已恢复)
        if not EASTMONEY_BLOCKED:
            for code in remaining:
                q = fetch_quote_eastmoney(code)
                if q and q.get("price", 0) > 0:
                    results[code] = q
        # 3) 再试腾讯单只 (不同路径)
        still_missing = [c for c in remaining if c not in results]
        for code in still_missing:
            q = fetch_quote_tencent(code)
            if q and q.get("price", 0) > 0:
                results[code] = q

    missing = [c for c in codes if c not in results]
    if missing:
        logger.warning("⚠ 以下股票所有行情源均失败: %s", missing)

    return results


def fetch_index_quote(index_code: str, index_name: str) -> Optional[dict]:
    """获取指数行情 (路由器 → 遗留回退)"""
    # 路由器一次性获取所有指数
    indices = router_get_index_quotes()
    for idx in indices:
        if idx["name"] == index_name:
            return {"code": index_code, "name": index_name, "price": idx["price"], "change_pct": idx["change_pct"]}

    # 遗留: 东方财富 (如果已恢复)
    if not EASTMONEY_BLOCKED:
        q = fetch_quote_eastmoney(index_code)
        if q:
            q["name"] = index_name
            return q
    return None


# ── 全球市场 ─────────────────────────────────────────────────────


GLOBAL_INDICES = [
    ("1.000001", "上证指数"),
    ("0.399001", "深证成指"),
    ("0.399006", "创业板指"),
    ("1.000688", "科创50"),
]

US_INDICES = [
    ("100.DJIA", "道琼斯"),
    ("100.NDX", "纳斯达克"),
    ("100.SPX", "标普500"),
]


def fetch_global_markets() -> dict:
    """获取全球主要指数和商品数据 (路由器 → akshare → 遗留回退)"""
    result: dict = {"indices": [], "commodities": [], "forex": []}

    # A股指数 (路由器: 新浪主→腾讯备)
    a_indices = router_get_index_quotes()
    for idx in a_indices:
        result["indices"].append({
            "name": idx["name"],
            "price": idx["price"],
            "change_pct": idx["change_pct"],
        })

    # 美股指数 (akshare)
    us_indices = get_us_index_quotes()
    for idx in us_indices:
        result["indices"].append({
            "name": idx["name"],
            "price": idx["price"],
            "change_pct": idx["change_pct"],
        })

    # 遗留: 东方财富美股 (如果akshare失败且东方财富已恢复)
    if not EASTMONEY_BLOCKED:
        existing_names = {idx["name"] for idx in result["indices"]}
        for code, name in US_INDICES:
            if name in existing_names:
                continue
            q = fetch_quote_eastmoney(code)
            if q:
                result["indices"].append({
                    "name": name,
                    "price": q.get("price", 0),
                    "change_pct": q.get("change_pct", 0),
                })

    return result


# ── 经济日历 ─────────────────────────────────────────────────────


ECONOMIC_CALENDAR = [
    {"date": "05/01", "event": "PMI (制造业/非制造业)", "importance": 5},
    {"date": "05/07", "event": "外汇储备", "importance": 5},
    {"date": "05/10", "event": "CPI / PPI", "importance": 5},
    {"date": "05/11", "event": "社会融资规模 / M2货币供应", "importance": 5},
    {"date": "05/15", "event": "工业增加值 / 固定资产投资 / 社消", "importance": 5},
    {"date": "05/17", "event": "70城房价", "importance": 3},
    {"date": "05/18", "event": "LPR报价", "importance": 3},
    {"date": "05/20", "event": "规模以上工业企业利润", "importance": 3},
]


def fetch_economic_calendar() -> dict:
    """获取近期经济日历事件"""
    now = datetime.now()
    today = now.strftime("%m/%d")
    monthly = []
    published = []

    for evt in ECONOMIC_CALENDAR:
        entry = {
            "date": evt["date"],
            "event": evt["event"],
            "status": "已发布" if evt["date"] < today else "待发布",
            "importance": "★" * evt["importance"],
        }
        if evt["date"] < today:
            published.append(entry)
        else:
            monthly.append(entry)

    return {"monthly_events": monthly, "recent_published": published}


# ── 新闻采集 ─────────────────────────────────────────────────────


def fetch_news_for_holdings(codes: list[str], limit: int = 20) -> list[dict]:
    """获取与持仓相关的新闻"""
    news_items = []
    code_set = set(codes)

    # 财联社电报接口 (nodeapi/telegraphList — 更稳定)
    try:
        cls_headers = {**HEADERS, "Referer": "https://www.cls.cn/telegraph"}
        r = requests.get(
            "https://www.cls.cn/nodeapi/telegraphList",
            params={"rn": 50, "pn": 0},
            headers=cls_headers,
            timeout=10,
        )
        if r and r.status_code == 200:
            data = r.json()
            raw_list = data.get("data", {}).get("roll_data", [])
            if isinstance(raw_list, list):
                for item in raw_list[:50]:
                    title = item.get("title", "")
                    content = item.get("content", "") or item.get("brief", "") or ""
                    combined = title + content
                    # 检查是否与持仓股票相关
                    related = []
                    for c in code_set:
                        if c in combined:
                            related.append(c)
                    if not related:
                        continue
                    news_items.append({
                        "title": title,
                        "time": item.get("ctime", ""),
                        "source": "财联社",
                        "related_stocks": ",".join(related),
                        "sentiment": "",
                        "category": item.get("subject", ""),
                    })
    except Exception as e:
        logger.warning(f"财联社新闻获取失败: {e}")

    # 沪/深交易所公告标题检索 (仅当东方财富可用时)
    if not EASTMONEY_BLOCKED:
        for code in code_set:
            try:
                prefix = _market_prefix(code)
                r = safe_request(
                    f"https://push2.eastmoney.com/api/qt/stock/get",
                    params={
                        "secid": f"{'0' if prefix == 'sz' else '1'}.{code}",
                        "fields": "f271,f272",
                        "ut": "fa5fd1943c7b386f172d6893dbf38dc7",
                    },
                    timeout=8,
                )
                if r:
                    d = r.json().get("data", {})
                    if d:
                        for field in ["f271", "f272"]:
                            txt = d.get(field, "")
                            if txt and len(txt) > 5:
                                news_items.append({
                                    "title": txt[:100],
                                    "time": timestamp_now(),
                                    "source": "东方财富",
                                    "related_stocks": code,
                                    "sentiment": "",
                                    "category": "公告",
                                })
            except Exception:
                continue

    # 按时间排序并截断
    news_items.sort(key=lambda x: x.get("time", ""), reverse=True)
    return news_items[:limit]


# ── 热门股票 ─────────────────────────────────────────────────────


def fetch_hot_stocks_10jqka() -> list[dict]:
    """从同花顺获取热门股票排行"""
    results = []
    # 尝试多个接口路径
    urls = [
        "https://www.10jqka.com.cn/api/hotstock",
        "https://eq.10jqka.com.cn/api/hotstock",
    ]
    for url in urls:
        try:
            r = safe_request(url, timeout=10)
            if r is None:
                continue
            data = r.json()
            items = data.get("data", data.get("list", []))
            if not isinstance(items, list):
                items = []
            for i, item in enumerate(items):
                results.append({
                    "code": str(item.get("code", "")).zfill(6),
                    "name": item.get("name", ""),
                    "price": float(item.get("price", item.get("latest", 0))),
                    "change_pct": float(item.get("change_pct", item.get("change", 0))),
                    "rank": i + 1,
                    "sources": ["同花顺"],
                    "volume": item.get("volume", 0),
                    "amount": item.get("amount", 0),
                    "turnover_rate": item.get("turnover_rate", 0),
                })
            if results:
                return results
        except Exception as e:
            logger.warning(f"同花顺热门股票 {url} 失败: {e}")
    return results


def fetch_hot_stocks_eastmoney() -> list[dict]:
    """从东方财富获取涨幅榜/成交额榜 (东方财富WAF封锁时跳过)"""
    if EASTMONEY_BLOCKED:
        return []
    results = []
    # 涨幅榜
    try:
        params = {
            "pn": 1, "pz": 30, "po": 1, "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2, "invt": 2,
            "fid": "f3",  # 按涨跌幅排序
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",  # A股
            "fields": "f2,f3,f4,f5,f6,f7,f8,f12,f14,f15,f16,f17,f18,f20",
        }
        r = safe_request("https://push2.eastmoney.com/api/qt/clist/get", params=params, timeout=10)
        if r:
            data = r.json()
            items = data.get("data", {}).get("diff", [])
            for i, item in enumerate(items[:20]):
                code = str(item.get("f12", "")).zfill(6)
                if code:
                    results.append({
                        "code": code,
                        "name": item.get("f14", ""),
                        "price": item.get("f2", 0),
                        "change_pct": item.get("f3", 0),
                        "rank": i + 1,
                        "sources": ["东方财富涨跌幅榜"],
                        "volume": item.get("f5", 0),
                        "amount": item.get("f6", 0),
                        "turnover_rate": item.get("f8", 0),
                        "pe": item.get("f9", 0),
                        "market_cap": item.get("f20", 0),
                    })
    except Exception as e:
        logger.warning(f"东方财富热门股票失败: {e}")
    return results


def fetch_hot_stocks_zt_pool() -> list[dict]:
    """从 akshare 涨停板池获取热门股票（替代已死的10jqka/东方财富）"""
    today = datetime.now().strftime("%Y%m%d")
    try:
        df = safe_akshare_call(ak.stock_zt_pool_em, date=today)
        if df is None or df.empty:
            logger.info("涨停板池: 无数据")
            return []
    except Exception as e:
        logger.warning(f"涨停板池接口失败: {e}")
        return []

    results = []
    for i, (_, row) in enumerate(df.iterrows()):
        results.append({
            "code": str(row.get("代码", "")),
            "name": str(row.get("名称", "")),
            "price": float(row.get("最新价", 0)),
            "change_pct": round(float(row.get("涨跌幅", 0)), 2),
            "amount": float(row.get("成交额", 0)),
            "market_cap": float(row.get("总市值", 0)),
            "turnover_rate": float(row.get("换手率", 0)),
            "rank": i + 1,
            "sources": ["涨停板池"],
        })
    logger.info(f"涨停板池: {len(results)} 只")
    return results


def collect_hot_stocks() -> list[dict]:
    """汇总多来源热门股票数据，去重并排序"""
    all_stocks = fetch_hot_stocks_10jqka() + fetch_hot_stocks_eastmoney() + fetch_hot_stocks_zt_pool()

    # 按code去重，合并来源
    merged: dict[str, dict] = {}
    for s in all_stocks:
        code = s["code"]
        if code in merged:
            merged[code]["sources"] = list(set(merged[code]["sources"] + s["sources"]))
            # 保留 rank 较小的
            if s.get("rank", 999) < merged[code].get("rank", 999):
                merged[code].update({k: v for k, v in s.items() if k != "sources"})
        else:
            merged[code] = dict(s)

    result = sorted(merged.values(), key=lambda x: x.get("rank", 999))[:50]
    logger.info(f"热门股票采集完成: {len(result)} 条 (来自 {len(all_stocks)} 原始记录)")
    return result


# ── 盈亏计算 ─────────────────────────────────────────────────────


def calculate_position_report(holdings: list[dict]) -> dict:
    """基于持仓和最新行情计算完整盈亏报告"""
    codes = [h["code"] for h in holdings]
    quotes = fetch_quotes_batch(codes)

    report_holdings = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        code = h["code"]
        q = quotes.get(code)
        if q is None or q.get("price", 0) <= 0:
            logger.warning(f"⚠ {code} 行情缺失，使用成本价计算（盈亏数据可能不准）")
            price = h.get("cost", 0)
            q = {}
        else:
            price = q.get("price", h.get("cost", 0))
        high = q.get("high", price)
        low = q.get("low", price)
        change_pct = q.get("change_pct", 0)
        volume = q.get("volume", 0)
        cost = h["cost"]
        shares = h["shares"]
        position_value = price * shares
        cost_basis = cost * shares
        pnl_amt = position_value - cost_basis
        pnl_pct = ((price - cost) / cost * 100) if cost > 0 else 0
        stop_loss = round(cost * (1 - DEFAULT_STOP_LOSS_PCT), 2)
        dist_to_stop = round((price - stop_loss) / price * 100, 2) if price > 0 else 0

        # 状态判定
        if pnl_pct >= 15:
            status = "\U0001f7e2 大幅盈利"
        elif pnl_pct >= 5:
            status = "\U0001f7e1 盈利中"
        elif pnl_pct >= 0:
            status = "\U0001f7e1 微利"
        elif pnl_pct >= -5:
            status = "⚠️ 临近止损"
        else:
            status = "\U0001f534 亏损"

        report_holdings.append({
            "code": code,
            "name": h.get("name", ""),
            "sector": h.get("sector", ""),
            "shares": shares,
            "cost": round(cost, 3),
            "price": round(price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "change_pct": round(change_pct, 2),
            "volume": volume,
            "turnover": q.get("turnover_rate", 0),
            "pnl_pct": round(pnl_pct, 2),
            "pnl_amt": round(pnl_amt, 2),
            "position_value": round(position_value, 2),
            "stop_loss": stop_loss,
            "dist_to_stop": dist_to_stop,
            "status": status,
        })

        total_value += position_value
        total_cost += cost_basis

    total_pnl = total_value - total_cost
    total_pnl_pct = round((total_pnl / total_cost * 100), 2) if total_cost > 0 else 0

    return {
        "holdings": report_holdings,
        "total_value": round(total_value, 2),
        "total_cost": round(total_cost, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": total_pnl_pct,
    }


# ── 飞书格式化 ───────────────────────────────────────────────────


def format_holdings_feishu(holdings: list[dict]) -> str:
    """将持仓报告格式化为飞书 Markdown"""
    lines = ["**持仓盈亏一览**\n"]
    for h in holdings:
        pnl_pct = h.get("pnl_pct")
        status = h.get("status", "")
        pos_value = h.get("position_value", (h.get("price") or 0) * h.get("shares", 0))
        status_str = f"{status} " if status else ""

        if pnl_pct is None:
            lines.append(
                f"- {status_str}**{h.get('name', '')}**({h.get('code', '')}) "
                f"现价 数据暂缺 | 成本 {h.get('cost', '-')} | 盈亏 数据暂缺"
            )
        else:
            sign = "+" if pnl_pct >= 0 else ""
            pnl_amt = h.get("pnl_amt", 0)
            price = h.get("price", "-")
            lines.append(
                f"- {status_str}**{h.get('name', '')}**({h.get('code', '')}) "
                f"现价 {price} | 成本 {h.get('cost', '-')} | "
                f"盈亏 {sign}{pnl_pct:.1f}%"
                + (f" ({sign}{pnl_amt:.0f}元)" if pnl_amt else "")
                + f" | 市值 {pos_value:.0f}元"
            )
    return "\n".join(lines)


def format_indices_feishu(indices: list[dict]) -> str:
    """格式化指数行情为飞书 Markdown"""
    lines = ["**主要指数**\n"]
    for idx in indices:
        sign = "+" if idx.get("change_pct", 0) >= 0 else ""
        lines.append(f"- {idx['name']}: {idx.get('price', '-')} ({sign}{idx.get('change_pct', 0):.2f}%)")
    return "\n".join(lines)


# ── 导入命令模块与主入口 ──
import sys
if __name__ == '__main__':
    if 'daily_task' not in sys.modules:
        sys.modules['daily_task'] = sys.modules['__main__']

    from _dt_morning import run_morning_enhanced
    from _dt_closing import run_closing_review
    from _dt_intraday import run_intraday_analysis
    from _dt_hot import run_hot_stocks
    from _dt_evening import run_evening
    from _dt_overnight import run_overnight
    from _dt_tech import run_tech_scan
    from _dt_poscheck import run_position_check
    from experts.decision_backtest import run_smart_backtest_and_dreamer
    from experts.sector_tracker import collect_daily_snapshot, generate_rotation_report

    MODE_HANDLERS = {
        "morning_enhanced": (run_morning_enhanced, "盘前增强简报"),
        "morning": (run_morning_enhanced, "盘前简报(别名)"),
        "closing_review": (run_closing_review, "收盘复盘"),
        "closing": (run_closing_review, "收盘复盘(别名)"),
        "intraday_analysis": (run_intraday_analysis, "盘中30分钟快照"),
        "intraday": (run_intraday_analysis, "盘中快照(别名)"),
        "hot_stocks": (run_hot_stocks, "热门股票采集"),
        "evening": (run_evening, "晚间总结"),
        "overnight": (run_overnight, "隔夜分析"),
        "tech_scan": (run_tech_scan, "技术形态扫描"),
        "scan": (run_tech_scan, "技术扫描(别名)"),
        "position_check": (run_position_check, "持仓三层检查"),
        "pos": (run_position_check, "持仓检查(别名)"),
        "backtest": (run_smart_backtest_and_dreamer, "决策T+5回测+Dreamer权重更新"),
        "sector_collect": (collect_daily_snapshot, "板块日数据采集"),
        "weekly_sector": (generate_rotation_report, "周度板块轮动报告"),
    }

def main():
    """主入口：按 mode 参数调度任务"""
    if len(sys.argv) < 2:
        print("\u7528\u6cd5: python daily_task.py <mode> [sub_mode]")
        print(f"\u53ef\u7528\u6a21\u5f0f: {', '.join(sorted(set(MODE_HANDLERS.keys())))}")
        print("  intraday_analysis \u9700\u7b2c\u4e8c\u4e2a\u53c2\u6570: midday \u6216 close")
        sys.exit(1)

    mode = sys.argv[1].lower()
    sub_mode = sys.argv[2] if len(sys.argv) > 2 else ""

    if mode not in MODE_HANDLERS:
        print(f"\u672a\u77e5\u6a21\u5f0f: {mode}")
        print(f"\u53ef\u7528\u6a21\u5f0f: {', '.join(sorted(set(MODE_HANDLERS.keys())))}")
        sys.exit(1)

    handler, description = MODE_HANDLERS[mode]

    TRADING_DAY_MODES = {
        "morning_enhanced", "morning",
        "closing_review", "closing",
        "intraday_analysis", "intraday",
        "hot_stocks",
        "evening",
        "overnight",
        "tech_scan", "scan",
        "position_check", "pos",
    }
    if mode in TRADING_DAY_MODES and not is_trading_day():
        logger.info(f"\u4eca\u65e5\u975e\u4ea4\u6613\u65e5\uff0c\u8df3\u8fc7 {mode} ({description})")
        return
    logger.info(f"\u542f\u52a8\u6a21\u5f0f: {mode} ({description}) | \u65f6\u95f4: {timestamp_now()}")

    start_time = time.time()

    try:
        if mode in ("intraday_analysis", "intraday"):
            sub = sub_mode or "midday"
            handler(sub)
        else:
            handler()
    except Exception as e:
        logger.exception(f"\u6a21\u5f0f {mode} \u6267\u884c\u5f02\u5e38: {e}")
        try:
            publish_status("front-office", {
                "health": "degraded",
                "pipeline": {mode: {"status": "error", "error": str(e)[:200]}},
                "issues": [{"area": mode, "severity": "high", "message": str(e)[:200]}],
            })
        except Exception:
            pass
        try:
            send_feishu_message(
                f"\u4efb\u52a1\u5f02\u5e38 | {mode}",
                f"\u6a21\u5f0f `{mode}` \u6267\u884c\u5931\u8d25\n\n\u9519\u8bef: {str(e)[:200]}\n\n\u65f6\u95f4: {timestamp_now()}",
            )
        except Exception:
            pass
        sys.exit(1)

    # \u9694\u591c\u5206\u6790\u5b8c\u6210\u540e\u81ea\u52a8\u89e6\u53d1 T+5 \u56de\u6d4b\uff08\u667a\u80fd\u6a21\u5f0f\uff09
    if mode in ("overnight",):
        try:
            logger.info("[auto_backtest] overnight \u5b8c\u6210\uff0c\u81ea\u52a8\u6267\u884c T+5 \u56de\u6d4b...")
            result = run_smart_backtest_and_dreamer()
            filled = result.get("backtest", {}).get("updated", 0)
            if filled > 0:
                logger.info(f"[auto_backtest] \u56de\u6d4b\u5b8c\u6210: {filled} \u6761\u65b0\u586b\u5145, Dreamer \u6743\u91cd\u5df2\u66f4\u65b0")
            else:
                logger.info("[auto_backtest] \u65e0\u65b0\u6210\u719f outcome, \u8df3\u8fc7 Dreamer")
        except Exception as e:
            logger.warning(f"[auto_backtest] \u6267\u884c\u5f02\u5e38(\u4e0d\u5f71\u54cd\u4e3b\u6d41\u7a0b): {e}")

    # \u6536\u76d8\u590d\u76d8\u5b8c\u6210\u540e\u81ea\u52a8\u91c7\u96c6\u677f\u5757\u65e5\u6570\u636e
    if mode in ("closing_review", "closing"):
        try:
            if _already_ran_today(f"sector_collect"):
                logger.info("[sector_collect] \u4eca\u65e5\u5df2\u91c7\u96c6\uff0c\u8df3\u8fc7")
            else:
                logger.info("[sector_collect] \u6536\u76d8\u5b8c\u6210\uff0c\u81ea\u52a8\u91c7\u96c6\u677f\u5757\u6570\u636e...")
                collect_daily_snapshot()
                logger.info("[sector_collect] \u677f\u5757\u6570\u636e\u91c7\u96c6\u5b8c\u6210")
        except Exception as e:
            logger.warning(f"[sector_collect] \u91c7\u96c6\u5f02\u5e38(\u4e0d\u5f71\u54cd\u4e3b\u6d41\u7a0b): {e}")

    elapsed = time.time() - start_time
    logger.info(f"\u6a21\u5f0f {mode} \u5b8c\u6210\uff0c\u8017\u65f6 {elapsed:.1f}s")

    try:
        pipeline_status = {
            mode: {
                "status": "ok",
                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_s": round(elapsed, 1),
            }
        }
        ch_ok = {k: "ok" if v else "blocked" for k, v in _channels_ok.items()}
        publish_status("front-office", {
            "health": "healthy",
            "pipeline": pipeline_status,
            "data_channels": ch_ok,
            "artifacts": [],
            "issues": [],
        })
    except Exception as e:
        logger.warning("\u524d\u5385\u90e8\u72b6\u6001\u53d1\u5e03\u5931\u8d25: %s", e)

if __name__ == "__main__":
    main()
