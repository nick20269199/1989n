"""Expert system configuration — weights, models, timeouts."""

import os
from pathlib import Path

# --- Paths ---
STOCK_DATA = Path("D:/1989n/stock_data")
OUTPUT_DIR = STOCK_DATA / "expert_outputs"
MARKET_POOL_DIR = STOCK_DATA / "market_pool" / "kline"
STOCK_DB = STOCK_DATA / "stock.db"
PORTFOLIO_FILE = Path("D:/1989n/stock_analysis/data/portfolio.json")
VV_RADAR_DB = STOCK_DATA / "vv_radar.db"

# Ensure output dir exists
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# --- Expert weights (adjusted by Dreamer) ---
EXPERT_WEIGHTS = {
    "expert1_tech": 1.0,
    "expert2_money": 1.0,
    "expert3_sentiment": 1.0,
    "expert4_macro": 1.0,
    "expert5_risk": 1.0,
}

WEIGHT_FILE = Path("D:/1989n/stock_analysis/experts/expert_weights.json")

# --- Model routing ---
# Model routing
# DeepSeek: channel 1 (原key过期, 已由channel 2替换, 200✅)
# Qwen: 3 channels all 200✅
EXPERT_MODEL = {
    "expert1_tech": "deepseek",
    "expert2_money": "deepseek",
    "expert3_sentiment": "qwen",
    "expert4_macro": "qwen",
    "expert5_risk": "deepseek",
    "grader": "qwen",
    "lead": "qwen",
}

EXPERT_CHANNEL = {
    "expert1_tech": None,
    "expert2_money": None,
    "expert3_sentiment": "parallel",
    "expert4_macro": "research",
    "expert5_risk": None,
    "grader": "research",
    "lead": "primary",
}

# --- Timeouts ---
EXPERT_TIMEOUT = 60  # seconds per expert
GRADER_TIMEOUT = 45
LEAD_TIMEOUT = 120   # total pipeline timeout

# --- Grader ---
GRADER_MODEL = "qwen"
GRADER_CHANNEL = "research"
GRADER_MIN_SCORE = 0.6  # minimum average score to pass

# --- Dreamer ---
DREAMER_SCHEDULE = "0 17 * * 1-5"  # daily at 17:00 weekdays
DREAMER_WINDOW_DAYS = 30  # how many days of history to review

# --- Market state thresholds ---
MARKET_STATE_RULES = {
    "trend": {"min_rsi": 55, "max_rsi": 80, "min_volume_ratio": 1.2},
    "oscillating": {"min_rsi": 35, "max_rsi": 65, "volume_ratio_range": [0.6, 1.1]},
    "structural_shift": {"volume_ratio": 1.5, "breakout_pct": 0.03},
    "crisis": {"max_rsi": 30, "volume_ratio": 2.0},
}
