import os

# --- Global Configuration ---
# It is recommended to set these in environment variables for security
ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN', 'eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2OTdjMjk1NWRiMmJkNDMyYjA5ZDM3NmQiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc2OTc0NDcyNSwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzY5ODEwNDAwfQ.8mt1Xz4vzP7HQVflLerHKWrtfvIt7PlD0gVjrzdyo90')
SANDBOX_ACCESS_TOKEN = os.getenv('UPSTOX_SANDBOX_ACCESS_TOKEN', 'YOUR_SANDBOX_ACCESS_TOKEN_HERE')

# MongoDB Config
MONGO_URI = os.getenv('MONGO_URI', "mongodb://localhost:27017/")
DB_NAME = os.getenv('DB_NAME', "upstox_strategy_db_new")

# API Config
UPSTOX_API_VERSION = "2.0"

# --- Strategy Configuration ---
INITIAL_INSTRUMENTS = ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]

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
