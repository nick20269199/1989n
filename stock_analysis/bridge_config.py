"""
Bridge configuration for NLP-to-Feishu messaging.

Defines settings for the local bridge service that connects
NLP analysis outputs to Feishu message delivery channels.
"""

from config import FEISHU_BOT_CHAT_ID

# === Bridge service settings ===
BRIDGE_ENABLED = True
NLP_ENABLED = True
BRIDGE_HOST = "127.0.0.1"
BRIDGE_PORT = 19898

# === NLP model selection ===
# Options: "local" (keyword-based, no dependencies),
#          "remote" (HTTP API), "mock" (returns canned results)
NLP_MODEL = "local"

# === Alert type taxonomy ===
ALERT_TYPES = [
    "price_break",
    "volume_surge",
    "technical",
    "risk",
    "system",
    "news",
    "sentiment",
]

# === Rate limiting (shared with feishu_sender) ===
BRIDGE_MAX_MSGS_PER_MINUTE = 15

# === Monitor thresholds ===
PRICE_MOVE_ALERT_PCT = 3.0       # % move that triggers a desktop popup
VOLUME_SURGE_MULTIPLE = 2.0      # volume vs 20-day average that triggers alert
RSI_OVERBOUGHT = 80
RSI_OVERSOLD = 20
STOP_LOSS_PROXIMITY_PCT = 3.0    # how close to stop loss before alerting (%)


def bridge_ready() -> bool:
    """Return True if the bridge has all minimum prerequisites to operate."""
    return BRIDGE_ENABLED and bool(FEISHU_BOT_CHAT_ID)
