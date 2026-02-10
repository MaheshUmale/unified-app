import os

# --- Global Configuration ---
# It is recommended to set these in environment variables for security
# TradingView Config
# TV_USERNAME = os.getenv('TV_USERNAME', '')
# TV_PASSWORD = os.getenv('TV_PASSWORD', '')
import rookiepy

try:
    raw_cookies = rookiepy.brave(['.tradingview.com']) #os.getenv('TV_COOKIE', '')
    # 2. Convert to a simple name:value dictionary
    cookie_dict = {c['name']: c['value'] for c in raw_cookies}
    TV_COOKIE = cookie_dict
except Exception:
    TV_COOKIE = {}

TV_STUDY_ID = os.getenv('TV_STUDY_ID', 'USER;f9c7fa68b382417ba34df4122c632dcf')

# LocalDB Config
DUCKDB_PATH = os.getenv('DUCKDB_PATH', 'pro_trade.db')

# --- Strategy Configuration ---
INITIAL_INSTRUMENTS = ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank", "NSE_INDEX|India VIX"]
OPTIONS_UNDERLYINGS = ["NSE:NIFTY", "NSE:BANKNIFTY", "NSE:FINNIFTY"]

# --- Logging Configuration ---
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        },
    },
    "handlers": {
        "default": {
            "level": "INFO",
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["default"],
            "level": "INFO",
            "propagate": True
        },
        "uvicorn.error": {
            "level": "INFO"
        },
        "uvicorn.access": {
            "level": "INFO"
        },
    }
}
