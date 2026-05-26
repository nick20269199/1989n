"""
系统配置 - 所有路径、API密钥、常量定义
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

# Apply DNS fix before any network calls
try:
    from dns_fix import apply as _apply_dns_fix
    _apply_dns_fix()
except Exception:
    pass

# Apply global requests timeout patch (覆盖 akshare 等不设 timeout 的调用)
try:
    from _patch_timeout import apply as _apply_timeout_patch
    _apply_timeout_patch()
except Exception:
    pass

# === 路径配置（单信源：所有模块从 config 导入，不自行定义） ===
PROJECT_DIR = Path(__file__).parent
STOCK_DATA_DIR = Path(os.getenv("STOCK_DATA_DIR", "D:/1989n/stock_data"))
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "D:/1989n/screenshots"))
DATABASE_PATH = os.getenv("DATABASE_PATH", str(STOCK_DATA_DIR / "stock.db"))
LEARNING_DIR = STOCK_DATA_DIR / "learning"
ERROR_FILE = STOCK_DATA_DIR / "last_error.txt"
LOG_DIR = PROJECT_DIR / "logs"
OUTPUT_DIR = PROJECT_DIR / "output"

# === API 配置 ===
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")
FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
STOCKAPI_TOKEN = os.getenv("STOCKAPI_TOKEN", "")
DASHSCOPE_API_KEY = os.getenv("DASHSCOPE_API_KEY", "")
DASHSCOPE_API_KEY_RESEARCH = os.getenv("DASHSCOPE_API_KEY_RESEARCH", "")
DASHSCOPE_API_KEY_PARALLEL = os.getenv("DASHSCOPE_API_KEY_PARALLEL", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_KEY_RESEARCH = os.getenv("DEEPSEEK_API_KEY_RESEARCH", "")
DEEPSEEK_API_KEY_PARALLEL = os.getenv("DEEPSEEK_API_KEY_PARALLEL", "")
DEEPSEEK_API_KEY_INTRADAY = os.getenv("DEEPSEEK_API_KEY_INTRADAY", "")
DEEPSEEK_API_KEY_REVIEW = os.getenv("DEEPSEEK_API_KEY_REVIEW", "")
DEEPSEEK_API_KEY_NEWS = os.getenv("DEEPSEEK_API_KEY_NEWS", "")
FEISHU_BOT_PORT = int(os.getenv("FEISHU_BOT_PORT", "19899"))
FEISHU_BOT_CHAT_ID = os.getenv("FEISHU_BOT_CHAT_ID", "oc_983693a765e4284d1dc7bbeaf56cf1a9")
FEISHU_ENCRYPT_KEY = os.getenv("FEISHU_ENCRYPT_KEY", "")

# === 飞书表格配置 ===
FEISHU_SPREADSHEET_TOKEN = os.getenv("FEISHU_SPREADSHEET_TOKEN", "")
FEISHU_PORTFOLIO_SHEET_ID = os.getenv("FEISHU_PORTFOLIO_SHEET_ID", "")
FEISHU_REPORT_SHEET_ID = os.getenv("FEISHU_REPORT_SHEET_ID", "")
FEISHU_NEWS_SHEET_ID = os.getenv("FEISHU_NEWS_SHEET_ID", "")

# === 数据源URL ===
CLS_NEWS_FLASH_URL = "https://www.cls.cn/api/sw?app=CailianpressWeb&os=web&sv=8.4.6"
EASTMONEY_QUOTE_URL = "https://push2.eastmoney.com/api/qt/stock/get"
TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/mkline"
THS_HOT_STOCKS_URL = "https://www.10jqka.com.cn/api/hotstock"
SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_NEWS_ROLL_URL = "https://feed.mix.sina.com.cn/api/roll/get?pageid=153&lid=2516&knum=50"
EASTMONEY_NEWS_URL = "https://push2.eastmoney.com/api/qt/ulist.np/get"
THS_NEWS_URL = "https://news.10jqka.com.cn/tapp/news/push/stock"
WALLSTREETCN_LIVES_URL = "https://api-prod.wallstreetcn.com/apiv1/content/lives"
XUEQIU_TIMELINE_URL = "https://xueqiu.com/v4/statuses/public_timeline_by_category.json"

# === 请求头 ===
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# === 日志配置 ===
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# === 持仓配置（可在 .env 覆盖） ===
PORTFOLIO_FILE = PROJECT_DIR / "data" / "portfolio.json"

# === 技术分析参数 ===
VCP_MIN_TIGHTENING_DAYS = 3
MA_PERIODS = [5, 10, 20, 60, 120, 250]
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# === 新闻采集配置 ===
NEWS_INTRADAY_INTERVAL_MINUTES = 30
NEWS_MARKET_OPEN = "09:30"
NEWS_MARKET_CLOSE = "15:00"

# 确保目录存在
for d in [LOG_DIR, OUTPUT_DIR, SCREENSHOT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# === 飞书推送路由（内容类型 → 群聊） ===
FEISHU_ROUTES = {
    "main":      FEISHU_BOT_CHAT_ID,                  # 主群（默认）
    "book":      "oc_7884ad241159d9b39fb855592e19bb6d",  # 书虫群
    "news":      "oc_879207bdeaee695505d45a85afb9bca8",  # 新闻群
    "midday":    "oc_2683bbadb9721aea6e6ed585c24a3cf4",  # 午盘数据群
    "closing":   "oc_afc63ec9893d4f3393bfe5cb64203e72",  # 收盘数据群
    "alerts":    "oc_2c82fb2d0b3c326a3edd0e413dcb5089",  # 问题组告警群
    "overnight": "oc_fc5afbd06d624257b621f9bbad3e3bf7",  # 背调小队
}
