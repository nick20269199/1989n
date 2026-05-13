"""
market_pool.config — 路径与常量
"""
from pathlib import Path

# ── 数据根目录 ──
STOCK_DATA_DIR = Path("D:/1989n/stock_data")
STOCK_ANALYSIS_DIR = Path("D:/1989n/stock_analysis")

# ── 市场池存储目录 (Parquet + JSON, 与旧kline_cache不冲突) ──
POOL_DIR = STOCK_DATA_DIR / "market_pool"
KLINE_DIR = POOL_DIR / "kline"          # {code}.parquet, 每只一只
QUOTES_FILE = POOL_DIR / "quotes.json"   # 最新实时行情快照
QUOTES_CACHE_TTL = 60                    # 行情缓存秒数

# ── 股票列表 ──
STOCK_LIST_FILE = STOCK_DATA_DIR / "a_stock_list.json"

# ── 元数据 ──
META_FILE = POOL_DIR / "meta.json"

# ── 旧版兼容 ──
OLD_KLINE_DIR = STOCK_DATA_DIR / "kline_cache"

# ── 请求参数 ──
REQUEST_TIMEOUT = 15
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}
TENCENT_HEADERS = {"Referer": "https://stock.finance.qq.com"}
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}

# ── 多线程 ──
UPDATE_WORKERS = 15  # 全市场更新并发数
