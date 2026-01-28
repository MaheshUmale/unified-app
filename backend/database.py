from pymongo import MongoClient
import os
import database
# --- Configuration ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "upstox_strategy_db"

# --- Database Connection ---
def get_db_client():
    return MongoClient(MONGO_URI)

def get_db():
    client = get_db_client()
    return client[DB_NAME]

def get_oi_collection():
    db = get_db()
    return db['oi_data']

def get_tick_data_collection():
    db = get_db()
    return db['tick_data']

def get_raw_tick_data_collection():
    db = get_db()
    return db['raw_tick_data']

def get_instruments_collection():
    db = get_db()
    return db['instruments']

def get_stocks_collection():
    db = get_db()
    return db['stocks']


SIGNAL_COLLECTION_NAME ='trade_signals'
def get_trade_signals_collection():
    db = get_db()
    return db[SIGNAL_COLLECTION_NAME]

def ensure_indexes():
    """Create indexes on collections for performance optimization."""
    db = get_db()

    # Index on tick_data.instrumentKey for fast instrument-specific queries
    tick_data = db['tick_data']
    tick_data.create_index('instrumentKey', background=True)
    print("[DB] Created index on tick_data.instrumentKey")

    # Optional: Compound index for time-based queries
    # tick_data.create_index([('instrumentKey', 1), ('_id', 1)], background=True)

    return True
