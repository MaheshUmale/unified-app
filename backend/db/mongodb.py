from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection
import os
import config
import mongomock
import logging

logger = logging.getLogger(__name__)

# --- Configuration ---
MONGO_URI = config.MONGO_URI
DB_NAME = config.DB_NAME

# --- Database Connection ---
_client: MongoClient = None

def get_db_client() -> MongoClient:
    """Initializes and returns a singleton MongoDB client with fallback to mongomock."""
    global _client
    if _client is None:
        try:
            # Use short timeout for testing environments
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            _client.server_info()
            logger.info("Connected to real MongoDB")
        except Exception as e:
            logger.warning(f"Could not connect to MongoDB, using mongomock: {e}")
            _client = mongomock.MongoClient()
    return _client

def get_db() -> Database:
    """Returns the database instance for the strategy app using a shared client."""
    return get_db_client()[DB_NAME]

def get_oi_collection() -> Collection:
    """Returns the collection for Open Interest data."""
    db = get_db()
    return db['oi_data']

def get_tick_data_collection() -> Collection:
    """Returns the collection for processed tick data."""
    db = get_db()
    return db['tick_data']

def get_raw_tick_data_collection() -> Collection:
    """Returns the collection for raw Upstox WebSocket feed data."""
    db = get_db()
    return db['raw_tick_data']

def get_instruments_collection() -> Collection:
    """Returns the collection for instrument master data."""
    db = get_db()
    return db['instruments']

def get_stocks_collection() -> Collection:
    """Returns the collection for equity/stock data."""
    db = get_db()
    return db['stocks']

def get_trendlyne_buildup_collection() -> Collection:
    """Returns the collection for Trendlyne buildup data."""
    db = get_db()
    return db['trendlyne_buildup']


SIGNAL_COLLECTION_NAME = 'trade_signals'

def get_trade_signals_collection() -> Collection:
    """Returns the collection for generated trade signals."""
    db = get_db()
    return db[SIGNAL_COLLECTION_NAME]

def ensure_indexes() -> bool:
    """
    Create indexes on collections for performance optimization.
    Returns:
        bool: True if successful.
    """
    db = get_db()

    # Index on tick_data.instrumentKey for fast instrument-specific queries
    tick_data = db['tick_data']
    tick_data.create_index('instrumentKey', background=True)
    tick_data.create_index('ts_ms', background=True)
    print("[DB] Created index on tick_data.instrumentKey and ts_ms")

    # Optional: Compound index for time-based queries
    # tick_data.create_index([('instrumentKey', 1), ('_id', 1)], background=True)

    return True
