import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta
import sys
import time
from collections import deque

# Assuming ORDER_FLOW_s9 contains the necessary classes and functions
# Ensure these classes do NOT try to connect to live data when a 'backtest' flag is set.
from ORDER_FLOW_s9 import StrategyEngine, PaperTradeManager, DataPersistor

# --- Configuration ---
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "upstox_strategy_db"
TICK_COLLECTION = "tick_data"
BACKTEST_SIGNAL_COLLECTION = "backtest_signals"
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
tick_collection = db[TICK_COLLECTION]

# Set the backtest flag to True for all imported components
BACKTEST_MODE = True

def run_backtest(start_time, end_time):
    """
    Runs a backtest of the trading strategy on historical tick data.
    """
    # iso_string = start.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    # start_time = datetime.strptime(iso_string, '%Y-%m-%dT%H:%M:%S.%fZ')
    # print(start_time)

    # iso_string = end.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    # end_time = datetime.strptime(iso_string, '%Y-%m-%dT%H:%M:%S.%fZ')
    # print(end_time)


    # print(f"Running backtest from {start_time.isoformat()} to {end_time.isoformat()}...")



    # Use a separate collection for backtest signals
    persistor = DataPersistor()
    persistor.db = db
    persistor.SIGNAL_COLLECTION = BACKTEST_SIGNAL_COLLECTION

    # Pass the BACKTEST_MODE flag to prevent live connections/fetches in the trade manager and engine
    trade_manager = PaperTradeManager(persistor=persistor, backtest_mode=BACKTEST_MODE)
    strategy_engine = StrategyEngine(persistor=persistor, trade_manager=trade_manager, backtest_mode=BACKTEST_MODE)

    # --- Efficiently get unique instrument keys within the time range ---
    query_filter = {
        "_insertion_time": {
            "$gte": start_time,
            "$lte": end_time
        }
    }

    # 1. Get all unique instrument keys present in the data for the time period
    try:
        instrument_keys = tick_collection.distinct("instrumentKey", query_filter)
    except Exception as e:
        print(f"Error fetching distinct instrument keys: {e}")
        return

    sort_order = [('fullFeed.marketFF.ltpc.ltt', 1)] # Sort by last trade time

    if not instrument_keys:
        print("No instrument keys found in the specified time range. Please check your data and time period.")
        return

    for instrument in instrument_keys:
        print(f"BACKTESTING FOR {instrument}")

        # 2. Fetch all ticks for this instrument in the time window
        instrument_filter = {
            "instrumentKey" : instrument,
            "_insertion_time": {
                "$gte": start_time,
                "$lte": end_time
            },
        }


        document_count = tick_collection.count_documents(instrument_filter)
        if document_count == 0:
            print(f"No tick data found for instrument {instrument} in the specified time range.")
            continue
        else:
            # print(f"Filter: {instrument_filter}")
            # Fetch ticks for the specific instrument and time range, sorted chronologically
            ticks = tick_collection.find(instrument_filter).sort(sort_order)
            #check for cursor ticks has any results
            print(f"Fetched {document_count} ticks for instrument {instrument}.")
            # Process ticks one by one for the strategy engine
            for tick in ticks:
                # Safely extract last traded quantity (ltq)
                ltpc_data = tick.get('fullFeed', {}).get('marketFF', {}).get('ltpc', {})
                ltq = ltpc_data.get('ltq', 0)

                try:
                    ltq = int(ltq)
                except (ValueError, TypeError):
                    ltq = 0

                strategy_engine.process_tick(tick, ltq)

    print("Backtest complete.")
    generate_backtest_report(db, BACKTEST_SIGNAL_COLLECTION)

def generate_backtest_report(db, collection_name):
    """
    Generates a performance report from the backtest signals.
    """
    signals = pd.DataFrame(list(db[collection_name].find()))
    if signals.empty:
        print("No signals were generated during the backtest.")
        return

    # PnL Analysis
    pnl = signals[signals['signal'] == 'SQUARE_OFF']['pnl'].sum()
    print(f"Total PnL: {pnl}")

    # Further analysis can be added here (e.g., win/loss ratio, Sharpe ratio, etc.)

from datetime import datetime, time, date
import pytz


if __name__ == "__main__":

    # --- Define the specific date and time for backtesting ---

    # Choose the date you want to backtest (e.g., the previous trading day)
    BACKTEST_DATE = datetime(2025, 12, 8)

    # Set market open time (9:15:00 AM)
    start_time = BACKTEST_DATE.replace(hour=9, minute=15, second=0, microsecond=0)

    # Set market close time (3:30:00 PM)
    end_time = BACKTEST_DATE.replace(hour=15, minute=30, second=0, microsecond=0)

    print(f"Running backtest for {BACKTEST_DATE.date()} from {start_time.strftime('%H:%M:%S')} to {end_time.strftime('%H:%M:%S')}...")

    # --- Define Timezone Constants ---
    IST = pytz.timezone('Asia/Kolkata')
    BACKTEST_DATEStart = date(2025, 12, 8)
    BACKTEST_DATEEnd = date(2025, 12, 9)

    # 1. Define Local Market Times (IST)
    # Start Time: 9:15 AM IST
    local_start_time = IST.localize(datetime.combine(BACKTEST_DATEStart, time(9, 15)))

    # End Time: 3:30 PM IST
    local_end_time = IST.localize(datetime.combine(BACKTEST_DATEEnd, time(15, 30)))

    # 2. Convert to UTC (What MongoDB usually stores)
    start_time_utc = local_start_time.astimezone(pytz.utc)
    end_time_utc = local_end_time.astimezone(pytz.utc)


    # Check to ensure end_time is strictly after start_time
    if start_time >= end_time:
        print("Error: Start time is after or same as end time.")
    else:
        run_backtest(start_time_utc, end_time_utc)