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
        {"code": "601789", "name": "宁波建工", "shares": 5200, "cost": 6.206, "sector": "建筑工程/基建", "first_buy": "2026-05-05", "latest_buy": "2026-05-15"},
        {"code": "002156", "name": "通富微电", "shares": 600, "cost": 44.850, "sector": "半导体封测", "first_buy": "2026-04-27", "latest_buy": "2026-05-15"},
        {"code": "002208", "name": "合肥城建", "shares": 2100, "cost": 24.599, "sector": "房地产", "first_buy": "2026-05-15", "latest_buy": "2026-05-20"},
        {"code": "300792", "name": "壹网壹创", "shares": 400, "cost": 35.520, "sector": "电商服务/数字营销", "first_buy": "2026-05-13", "latest_buy": "2026-05-18"},
        {"code": "300339", "name": "润和软件", "shares": 300, "cost": 44.910, "sector": "金融科技/鸿蒙", "first_buy": "2026-05-18", "latest_buy": "2026-05-18"},
        {"code": "300136", "name": "信维通信", "shares": 400, "cost": 113.605, "sector": "消费电子/射频", "first_buy": "2026-05-18", "latest_buy": "2026-05-20"},
        {"code": "600498", "name": "烽火通信", "shares": 300, "cost": 57.210, "sector": "通信设备", "first_buy": "2026-05-20", "latest_buy": "2026-05-20"},
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


# ── 模式: morning_enhanced ───────────────────────────────────────


def _load_latest_trade_plan():
    """加载最新的隔夜交易计划"""
    import glob
    plan_dir = ensure_data_dir() / "trade_plans"
    if not plan_dir.exists():
        return None
    files = sorted(glob.glob(str(plan_dir / "plan_*.json")))
    if not files:
        return None
    try:
        with open(files[-1], "r", encoding="utf-8") as f:
            plan = json.load(f)
        # 只提取关键信息，去掉冗余
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
    # 从日历获取市场状态
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
            # 数据源不可用 → 标记缺失，不生成虚假盈亏
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

        # 三层检查告警
        alerts = []
        # 硬止损
        if pnl_pct <= -7:
            alerts.append(f"⛔ 硬止损触发 {pnl_pct:.1f}%")
        elif pnl_pct <= -5:
            alerts.append(f"⚠ 接近硬止损 {pnl_pct:.1f}%")
        elif pnl_pct <= -3:
            alerts.append(f"⚡ 软止损触发 {pnl_pct:.1f}%")
        # 危险区检测 (持仓天数3-5天 + 浮亏)
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
        # 止盈
        if pnl_pct >= 15:
            alerts.append(f"💰 +15%全止盈")
        elif pnl_pct >= 8:
            alerts.append(f"💰 +8%止盈一半")
        # 移动止损
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

    # 交易计划速览
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

    if news_alerts:
        md_lines.append("\n## 重要新闻\n")
        for n in news_alerts[:10]:
            md_lines.append(f"- [{n.get('source', '')}] {n.get('title', '')}\n")

    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown 输出: {md_path}")

    # 发送飞书
    feishu_content = format_indices_feishu(global_data.get("indices", []))
    feishu_content += "\n\n" + format_holdings_feishu(portfolio_scan["holdings"])
    # 附加告警摘要
    urgent_alerts = [h for h in portfolio_scan["holdings"] if h["alerts"]]
    if urgent_alerts:
        feishu_content += "\n\n**⚠ 持仓告警**\n"
        for h in urgent_alerts:
            for a in h["alerts"]:
                feishu_content += f"- {h['name']}({h['code']}): {a}\n"
    if news_alerts:
        feishu_content += "\n**重要新闻**\n"
        for n in news_alerts[:5]:
            feishu_content += f"- {n.get('title', '')[:80]}\n"

    ok = send_feishu_message(f"盘前简报 | {date_str}", feishu_content)
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("morning_enhanced 完成")
    return output


# ── 模式: closing_review ─────────────────────────────────────────


def run_closing_review():
    """收盘复盘 (15:15 执行)"""
    logger.info("=" * 50)
    logger.info("执行 closing_review — 收盘复盘")
    ensure_data_dir()

    dt = datetime.now()
    date_str = date_today()

    # 1) 持仓盈亏
    logger.info("计算持仓盈亏...")
    holdings = load_portfolio()
    holdings_report = calculate_position_report(holdings)

    # 2) 市场背景
    logger.info("获取指数行情...")
    indices = []
    for code, name in GLOBAL_INDICES:
        q = fetch_index_quote(code, name)
        if q:
            indices.append({
                "name": name,
                "code": code,
                "price": q.get("price", 0),
                "change_pct": q.get("change_pct", 0),
            })

    # 3) 热门板块 (仅东方财富可用时)
    hot_sectors = []
    if not EASTMONEY_BLOCKED:
        try:
            params = {
                "pn": 1, "pz": 10, "po": 1, "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2, "invt": 2,
                "fid": "f3",
                "fs": "m:90+t:2",  # 行业板块
                "fields": "f2,f3,f4,f12,f14",
            }
            r = safe_request("https://push2.eastmoney.com/api/qt/clist/get", params=params, timeout=10)
            if r:
                items = r.json().get("data", {}).get("diff", [])
                for item in items:
                    hot_sectors.append({
                        "name": item.get("f14", ""),
                        "change_pct": item.get("f3", 0),
                    })
        except Exception as e:
            logger.warning(f"板块数据获取失败: {e}")

    # 4) 持仓建议
    recommendations = []
    for h in holdings_report["holdings"]:
        pnl = h["pnl_pct"]
        dist = h["dist_to_stop"]
        if pnl >= 15:
            recommendations.append({
                "code": h["code"], "name": h["name"],
                "action": "考虑部分止盈",
                "detail": f"浮盈{pnl:.1f}%，评估是否分批锁利",
                "urgency": "medium",
            })
        elif dist <= 8:
            recommendations.append({
                "code": h["code"], "name": h["name"],
                "action": "关注",
                "detail": f"距止损位{dist:.1f}%，监控是否企稳",
                "urgency": "medium",
            })

    # 构建输出
    output = {
        "title": f"收盘复盘 | {date_str}日",
        "date": date_str,
        "time": dt.strftime("%H:%M:%S"),
        "is_trading_hours": is_market_hours(dt),
        "holdings_report": holdings_report,
        "market_context": {
            "indices": indices,
            "breadth": {},
        },
        "hot_sectors": hot_sectors,
        "actions": recommendations,
        "mcp_checklist": {
            "fund_flow_check": [
                {"code": h["code"], "tool": "mcp__china-stock__get_fund_flow",
                 "purpose": "验证超大单方向是否与量价模型一致"}
                for h in holdings_report["holdings"]
            ],
            "volume_price_phase": [
                {"code": h["code"], "tool": "mcp__china-stock__get_hist_data",
                 "purpose": "识别当前处于VCP五阶段中的哪个阶段"}
                for h in holdings_report["holdings"]
            ],
            "investor_sentiment": [
                {"code": h["code"], "tool": "mcp__china-stock__get_investor_sentiment",
                 "purpose": "补充情绪数据辅助判断"}
                for h in holdings_report["holdings"]
            ],
        },
    }

    # 写入JSON
    json_path = ensure_data_dir() / "closing_review.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    # 写入Markdown
    md_path = ensure_data_dir() / "closing_review.md"
    md_lines = []
    md_lines.append(f"# 收盘复盘 | {date_str}\n")
    md_lines.append(f"**时间**: {dt.strftime('%H:%M:%S')}\n")

    # ── 盘中异动回顾（三线打通）──
    try:
        from stage_context import intraday_summary
        ims = intraday_summary()
        if ims:
            md_lines.append("\n" + ims + "\n")
    except ImportError:
        pass

    md_lines.append("\n## 指数\n")
    md_lines.append("| 指数 | 点位 | 涨跌 |")
    md_lines.append("|------|------|------|")
    for idx in indices:
        sign = "+" if idx.get("change_pct", 0) >= 0 else ""
        md_lines.append(f"| {idx['name']} | {idx['price']:.2f} | {sign}{idx['change_pct']:.2f}% |")

    md_lines.append("\n## 持仓\n")
    rpt = holdings_report
    md_lines.append(f"总市值: **{rpt['total_value']:,.0f}** | 总盈亏: **{rpt['total_pnl']:+,.0f}** ({rpt['total_pnl_pct']:+.1f}%)\n")
    md_lines.append("| 股票 | 现价 | 成本 | 盈亏% | 盈亏额 | 距止损 |")
    md_lines.append("|------|------|------|-------|--------|--------|")
    for h in rpt["holdings"]:
        sign = "+" if h["pnl_pct"] >= 0 else ""
        md_lines.append(
            f"| {h['name']}({h['code']}) | {h['price']} | {h['cost']} | "
            f"{sign}{h['pnl_pct']:.1f}% | {sign}{h['pnl_amt']:,.0f} | {h['dist_to_stop']:.1f}% |"
        )

    if hot_sectors:
        md_lines.append("\n## 热门板块\n")
        for s in hot_sectors[:8]:
            md_lines.append(f"- {s['name']}: {s['change_pct']:+.2f}%\n")

    if recommendations:
        md_lines.append("\n## 操作建议\n")
        for r in recommendations:
            md_lines.append(f"- **{r['name']}**: {r['action']} — {r['detail']}\n")

    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown 输出: {md_path}")

    # 发送飞书
    feishu_content = format_indices_feishu(indices)
    feishu_content += f"\n\n组合总市值: **{rpt['total_value']:,.0f}元** | 总盈亏: **{rpt['total_pnl']:+,.0f}元 ({rpt['total_pnl_pct']:+.1f}%)**\n\n"
    feishu_content += format_holdings_feishu(rpt["holdings"])

    if recommendations:
        feishu_content += "\n**操作建议**\n"
        for r in recommendations:
            feishu_content += f"- {r['name']}: {r['action']} ({r['urgency']})\n"

    # 发送前保鲜检查
    preflight = preflight_scan(["portfolio.json", "closing_review.json"])
    if preflight["healthy"]:
        ok = send_feishu_message(f"收盘复盘 | {date_str}", feishu_content, chat_id="closing")
        logger.info(f"飞书发送: {'成功' if ok else '失败'}")
    else:
        logger.warning(f"收盘复盘跳过发送: {preflight['summary']}")
        send_feishu_message(f"⚠ 收盘复盘跳过 | {date_str}",
                           f"数据保鲜检查未通过:\n{preflight['summary']}", chat_id="alerts")
    logger.info("closing_review 完成")
    return output


# ── 模式: intraday_analysis ─────────────────────────────────────


def run_intraday_analysis(mode: str):
    """30分钟盘中快照 (11:30 或 15:00 执行)"""
    logger.info("=" * 50)
    logger.info(f"执行 intraday_analysis — {mode}")
    ensure_data_dir()

    # 去重守卫: 同日同mode只跑一次，防止调度器重复触发
    dt = datetime.now()
    dedup_key = f"analysis_{mode}_{dt.strftime('%Y%m%d')}"
    if _already_ran_today(dedup_key):
        logger.warning(f"[{mode}] 今日已执行过，跳过重复调用")
        return None

    ts_compact = date_now_compact()

    # 1) 指数
    indices = {}
    for code, name in GLOBAL_INDICES:
        q = fetch_index_quote(code, name)
        if q:
            # 使用拼音 key
            key_map = {"上证指数": "sh", "深证成指": "sz", "创业板指": "cy", "科创50": "kc50"}
            indices[key_map.get(name, name)] = q.get("price", 0)

    # 2) 持仓行情
    holdings = load_portfolio()
    codes = [h["code"] for h in holdings]
    quotes = fetch_quotes_batch(codes)

    holdings_data = []
    total_value = 0.0
    total_cost = 0.0

    for h in holdings:
        q = quotes.get(h["code"])
        if q is None or q.get("price", 0) <= 0:
            logger.warning(f"⚠ {h['code']} 30min行情缺失，使用成本价")
            price = h.get("cost", 0)
            q = {}
        else:
            price = q.get("price", h.get("cost", 0))
        cost = h["cost"]
        shares = h["shares"]
        mv = price * shares
        pnl_pct = round(((price - cost) / cost * 100), 2) if cost > 0 else 0

        holdings_data.append({
            "code": h["code"],
            "name": h.get("name", ""),
            "price": price,
            "today_chg": q.get("change_pct", 0),
            "cost": cost,
            "pnl_pct": pnl_pct,
            "mv": round(mv, 2),
        })
        total_value += mv
        total_cost += cost * shares

    total_pnl = total_value - total_cost
    total_pnl_pct = round((total_pnl / total_cost * 100), 2) if total_cost > 0 else 0

    output = {
        "type": "30min_analysis",
        "time": dt.strftime("%Y-%m-%d %H:%M"),
        "indices": indices,
        "portfolio": {
            "total_value": round(total_value, 2),
            "total_cost": round(total_cost, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": total_pnl_pct,
        },
        "holdings": holdings_data,
    }

    # 写入JSON
    json_path = ensure_data_dir() / f"analysis_30min_{ts_compact}.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    # 写入Markdown
    md_path = ensure_data_dir() / f"analysis_30min_{ts_compact}.md"
    md_lines = []
    md_lines.append(f"# 盘中快照 | {dt.strftime('%Y-%m-%d %H:%M')}\n")
    if indices:
        md_lines.append("\n## 指数\n")
        for k, v in indices.items():
            md_lines.append(f"- {k}: {v:.2f}\n")
    md_lines.append(f"\n组合市值: {total_value:,.0f} | 盈亏: {total_pnl:+,.0f} ({total_pnl_pct:+.1f}%)\n")
    md_lines.append("| 股票 | 现价 | 日内涨跌 | 盈亏 | 市值 |")
    md_lines.append("|------|------|----------|------|------|")
    for h in holdings_data:
        sign = "+" if h["pnl_pct"] >= 0 else ""
        md_lines.append(f"| {h['name']}({h['code']}) | {h['price']} | {h['today_chg']:+.1f}% | {sign}{h['pnl_pct']:.1f}% | {h['mv']:,.0f} |")
    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown 输出: {md_path}")

    # 飞书摘要
    feishu_content = f"盘中快照 ({dt.strftime('%H:%M')})\n组合市值: **{total_value:,.0f}元** | 盈亏: **{total_pnl:+,.0f}元 ({total_pnl_pct:+.1f}%)**\n"
    feishu_content += "\n".join(
        f"- {h['name']}: {h['price']} ({h['today_chg']:+.1f}%)"
        for h in holdings_data
    )
    ok = send_feishu_message(f"盘中快照 | {dt.strftime('%m/%d %H:%M')}", feishu_content, chat_id="midday")
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("intraday_analysis 完成")
    return output


# ── 模式: hot_stocks ─────────────────────────────────────────────


def run_hot_stocks():
    """热门股票采集 (09:15 起每小时执行)"""
    logger.info("=" * 50)
    logger.info("执行 hot_stocks — 热门股票采集")
    ensure_data_dir()

    stocks = collect_hot_stocks()

    output = {
        "update_time": datetime.now().isoformat(),
        "top": stocks,
    }

    json_path = ensure_data_dir() / "hot_stocks.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path} ({len(stocks)} 条)")

    # 存数据库
    if _DB_AVAILABLE and stocks:
        try:
            db_save_hot_stocks(stocks)
            logger.info(f"数据库保存: {len(stocks)} 条")
        except Exception as e:
            logger.warning(f"数据库保存失败: {e}")

    # 保鲜检查：采集到空数据时不发送
    if not stocks:
        logger.warning("hot_stocks 采集结果为空，跳过飞书发送")
    else:
        # 飞书摘要（仅发送 Top 10）
        lines = ["**热门股票 Top 10**\n"]
        for s in stocks[:10]:
            sign = "+" if s.get("change_pct", 0) >= 0 else ""
            lines.append(f"- {s.get('rank','')}. {s['name']}({s['code']}) {s.get('price','')} ({sign}{s.get('change_pct',0):.2f}%)")
        ok = send_feishu_message(f"热门股票 | {datetime.now().strftime('%H:%M')}", "\n".join(lines), chat_id="midday")
        logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("hot_stocks 完成")
    return output


# ── 模式: evening ────────────────────────────────────────────────


def run_evening():
    """晚间总结 (22:00 执行)"""
    logger.info("=" * 50)
    logger.info("执行 evening — 晚间总结")
    ensure_data_dir()

    dt = datetime.now()
    date_str = date_today()

    # 1) 汇总当天数据
    news_items = fetch_news_for_holdings([h["code"] for h in load_portfolio()], limit=30)

    # 2) 尝试读取当日盘中快照
    snapshots = []
    try:
        for f in sorted(ensure_data_dir().glob("analysis_30min_*.json")):
            if date_str.replace("-", "") in f.name:
                snapshots.append(f.name)
    except Exception:
        pass

    # 3) 读取热门股票
    hot_data = {}
    hot_path = ensure_data_dir() / "hot_stocks.json"
    if hot_path.exists():
        try:
            hot_data = json.loads(hot_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    output = {
        "title": f"晚间总结 | {date_str}日",
        "date": date_str,
        "time": dt.strftime("%H:%M:%S"),
        "news_count": len(news_items),
        "top_news": news_items[:15],
        "snapshots_available": snapshots,
        "hot_stocks_summary": {
            "total": len(hot_data.get("top", [])),
            "top5": [
                {"name": s.get("name", ""), "code": s.get("code", ""),
                 "change_pct": s.get("change_pct", 0), "rank": s.get("rank", "")}
                for s in hot_data.get("top", [])[:5]
            ],
        },
    }

    json_path = ensure_data_dir() / f"news_evening_{date_str.replace('-', '')}_2200.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    # 生成Markdown晚间报告
    md_lines = []
    md_lines.append(f"# 晚间总结 | {date_str}\n")
    md_lines.append(f"**生成时间**: {dt.strftime('%H:%M:%S')}\n")
    md_lines.append(f"\n## 今日新闻 ({len(news_items)}条)\n")
    for n in news_items[:15]:
        md_lines.append(f"- [{n.get('source','')}] {n.get('title','')}\n")

    report_path = ensure_data_dir() / f"report_evening_{date_str.replace('-', '')}.md"
    report_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"报告输出: {report_path}")

    # 飞书摘要
    feishu_content = f"今日新闻 **{len(news_items)}** 条\n"
    for n in news_items[:10]:
        feishu_content += f"- {n.get('title', '')[:80]}\n"

    ok = send_feishu_message(f"晚间总结 | {date_str}", feishu_content)
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("evening 完成")
    return output


# ── 模式: overnight ──────────────────────────────────────────────


def run_overnight():
    """隔夜分析 (23:30 执行)"""
    logger.info("=" * 50)
    logger.info("执行 overnight — 隔夜分析")
    ensure_data_dir()

    # 去重守卫: 同日只跑一次
    dt = datetime.now()
    if _already_ran_today(f"overnight_{dt.strftime('%Y%m%d')}"):
        logger.warning("[overnight] 今日已执行过，跳过重复调用")
        return None

    ts_compact = date_now_compact()

    # 1) 美股指数 (akshare → 东方财富备选)
    us_market = get_us_index_quotes()
    if not us_market and not EASTMONEY_BLOCKED:
        for code, name in US_INDICES:
            q = fetch_quote_eastmoney(code)
            if q:
                us_market.append({
                    "name": name,
                    "price": q.get("price", 0),
                    "change_pct": q.get("change_pct", 0),
                })

    # 2) 汇总今日数据源
    holdings = load_portfolio()
    today_news = fetch_news_for_holdings([h["code"] for h in holdings], limit=20)

    # 3) 下一交易日展望
    outlook = "观望"
    if is_trading_day():
        outlook = "正常交易"

    output = {
        "title": f"隔夜分析 | {date_today()}日",
        "date": date_today(),
        "time": dt.strftime("%H:%M:%S"),
        "us_market": us_market,
        "key_developments": today_news[:10],
        "next_day_outlook": outlook,
    }

    json_path = ensure_data_dir() / f"analysis_overnight_{ts_compact}.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"JSON 输出: {json_path}")

    md_lines = []
    md_lines.append(f"# 隔夜分析 | {date_today()}\n")
    md_lines.append(f"**时间**: {dt.strftime('%H:%M:%S')}\n")
    md_lines.append("\n## 美股\n")
    for m in us_market:
        sign = "+" if m["change_pct"] >= 0 else ""
        md_lines.append(f"- {m['name']}: {m['price']:.2f} ({sign}{m['change_pct']:.2f}%)\n")
    md_lines.append(f"\n**明日展望**: {outlook}\n")

    if today_news:
        md_lines.append("\n## 关键进展\n")
        for n in today_news[:10]:
            md_lines.append(f"- {n.get('title', '')}\n")

    md_path = ensure_data_dir() / f"analysis_overnight_{ts_compact}.md"
    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"Markdown 输出: {md_path}")

    # 飞书摘要
    feishu_content = ""
    if us_market:
        feishu_content += "**美股**\n"
        for m in us_market:
            sign = "+" if m["change_pct"] >= 0 else ""
            feishu_content += f"- {m['name']}: {sign}{m['change_pct']:.2f}%\n"
    feishu_content += f"\n明日展望: **{outlook}**"

    ok = send_feishu_message(f"隔夜分析 | {date_today()}", feishu_content, chat_id="overnight")
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("overnight 完成")
    return output


# ── 模式: tech_scan ──────────────────────────────────────────────


def run_tech_scan():
    """技术形态扫描 (15:30 执行)"""
    logger.info("=" * 50)
    logger.info("执行 tech_scan — 技术形态扫描")
    ensure_data_dir()

    timestamp = timestamp_now()
    holdings = load_portfolio()
    codes = [h["code"] for h in holdings]

    # 1) VCP扫描
    logger.info(f"运行 VCP 扫描 ({len(codes)} 只股票)...")
    if _SKILL_AVAILABLE:
        vcp_result = scan_vcp(codes)
    else:
        vcp_result = {"scan_type": "vcp", "param": None, "time": timestamp, "count": 0, "results": []}

    vcp_result["time"] = timestamp
    vcp_path = ensure_data_dir() / "scan_vcp_default.json"
    vcp_path.write_text(json.dumps(vcp_result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"VCP 输出: {vcp_path} ({vcp_result.get('count', 0)} 个信号)")

    # 2) 技术指标扫描
    logger.info(f"运行技术指标扫描...")
    if _SKILL_AVAILABLE:
        tech_result = scan_watchlist_tech(codes)
    else:
        tech_result = {"scan_type": "watchlist_tech", "param": None, "time": timestamp, "count": 0, "results": []}

    tech_result["time"] = timestamp
    tech_path = ensure_data_dir() / "scan_watchlist_tech_default.json"
    tech_path.write_text(json.dumps(tech_result, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"技术指标 输出: {tech_path} ({tech_result.get('count', 0)} 个信号)")

    # 飞书摘要
    feishu_lines = []
    feishu_lines.append(f"**VCP形态扫描** — {vcp_result.get('count', 0)} 个信号\n")
    for r in vcp_result.get("results", [])[:8]:
        feishu_lines.append(
            f"- {r.get('code','')}: {r.get('phase','')} "
            f"评分{r.get('score','')} | 现价{r.get('price','')}"
        )

    feishu_lines.append(f"\n**技术指标扫描** — {tech_result.get('count', 0)} 个信号\n")
    for r in tech_result.get("results", [])[:8]:
        feishu_lines.append(
            f"- {r.get('code','')}: {r.get('trend','')} "
            f"RSI{r.get('rsi','')} | 量比{r.get('vol_ratio','')}"
        )

    ok = send_feishu_message(f"技术扫描 | {datetime.now().strftime('%m/%d %H:%M')}", "\n".join(feishu_lines), chat_id="closing")
    logger.info(f"飞书发送: {'成功' if ok else '失败'}")

    logger.info("tech_scan 完成")


# ── 模式: position_check ─────────────────────────────────────────


def run_position_check():
    """持仓三层检查 — 实时价格 + 硬止损/软止损/危险区/止盈/超时"""
    logger.info("=" * 50)
    logger.info("执行 position_check — 持仓三层检查")
    ensure_data_dir()

    timestamp = timestamp_now()
    date_str = date_today()
    holdings = load_portfolio()

    if not holdings:
        logger.warning("无持仓数据，跳过")
        return

    codes = [h["code"] for h in holdings]
    quotes = fetch_quotes_batch(codes)
    prices = {code: q["price"] for code, q in quotes.items() if q.get("price", 0) > 0}

    # 使用 PositionManager 进行检查
    if _POSITION_MGR_AVAILABLE:
        mgr = PositionManager()
        # 用 daily_task 持仓覆盖 PositionManager 的硬编码持仓以保持一致
        mgr.holdings = [
            {"code": h["code"], "name": h["name"], "qty": h["shares"],
             "cost": h["cost"], "sector": h.get("sector", ""),
             "first_buy": h.get("first_buy", ""),
             "latest_buy": h.get("latest_buy", "")}
            for h in holdings
        ]
        positions = mgr.update_positions(prices)
        can_open, open_reasons = mgr.can_open_new()
    else:
        positions = _simple_position_check(holdings, prices)
        can_open = True
        open_reasons = []

    # 分类
    emergency = [p for p in positions if p.action == "清仓"] if _POSITION_MGR_AVAILABLE else []
    warning_ps = [p for p in positions if p.action == "减半"] if _POSITION_MGR_AVAILABLE else []
    normal = [p for p in positions if p.action == "持有"] if _POSITION_MGR_AVAILABLE else positions

    # 总值
    total_value = sum(p.market_value for p in positions if p.last_price > 0)
    total_pnl = sum(p.pnl_amount for p in positions if p.last_price > 0)
    total_cost = sum(p.cost * p.qty for p in positions)

    # JSON 输出
    output = {
        "date": date_str,
        "time": timestamp,
        "total_cost": round(total_cost, 2),
        "total_value": round(total_value, 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl / total_cost * 100, 2) if total_cost > 0 else 0,
        "can_open_new": can_open,
        "open_blockers": [r[1] for r in open_reasons if r[0] == "NOGO"] if not can_open else [],
        "emergency": [{"code": p.code, "name": p.name, "action": p.action,
                        "pnl_pct": round(p.pnl_pct, 2), "warnings": p.warnings}
                      for p in emergency],
        "warnings": [{"code": p.code, "name": p.name, "action": p.action,
                       "pnl_pct": round(p.pnl_pct, 2), "warnings": p.warnings}
                     for p in warning_ps],
        "all_positions": [
            {"code": p.code, "name": p.name, "qty": p.qty, "cost": p.cost,
             "last_price": p.last_price if p.last_price > 0 else None,
             "pnl_pct": round(p.pnl_pct, 2) if p.last_price > 0 else None,
             "hold_days": p.hold_days, "status": p.status, "action": p.action,
             "warnings": p.warnings if hasattr(p, 'warnings') else []}
            for p in positions
        ],
    }
    json_path = ensure_data_dir() / "position_check.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"持仓数据已写入: {json_path}")

    # Markdown / 日志输出
    print(f"\n{'='*60}")
    print(f"  持仓三层检查 — {date_str} {timestamp}")
    print(f"{'='*60}")
    print(f"  总成本: {total_cost:,.0f}  总市值: {total_value:,.0f}  总盈亏: {total_pnl:+,.0f}")
    print(f"  开新仓: {'✅ 允许' if can_open else '⛔ 禁止'}")
    if not can_open:
        for reason in open_reasons:
            if reason[0] == "NOGO":
                print(f"    - {reason[1]}")

    if emergency:
        print(f"\n  ⛔ 紧急: {len(emergency)} 只需要立即处理")
        for p in emergency:
            print(f"    {p.name}({p.code}): {p.action} | {p.pnl_pct:+.1f}%")
            for w in p.warnings:
                print(f"      → {w}")

    if warning_ps:
        print(f"\n  ⚠ 警告: {len(warning_ps)} 只需关注")
        for p in warning_ps:
            print(f"    {p.name}({p.code}): {p.action} | {p.pnl_pct:+.1f}%")

    if not emergency and not warning_ps:
        print(f"\n  ✅ 所有持仓正常")

    # 飞书推送（仅紧急情况）
    if emergency:
        feishu_lines = [f"**⛔ 持仓紧急警报 — {date_str} {timestamp}**\n"]
        feishu_lines.append(f"总盈亏: {total_pnl:+,.0f} ({total_pnl/total_cost*100:+.2f}%)\n" if total_cost > 0 else "")
        for p in emergency:
            feishu_lines.append(f"\n**{p.name}({p.code})**")
            feishu_lines.append(f"- 操作: {p.action}")
            feishu_lines.append(f"- 盈亏: {p.pnl_pct:+.1f}%")
            for w in p.warnings:
                feishu_lines.append(f"- {w}")
        ok = send_feishu_message(f"⚠ 持仓警报 | {date_str}", "\n".join(feishu_lines))
        logger.info(f"飞书警报发送: {'成功' if ok else '失败'}")

    # 同时保存 Markdown
    md_lines = [
        f"# 持仓三层检查 | {date_str}\n",
        f"**时间**: {timestamp} | **开新仓**: {'✅ 允许' if can_open else '⛔ 禁止'}\n\n",
        f"## 组合总览\n",
        f"| 指标 | 数值 |\n|------|------|\n",
        f"| 总成本 | {total_cost:,.0f} |\n",
        f"| 总市值 | {total_value:,.0f} |\n",
        f"| 总盈亏 | {total_pnl:+,.0f} ({total_pnl/total_cost*100:+.2f}%) |\n\n" if total_cost > 0 else "\n",
        f"## 持仓明细\n",
        f"| 代码 | 名称 | 持仓 | 成本 | 现价 | 盈亏 | 天数 | 状态 | 操作 |\n",
        f"|------|------|------|------|------|------|------|------|------|\n",
    ]
    for p in positions:
        price_str = f"{p.last_price:.2f}" if p.last_price > 0 else "-"
        pnl_str = f"{p.pnl_pct:+.1f}%" if p.last_price > 0 else "-"
        md_lines.append(
            f"| {p.code} | {p.name} | {p.qty} | {p.cost:.2f} | {price_str} | "
            f"{pnl_str} | {p.hold_days} | {p.status} | {p.action} |\n")
        if hasattr(p, 'warnings') and p.warnings:
            for w in p.warnings:
                md_lines.append(f"| | → {w} | | | | | | | |\n")
    md_path = ensure_data_dir() / "position_check.md"
    md_path.write_text("".join(md_lines), encoding="utf-8")
    logger.info(f"持仓报告已写入: {md_path}")

    return output


def _simple_position_check(holdings, prices):
    """简易持仓检查（PositionManager 不可用时回退）"""
    RULES = {
        "hard_stop": -7.0, "soft_stop": -3.0, "take_profit_half": 8.0,
        "take_profit_all": 15.0, "danger_zone": (3, 5), "max_hold": 10,
    }
    from dataclasses import dataclass, field
    from typing import List as _List

    @dataclass
    class SimplePos:
        code: str; name: str; qty: int; cost: float
        hard_stop_price: float; last_price: float = 0.0
        market_value: float = 0.0; pnl_pct: float = 0.0
        pnl_amount: float = 0.0; hold_days: int = 0
        status: str = "正常"; action: str = "持有"
        warnings: _List[str] = field(default_factory=list)

    results = []
    for h in holdings:
        code = h["code"]
        cost = h["cost"]
        p = SimplePos(code=code, name=h["name"], qty=h["shares"], cost=cost,
                       hard_stop_price=cost * 0.93)
        if code in prices:
            price = prices[code]
            p.last_price = price
            p.market_value = p.qty * price
            p.pnl_pct = (price - cost) / cost * 100
            p.pnl_amount = (price - cost) * p.qty

            if p.pnl_pct <= RULES["hard_stop"]:
                p.status, p.action = "止损", "清仓"
                p.warnings.append(f"硬止损触发: {p.pnl_pct:.1f}%")
            elif p.pnl_pct <= RULES["soft_stop"]:
                p.status, p.action = "预警", "减半"
                p.warnings.append(f"软止损: {p.pnl_pct:.1f}%")
            elif p.pnl_pct >= RULES["take_profit_all"]:
                p.status, p.action = "止盈", "清仓"
                p.warnings.append(f"+15%止盈: {p.pnl_pct:.1f}%")
            elif p.pnl_pct >= RULES["take_profit_half"]:
                p.status, p.action = "止盈", "减半"
                p.warnings.append(f"+8%止盈一半: {p.pnl_pct:.1f}%")
        else:
            p.warnings.append("无实时价格")
        results.append(p)
    return results


# ── 主入口 ───────────────────────────────────────────────────────


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
}


def main():
    """主入口：按 mode 参数调度任务"""
    if len(sys.argv) < 2:
        print("用法: python daily_task.py <mode> [sub_mode]")
        print(f"可用模式: {', '.join(sorted(set(MODE_HANDLERS.keys())))}")
        print("  intraday_analysis 需第二个参数: midday 或 close")
        sys.exit(1)

    mode = sys.argv[1].lower()
    sub_mode = sys.argv[2] if len(sys.argv) > 2 else ""

    if mode not in MODE_HANDLERS:
        print(f"未知模式: {mode}")
        print(f"可用模式: {', '.join(sorted(set(MODE_HANDLERS.keys())))}")
        sys.exit(1)

    handler, description = MODE_HANDLERS[mode]
    logger.info(f"启动模式: {mode} ({description}) | 时间: {timestamp_now()}")

    start_time = time.time()

    try:
        if mode in ("intraday_analysis", "intraday"):
            sub = sub_mode or "midday"
            handler(sub)
        else:
            handler()
    except Exception as e:
        logger.exception(f"模式 {mode} 执行异常: {e}")
        # 发布故障状态
        try:
            publish_status("front-office", {
                "health": "degraded",
                "pipeline": {mode: {"status": "error", "error": str(e)[:200]}},
                "issues": [{"area": mode, "severity": "high", "message": str(e)[:200]}],
            })
        except Exception:
            pass
        # 飞书告警
        try:
            send_feishu_message(
                f"任务异常 | {mode}",
                f"模式 `{mode}` 执行失败\n\n错误: {str(e)[:200]}\n\n时间: {timestamp_now()}",
            )
        except Exception:
            pass
        sys.exit(1)

    elapsed = time.time() - start_time
    logger.info(f"模式 {mode} 完成，耗时 {elapsed:.1f}s")

    # ── 发布前厅部状态 ─────────────────────────────────────────────
    try:
        pipeline_status = {
            mode: {
                "status": "ok",
                "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "elapsed_s": round(elapsed, 1),
            }
        }
        # 检查数据通道健康（从模块级变量获取）
        ch_ok = {k: "ok" if v else "blocked" for k, v in _channels_ok.items()}
        publish_status("front-office", {
            "health": "healthy",
            "pipeline": pipeline_status,
            "data_channels": ch_ok,
            "artifacts": [],
            "issues": [],
        })
    except Exception as e:
        logger.warning("前厅部状态发布失败: %s", e)


if __name__ == "__main__":
    main()
