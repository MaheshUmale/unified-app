import os

# --- Global Configuration ---
# It is recommended to set these in environment variables for security
ACCESS_TOKEN = os.getenv('UPSTOX_ACCESS_TOKEN', 'YOUR_ACCESS_TOKEN_HERE')
SANDBOX_ACCESS_TOKEN = os.getenv('UPSTOX_SANDBOX_ACCESS_TOKEN', 'YOUR_SANDBOX_ACCESS_TOKEN_HERE')

# MongoDB Config
MONGO_URI = os.getenv('MONGO_URI', "mongodb://localhost:27017/")
DB_NAME = os.getenv('DB_NAME', "upstox_strategy_db")

# API Config
UPSTOX_API_VERSION = "2.0"
