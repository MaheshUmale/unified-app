import os

# --- Global Configuration ---
# It is recommended to set these in environment variables for security
ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN', 'eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2OTdlY2M3ZjZjYTJhZTc2NjBkNGU5OWQiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc2OTkxNzU2NywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzY5OTgzMjAwfQ.k_8MAoB3YjVLY5x_cMt3Hi9xC6uOU6jlBtqInTxh7AM')
SANDBOX_ACCESS_TOKEN = os.getenv('UPSTOX_SANDBOX_ACCESS_TOKEN', 'YOUR_SANDBOX_ACCESS_TOKEN_HERE')

# MongoDB Config
MONGO_URI = os.getenv('MONGO_URI', "mongodb://localhost:27017/")
DB_NAME = os.getenv('DB_NAME', "PRO_TRADE_DATABASE")

# API Config
UPSTOX_API_VERSION = "2.0"

# --- Strategy Configuration ---
INITIAL_INSTRUMENTS = ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank", "NSE_INDEX|India VIX"]

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
