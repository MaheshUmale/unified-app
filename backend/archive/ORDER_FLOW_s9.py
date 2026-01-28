import asyncio
import json
import ssl
import concurrent
from sympy import im
import websockets
import requests
from google.protobuf.json_format import MessageToDict
import sys
import time
from collections import deque
from datetime import datetime, timedelta
import uuid
import random # <-- REQUIRED FOR BACKOFF JITTER (already in your file)
import traceback # <-- REQUIRED FOR DETAILED ERROR LOGGING (already in your file)
import pandas as pd
import os
from datetime import datetime, tzinfo, timezone
import traceback
# --- Fix Imports for Archive Run ---
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config import ACCESS_TOKEN

try:
    from option_chain_fetcher import get_api_client, get_option_chain, store_option_chain_data
except ImportError:
    #print("Error: option_chain_fetcher.py not found in parent directory.", file=sys.stderr)
    sys.exit(1)

# --- MongoDB Client Setup ---
try:
    from pymongo import MongoClient
    from pymongo.errors import BulkWriteError
except ImportError:
    #print("Error: pymongo library not found. Please install it using 'pip install pymongo'", file=sys.stderr)
    sys.exit(1)

# --- MongoDB Configuration (REQUIRED) ---
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "upstox_strategy_db"
TICK_COLLECTION = "tick_data"
SIGNAL_COLLECTION = "trade_signals"

# --- Utility Function for Previous Trading Day ---
def get_previous_day_range():
    """Calculates the 15-minute range at the close of the previous trading day."""
    previous_day = datetime.now() - timedelta(days=1)
    if previous_day.weekday() == 5  : # saturday
        previous_day -= timedelta(days=1)
    elif previous_day.weekday() == 6: # sunday
        previous_day -= timedelta(days=2)

    close_time = previous_day.replace(hour=15, minute=30, second=0, microsecond=0)
    start_time = previous_day.replace(hour=15, minute=15, second=0, microsecond=0)

    if previous_day.weekday() in [5, 6]: # 5=Saturday, 6=Sunday
         print("Warning: Previous day was a weekend. Using a generic fallback date might be inaccurate.", file=sys.stderr)
    return start_time, close_time


# --- Data Persistence/Journaling Engine (Using Real MongoDB) ---
class DataPersistor:
    """
    Handles persistent logging of both raw tick data and trade signals using MongoDB.
    Uses an internal buffer to batch tick insertions for high-throughput writing.
    """

    TICK_BATCH_SIZE = 50

    def __init__(self):
        self.client = None
        self.db = None
        self.tick_buffer = deque()
        self._connect_db()

    def _connect_db(self):
        """Establishes connection to the MongoDB server."""
        # if MONGO_URI == "mongodb://localhost:27017/":
            # print("INFO: Using default MongoDB URI (localhost:27017) for single instance setup.")

        try:
            if self.client is None:
                self.client = MongoClient(MONGO_URI)
            if self.db is None:
                self.db = self.client[MONGO_DB_NAME]
            #print(f"DataPersistor successfully connected to MongoDB database: {MONGO_DB_NAME}")

        except Exception as e:
            #print(f"CRITICAL ERROR: Could not connect to MongoDB at {MONGO_URI}. Is the MongoDB service running? Error: {e}", file=sys.stderr)
            self.client = None
            self.db = None

    async def shutdown(self):
        """Cleanly flushes the remaining ticks and closes the MongoDB connection."""
        if self.db is not None:
            self._flush_ticks(force=True)
            self.client.close()
            #print("MongoDB connection closed.")

    def get_unclosed_trades(self):
            """
            Retrieves all ENTRY signals that do not have a corresponding SQUARE_OFF signal
            to facilitate position recovery on restart.
            """
            if  self.db is None:
                return []
            try:
                # 1. Find all trade_ids with a SQUARE_OFF signal
                closed_trade_ids = self.db[SIGNAL_COLLECTION].distinct("trade_id", {"signal": {"$in": ["SQUARE_OFF", "EXIT"]}})

                # 2. Find all ENTRY signals whose trade_id is NOT in the closed list
                open_entries = self.db[SIGNAL_COLLECTION].find({
                    "signal": "ENTRY",
                    "trade_id": {"$nin": closed_trade_ids}
                }).sort('timestamp', 1)

                return list(open_entries)
            except Exception as e:
                #print(f"Error retrieving unclosed trades: {e}")
                return []
    def _flush_ticks(self, force: bool = False):
        """
        Inserts all accumulated ticks from the buffer into MongoDB using insert_many.
        Called when buffer size exceeds TICK_BATCH_SIZE or on shutdown (force=True).
        """
        if self.db is None or self.tick_buffer is None:
            return

        if not force and len(self.tick_buffer) < self.TICK_BATCH_SIZE:
            return

        batch_to_insert = list(self.tick_buffer)
        self.tick_buffer.clear()

        try:
            result = self.db[TICK_COLLECTION].insert_many(batch_to_insert, ordered=False)
            if force:
                print(f"Flushed {len(result.inserted_ids)} remaining ticks on shutdown.")

        except BulkWriteError as bwe:
             print(f"MongoDB BulkWriteError (tick data): Some inserts failed. Details: {bwe.details}", file=sys.stderr)
        except Exception as e:
            print(f"MongoDB insertion error (tick data batch): {e}", file=sys.stderr)


    def log_tick(self, tick_data: dict):
        """Adds raw tick data to the internal buffer for batch processing."""
        if self.db is None:
            return

        tick_data['_insertion_time'] = datetime.now()
        self.tick_buffer.append(tick_data)

        self._flush_ticks()


    def log_signal(self, log_entry: dict):
        """Inserts a trade signal document into the 'trade_signals' collection immediately."""
        try:
            if self.db is None:
                return
            self.db[SIGNAL_COLLECTION].insert_one(log_entry)

        except Exception as e:
            print(f"MongoDB insertion error (trade signal): {e}", file=sys.stderr)

async def fetch_and_store_option_chain():
    """
    Periodically fetches and stores option chain data for NIFTY and BANKNIFTY.
    """
    api_client = get_api_client()
    nifty_key = "NSE_INDEX|Nifty 50"
    banknifty_key = "NSE_INDEX|Nifty Bank"

    while True:
        try:
            for key in [nifty_key, banknifty_key]:
                option_chain_data = get_option_chain(api_client, key)
                if option_chain_data:
                    store_option_chain_data(option_chain_data)
            await asyncio.sleep(60)  # Fetch every 60 seconds
        except Exception as e:
            #print(f"Error in fetching/storing option chain data: {e}", file=sys.stderr)
            await asyncio.sleep(60) # Wait before retrying

# -----------------------------------------------------
# --- HVN (Volume Profile) Calculation Logic ---
# -----------------------------------------------------
# (Code remains the same as provided by user)

# global hvn_previous_cache, cache_timestamp
# hvn_previous_cache = None
# cache_timestamp = None
global first_time_check
first_time_check = []

#multithread calculate_hvn for parellar processing
thread_lock = asyncio.Lock()

from concurrent.futures import ThreadPoolExecutor
def api_calculate_hvn_parallel(tasks_data: list[dict]):
    """
    API endpoint that triggers parallel HVN calculations.

    Args:
        tasks_data: A list of dictionaries, each with 'instrument_key' (str)
                    and 'ltt' (float) for processing.
    """
    results = []
    # Use a ThreadPoolExecutor within a 'with' statement for proper cleanup
    with ThreadPoolExecutor(max_workers=5) as executor: # Adjust max_workers as needed
        # Submit tasks to the executor
        future_to_task = {
            executor.submit(
                calculate_hvn,
                task['instrument_key'],
                task['ltt']
            ): task for task in tasks_data
        }

        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_task):
            task = future_to_task[future]
            try:
                data = future.result()
                if data:
                    results.append(data)
            except Exception as exc:
                print(f"{task['instrument_key']} generated an exception: {exc}")

    return {"status": "completed", "results": results}

def runVPOC_Calculation(db, key,  ltt, pocMinutes=15):
    print(f"\nProcessing instrument: {key}")
    #calculet start and end date from ltt and pocMinutes
    # ltt_datetime = datetime.fromtimestamp(ltt, tz=timezone.utc)

    ltt_seconds = float(ltt) / 1000

    ltt_datetime = datetime.utcfromtimestamp(ltt_seconds).replace(tzinfo=timezone.utc)

    start_date = ltt_datetime - timedelta(minutes=pocMinutes)
    end_date = ltt_datetime


    end_ms = int((end_date + timedelta(days=1)).timestamp() * 1000)
        # Convert Python datetime objects to milliseconds for robust comparison in MongoDB
    start_ms = int(start_date.timestamp() * 1000)
    # Add 1 day to the end date timestamp for inclusive search
    # 1. MongoDB Aggregation Pipeline for 5-minute OHLCV + VPOC (HVN)
    pipeline = [
        {
            "$match": {
                "instrumentKey": key,
                "fullFeed.marketFF.ltpc.ltt": {
                    "$exists": True,
                    "$ne": ""
                }
            }
        },
        {
            "$addFields": {
                "ltt_num": { "$toLong": "$fullFeed.marketFF.ltpc.ltt" },
            }
        },
        {
            "$match": {
                "ltt_num": { "$gte": start_ms, "$lt": end_ms }
            }
        },
        {
            "$addFields": {
                # Calculate 5-min interval start time (900000ms = 15 minutes, but using 300000ms for 5 min)
                # ASSUMPTION: The pipeline should use 300000 for 5 min bars.
                # I see 900000ms (15 min) in your code. Assuming you meant 5-min (300000ms):
                "barTime": {
                    "$subtract": [
                        "$ltt_num",
                        { "$mod": ["$ltt_num", 300000] } # <-- Changed to 300000 for 5-min consistency
                    ]
                },
                # Convert ltp and ltq to numbers
                "ltp_num": { "$toDouble": "$fullFeed.marketFF.ltpc.ltp" },
                "ltq_num": {
                    "$toDouble": {
                        "$cond": {
                            "if": { "$ne": ["$fullFeed.marketFF.ltpc.ltq", ""] },
                            "then": "$fullFeed.marketFF.ltpc.ltq",
                            "else": "0"
                        }
                    }
                }
            }
        },

        {
            "$sort": {
                "barTime": 1,
                "ltt_num": 1
            }
        },
        {
            "$group": {
                "_id": {
                    "barTime": "$barTime",
                    "instrumentKey": "$instrumentKey",
                    "ltp": "$ltp_num"
                },
                "price_volume": {"$sum": "$ltq_num"},
                "last_ltp": {"$last": "$ltp_num"},
                "last_bid": {"$last": "$fullFeed.marketFF.marketLevel.bidAskQuote.0.bidP"},
                "last_ask": {"$last": "$fullFeed.marketFF.marketLevel.bidAskQuote.0.askP"},
            }
        },
        {
            "$group": {
                "_id": {
                    "barTime": "$_id.barTime",
                    "instrumentKey": "$_id.instrumentKey"
                },
                "open": {"$first": "$_id.ltp"},
                "high": {"$max": "$_id.ltp"},
                "low": {"$min": "$_id.ltp"},
                "close": {"$last": "$last_ltp"},
                "total_volume": {"$sum": "$price_volume"},
                "price_volume_pairs": {
                    "$push": {
                        "price": "$_id.ltp",
                        "volume": "$price_volume"
                    }
                },
                "final_bid_data": {"$last": "$last_bid"},
                "final_ask_data": {"$last": "$last_ask"},
            }
        },
        { "$sort": { "_id.barTime": 1 } },
        {
            "$project": {
                "_id": 0,
                "timestamp_ms": "$_id.barTime",
                "instrumentKey": "$_id.instrumentKey",
                "open": "$open",
                "high": "$high",
                "low": "$low",
                "close": "$close",
                "volume": "$total_volume",

                "final_bid": {
                    "$toDouble": {
                        "$cond": [
                            { "$isArray": "$final_bid_data" },
                            { "$arrayElemAt": [ "$final_bid_data", 0 ] },
                            "$final_bid_data"
                        ]
                    }
                },
                "final_ask": {
                    "$toDouble": {
                        "$cond": [
                            { "$isArray": "$final_ask_data" },
                            { "$arrayElemAt": [ "$final_ask_data", 0 ] },
                            "$final_ask_data"
                        ]
                    }
                },
                "price_volume_pairs": "$price_volume_pairs"
            }
        }
    ]

    cursor = db[TICK_COLLECTION].aggregate(pipeline, allowDiskUse=True)


    # 2. Strategy Processing Loop (Bar-Based)
    bar_count = 0
    try:
        for bar_data in cursor:
            bar_count += 1

            timestamp_ms = bar_data.get('timestamp_ms')
            if timestamp_ms is None:
                continue

            try:
                if 'price_volume_pairs' in bar_data:
                    priceVolumePairs = bar_data['price_volume_pairs']
                    vpoc_price = _calculate_bar_vpoc(priceVolumePairs)
                    return vpoc_price
                else:
                    print(f"No price_volume_pairs data for {key} bar at {timestamp_ms}", file=sys.stderr)
                    continue
            except Exception as e:
                print(f"Error calculating VPOC for bar at {timestamp_ms}: {e}", file=sys.stderr)

                traceback.print_exc()
                continue
    except Exception as e:
        print(f"Error processing bars for {key}: {e}", file=sys.stderr)

        traceback.print_exc()
    return None



def _calculate_bar_vpoc( price_volume_pairs: list) -> float:
    """Finds the price with the maximum volume within the 5-minute bar (HVN)."""
    if not price_volume_pairs:
        return 0.0

    max_volume = -1
    vpoc_price = 0.0

    for pair in price_volume_pairs:
        price = pair.get('price')
        volume = pair.get('volume')

        if price is not None and volume is not None and volume > max_volume:
            max_volume = volume
            vpoc_price = price
    return vpoc_price



def calculate_hvn(db, instrument_key: str, ltt: int) -> float | None:
    """
    Calculates the HVN by checking the current 15-minute window, then falling back
    to the previous day's closing 15-minute window if the current is empty.
    """
    #firsttime_check for instrument_key so we can add to global set
    global first_time_check
    if db is None:
        return None

        #retrieve from mongo db cache collection if exists

    # get latest from hvn_cache collection using instrument_key and last_updated timestamp

    client = DataPersistor().db["hvn_cache"]#find_one({"instrumentKey": instrument_key , "last_updated": {"$gte": new Date(2025, 11, 9, 20, 44, 2)}}, sort=[("last_updated", -1)])

    ltt_seconds = float(ltt) / 1000
    ltt_datetime = datetime.utcfromtimestamp(ltt_seconds).replace(tzinfo=timezone.utc)
    # ltt int to datetime

    # 2. Define the filter dictionary using the now-defined variable
    filter = {
        'instrumentKey': 'NSE_EQ|INE670K01029',
        'last_updated': {
            '$gte': ltt_datetime  # This will now work
        }
    }

    sort=list({
        'last_updated': -1
    }.items())
    limit=1
    result = client['upstox_strategy_db']['hvn_cache'].find(
    filter=filter,
    sort=sort,
    limit=limit
    )

    cached_entry = client.find(
    filter=filter,
    sort=sort,
    limit=limit
        )
    cached_entry = None
    for entry in result:
        cached_entry = entry


    hvn_current = None
    # print(f" HVN CACHE RETRIEVED ENTRY {cached_entry} for {instrument_key} ")
    #check for empty cache or not
    if cached_entry is None:
        isFirstTime = True
    if cached_entry and "last_updated" in cached_entry :
        return cached_entry["hvn"]
    else:
        hvn_current =  runVPOC_Calculation(db ,instrument_key, ltt, pocMinutes=15)

        if hvn_current is not None:
            # hvn_previous_cache = hvn_current
            #store to mongo db cache collection if needed hvncache and we retrieve it so that we dont need to recalculate again
            DataPersistor().db["hvn_cache"].update_one(
                {"instrumentKey": instrument_key},
                {
                    "$set": {
                        "hvn": hvn_current,
                        "last_updated": datetime.now()
                    }
                },
                upsert=True
            )
            return hvn_current


    #     # --- 2. PREVIOUS SESSION CHECK (Last 15 minutes of yesterday's close) ---
    #     start_prev, end_prev = get_previous_day_range()

    #     hvn_previous = _run_hvn_aggregation(
    #         db, instrument_key, start_prev, end_prev, "Previous Day Close"
    #     )
    #     hvn_previous_cache = hvn_previous

    #     if hvn_previous is not None:
    #         return hvn_previous

    # return hvn_previous_cache


# -----------------------------------------------------
# --- NEW: Paper Trading Engine ---
# -----------------------------------------------------

class PaperTradeManager:
    """
    Manages virtual positions, Stop Loss (SL), and Take Profit (TP) checks.
    """

    TP_PERCENT = 0.015
    DEFAULT_QTY = 1

    def __init__(self, persistor: DataPersistor):
        self.persistor = persistor
        self.positions = {}         # Dictionary to hold current open positions
        self.closed_trades = deque(maxlen=1000)
        # self.data_persistor = data_persistor # Store the instance

        # --- NEW: Position Recovery ---
        self.load_open_positions()
        #print(f"PaperTradeManager initialized. Virtual TP: {self.TP_PERCENT*100}% of entry.")



    def load_open_positions(self):
        """
        Attempts to load previously open positions from the DataPersistor
        if the database connection is available.
        NOTE: This requires a method like self.data_persistor.get_unclosed_trades()
              to be implemented in your DataPersistor class.
        """

        if self.persistor is not None and self.persistor.db is not None:
            try:
                # Assuming you implement a method in DataPersistor that queries
                # the signal collection for trades with an 'ENTRY' but no matching 'EXIT'.
                # Placeholder call:
                if hasattr(self.persistor, 'get_unclosed_trades'):
                    open_trades_list = self.persistor.get_unclosed_trades() # User must implement this
                    # #print(open_trades_list)
                    for trade_record in open_trades_list:
                        # #print(trade_record)
                        # return '':
                        instrument_key = trade_record.get('instrumentKey')
                        if instrument_key:
                             # Reconstruct the position dictionary using the recovered data
                            self.positions[instrument_key] = {
                                'trade_id': trade_record.get('trade_id'),
                                'position': trade_record.get('position_after', 'FLAT'),
                                'entry_time': trade_record.get('timestamp', time.time()),
                                'entry_price': trade_record.get('ltp'),
                                'sl_price': trade_record.get('sl_price'),
                                'tp_price': trade_record.get('tp_price'),
                                'hvn_price': trade_record.get('hvn'),
                                'quantity': trade_record.get('quantity', 50),
                                'signal_reason': trade_record.get('reason', 'RESTART_RECOVERY')
                            }
                            #print(f"🔄 RECOVERY: Loaded open {self.positions[instrument_key]['position']} position for {instrument_key}")
                    return

            except Exception as e:
                print(f"⚠️ WARNING: Failed to load open positions from DB: {e}")

        print("INFO: DataPersistor not available or position recovery skipped. Starting with no open positions.")
    async def shutdown(self):
        """Placeholder for clean shutdown if needed."""
        # Note: Position cleanup is handled in the main finally block
        pass

    def place_order(self,  direction: str,ltt, key: str, entry_price: float, hvn_price: float, sl_price: float, signal_reason: str):
        """
        Places a new virtual order, handling reversals by closing the opposite position first.
        'entry_price' is now the realistic Best Bid/Ask price passed from StrategyEngine.
        """
        # Note: Imports like time and uuid must be available at the top of the file.

        current_pos_data = self.positions.get(key, {})
        current_pos_direction = current_pos_data.get('position', 'FLAT')

        # --- Check for Reversal Condition ---
        is_reversal = (direction == 'BUY' and current_pos_direction == 'SELL') or \
                      (direction == 'SELL' and current_pos_direction == 'BUY')

        if is_reversal:
            # 1. Exit the current opposite position at the current market price (entry_price)
            self.close_trade_for_reversal(key, ltt ,entry_price, 'Reversal Signal')

        # 2. Open the new position (Reverse or new entry)
        if current_pos_direction == 'FLAT' or is_reversal:
            # Calculate Take Profit (TP) based on your chosen R:R ratio (1.5 used as example)
            RR_RATIO = 1.5
            risk = abs(entry_price - sl_price)
            tp_price = 0.0

            if direction == 'BUY':
                tp_price = entry_price + (risk * RR_RATIO)
            elif direction == 'SELL':
                tp_price = entry_price - (risk * RR_RATIO)

            trade_id = str(uuid.uuid4())
            tp_price = round(tp_price, 2)

            # Store the new trade
            self.positions[key] = {
                'trade_id': trade_id,
                'position': direction,
                'entry_time': ltt,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'tp_price': tp_price, # New TP price
                'hvn_price': hvn_price,
                'quantity': 50, # Example quantity
                'signal_reason': signal_reason
            }

            # --- CORRECTED LOGGING CALL (ENTRY) ---
            # All required positional arguments are now passed from the local variables.
            self._log_signal(
                ltt=int(int(ltt)),
                signal='ENTRY',
                key=key,
                ltp=entry_price,
                hvn=hvn_price,
                new_pos=direction,
                reason=signal_reason,
                sl_price=sl_price,
                tp_price=tp_price,
                trade_id=trade_id,
                quantity=self.positions[key]['quantity'] # <--- MODIFIED: Added quantity
            )
            #print(f"✅ ENTRY: {key} {direction} at {entry_price:.2f} (SL: {sl_price:.2f}, TP: {tp_price:.2f}) - Reason: {signal_reason}")
        # else:
            #print(f"DEBUG: {key} Skipping {direction} signal because current position is already {current_pos_direction}.")


    def _close_position(self,  key,ltt, exit_price, reason_code, trade_id):
            """Simulates closing a position."""
            pos = self.positions.pop(key)

            pnl = 0.0

            entry_p = float(pos['entry_price'])
            exit_p = float(exit_price)
            qty = float(pos['quantity'])

            if pos['position'] == 'LONG' or pos['position'] == 'BUY':
                pnl = (exit_p - entry_p) * qty
            else: # SHORT
                pnl = (entry_p - exit_p) * qty

            self._log_square_off(key, ltt,exit_price, pos, pnl, reason_code, trade_id)

            return pnl

    def close_trade_for_reversal(self, key: str, ltt, exit_price: float, reason: str):
        """Closes the existing position and calculates P&L when a reversal signal occurs."""
        # Note: Imports like time and uuid must be available at the top of the file.

        current_pos = self.positions.pop(key, None)

        if current_pos is None:
            return  # Nothing to close

        direction = current_pos['position']
        entry_price = current_pos['entry_price']

        pnl_points = 0.0

        if direction == 'BUY':
            pnl_points = exit_price - entry_price
        elif direction == 'SELL':
            pnl_points = entry_price - exit_price

        # Calculate P&L in currency
        quantity = current_pos.get('quantity', 50)
        pnl_amount = pnl_points * quantity

        # Finalize the trade record
        current_pos['exit_time'] = ltt
        current_pos['exit_price'] = exit_price
        current_pos['exit_reason'] = reason
        current_pos['pnl_points'] = round(pnl_points, 2)
        current_pos['pnl_amount'] = round(pnl_amount, 2)
        current_pos['status'] = 'CLOSED'

        self.closed_trades.append(current_pos)

        # --- NEW CORRECTED LOGGING CALL (EXIT) ---
        self._log_square_off(
            key=key,
            ltt=ltt,
            exit_price=exit_price,
            closed_pos=current_pos, # This passes all entry details
            pnl=pnl_amount,
            reason_code=reason,
            trade_id=current_pos['trade_id']
        )
        # --- END NEW LOGGING CALL ---

        #print(f"🔄 REVERSAL EXIT: {key} Closed {direction} at {exit_price:.2f}. P&L: {pnl_amount:.2f}")

    def _log_signal(self, ltt,signal: str, key: str, ltp: float, hvn: float, new_pos: str, reason: str, sl_price: float, tp_price: float, trade_id, quantity: int): # <--- MODIFIED: Added quantity
        """Helper function for consistent entry signal logging and persistence."""
        log_entry = {
            'timestamp': ltt,
            'signal': signal,
            'instrumentKey': key,
            'trade_id': trade_id,
            'ltp': ltp,
            'hvn': hvn, # <--- MODIFIED: Changed from hvn_anchor to hvn
            'position_after': new_pos,
            'reason': reason,
            'sl_price': sl_price, # <--- MODIFIED: Changed from stop_loss_price to sl_price
            'tp_price': tp_price, # <--- MODIFIED: Changed from take_profit_price to tp_price
            'quantity': quantity, # <--- ADDED QUANTITY
            'strategy': 'OBI_HVN',
            'type': 'ENTRY'
        }
        self.persistor.log_signal(log_entry)

        #print("\n========================================================")
        #print(f"!!! VIRTUAL ENTRY: {signal} (LOGGED to MongoDB) !!!")
        #print(f"INSTRUMENT: {key}")
        #print(f"LTP: {ltp:.2f} | HVN Anchor: {hvn:.2f}")
        #print(f"SL: {sl_price:.2f} | TP: {tp_price:.2f}")
        #print(f"QTY: {quantity}") # <--- ADDED QTY TO PRINT
        #print(f"NEW POSITION: {new_pos}")
        #print(f"REASON: {reason}")
        #print(f"TIME: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        #print("========================================================\n")

    def _log_square_off(self, key,ltt, exit_price, closed_pos, pnl, reason_code, trade_id):
        """Helper function for consistent square-off logging and persistence."""
        log_entry = {
            'timestamp': ltt,
            'signal': 'SQUARE_OFF',
            'instrumentKey': key,
            'trade_id': trade_id,
            'exit_price': exit_price,
            'entry_price': closed_pos['entry_price'],
            'position_closed': closed_pos['position'],
            'quantity': closed_pos.get('quantity', 50), # <--- ADDED QUANTITY
            'sl_price': closed_pos['sl_price'], # <--- ADDED SL PRICE
            'tp_price': closed_pos['tp_price'], # <--- ADDED TP PRICE
            'hvn': closed_pos.get('hvn_price'), # <--- ADDED HVN
            'pnl': round(pnl, 4),
            'reason_code': reason_code,
            'strategy': 'OBI_HVN',
            'type': 'EXIT'
        }
        self.persistor.log_signal(log_entry)

        #print("\n--- VIRTUAL SQUARE OFF ---")
        #print(f"INSTRUMENT: {key}")
        #print(f"EXIT PRICE: {exit_price:.2f} | REASON: {reason_code}")
        #print(f"P&L: {pnl:.2f} (Position: {closed_pos['position']})")
        #print(f"TIME: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        #print("--------------------------\n")

        # --- MODIFIED FUNCTION SIGNATURE ---
    def check_positions(self, key: str,ltt, ltp: float, bid: float, ask: float):
        """Checks if the current Bid/Ask triggers SL or TP for an active position."""
        if key not in self.positions:
            return

        pos = self.positions[key]


        # Check if we have valid bid/ask data for accurate execution
        if bid is None or ask is None:
            # If order book data is missing, fall back to LTP for a less precise check
            price_for_long_sl = ltp
            price_for_short_sl = ltp
            price_for_long_tp = ltp
            price_for_short_tp = ltp
        else:
            # --- CRITICAL FIX: Use Bid/Ask for Real Market Checks ---
            price_for_long_sl = bid
            price_for_short_sl = ask
            price_for_long_tp = ask
            price_for_short_tp = bid

        pos_sl = pos.get('sl_price', 0.0)
        pos_tp = pos.get('tp_price', 0.0)

        reason_code = None

        if pos['position'] == 'LONG' or  pos['position'] == 'BUY':
            # Check SL: Price (Bid) falls to or below SL
            if price_for_long_sl <= pos_sl:
                reason_code = 'SL_HIT'
                exit_price = pos_sl # Use SL price for fill if triggered
            # Check TP: Price (Ask) rises to or above TP
            elif price_for_long_tp >= pos_tp:
                reason_code = 'TP_HIT'
                exit_price = pos_tp # Use TP price for fill if triggered

        elif pos['position'] == 'SHORT' or  pos['position'] == 'SELL':
            # Check SL: Price (Ask) rises to or above SL
            if price_for_short_sl >= pos_sl:
                reason_code = 'SL_HIT'
                exit_price = pos_sl # Use SL price for fill if triggered
            # Check TP: Price (Bid) falls to or below TP
            elif price_for_short_tp <= pos_tp:
                reason_code = 'TP_HIT'
                exit_price = pos_tp # Use TP price for fill if triggered

        if reason_code:
            # Use the LTP if bid/ask was not available, otherwise use the exit price determined above
            final_exit_price = exit_price if 'exit_price' in locals() else ltp
            self._close_position(key,ltt, final_exit_price, reason_code, pos['trade_id'])

    # def check_positions(self, key: str, ltp: float):
    #     """Checks if the current LTP triggers SL or TP for an active position."""
    #     if key not in self.positions:
    #         return

    #     pos = self.positions[key]
    #     if pos :
    #         sl_price = float(pos['sl_price'])
    #         tp_price = float(pos['tp_price'])
    #         postion = pos['position']
    #         #print(" POSITION ")
    #         #print(f"{postion}::LTP {ltp} :: SL={sl_price}  :: TP= {tp_price}")
    #         ##print(pos)
    #         # {'trade_id': '4f71d8b2-abc3-46fa-aeb9-36a953ad4834',
    #         #  'position': 'BUY', 'entry_time': 1764918497.119413,
    #         #  'entry_price': 813.95, 'sl_price': 739.65,
    #         #  'tp_price': 1074.0,
    #         #  'hvn_price': 739.85,
    #         #  'quantity': 50,
    #         #  'signal_reason':
    #         #    'OBI: 2.81 (Exec at Ask)'}
    #         reason_code = None
    #         if postion== 'BUY':
    #             # Check SL: LTP falls to or below SL
    #             if ltp <= sl_price:    # <-- CORRECTED: Was 'stop_loss'
    #                 reason_code = 'SL_HIT'
    #             # Check TP: LTP rises to or above TP
    #             elif ltp >= tp_price:  # <-- CORRECTED: Was 'take_profit'
    #                 reason_code = 'TP_HIT'

    #         elif postion == 'SELL':
    #             # Check SL: LTP rises to or above SL
    #             if ltp >= sl_price:    # <-- CORRECTED: Was 'stop_loss'
    #                 reason_code = 'SL_HIT'
    #             # Check TP: LTP falls to or below TP
    #             elif ltp <= tp_price:  # <-- CORRECTED: Was 'take_profit'
    #                 reason_code = 'TP_HIT'

    #         if reason_code:
    #             #print("CLOSE POSTION ")
    #             # This call is still broken, see Flaw B below
    #             self._close_position(key, ltp, reason_code, self.positions[key]['trade_id'])

# -----------------------------------------------------
# --- End Paper Trading Engine ---
# -----------------------------------------------------

# Import the instrument key extractor function


# Import the compiled Protobuf definitions
try:
    import MarketDataFeedV3_pb2 as pb
except ImportError:
    #print("Error: MarketDataFeedV3_pb2.py not found. Please ensure it's in the same directory.", file=sys.stderr)
    sys.exit(1)


import os

# --- Configuration ---
# ACCESS_TOKEN imported from config.py

INSTRUMENTS_FILE_PATH = 'nse.json.gz'
# Use "full" mode to receive L5 Order Book data necessary for OBI Strategy
SUBSCRIPTION_MODE = "full"
WSS_GUID = f"my_session_{int(time.time())}" # Unique ID for the session


# --- Trading Strategy Engine (UPDATED) ---

class StrategyEngine:
    """
    Implements advanced strategies: Order Book Imbalance (OBI) and HVN Stop Loss.
    """
    # Strategy 1: OBI Constants
    OBI_LOWER_THRESHOLD = 0.60
    OBI_UPPER_THRESHOLD = 1.50
    HVN_SL_BUFFER = 0.20
    MIN_SL_DISTANCE = 0.50

    # ⭐ NEW EV FILTER: Require a minimum trade size to confirm the signal conviction
    MIN_TRADE_QUANTITY = 5 # Example: Only act if LTQ is 5 or more

    # CRITICAL CHANGE 1: Accept the Trade Manager instance
    def __init__(self, persistor: DataPersistor, trade_manager: PaperTradeManager):
        self.state = {}
        self.persistor = persistor
        self.trade_manager = trade_manager
        #print(f"Strategy initialized: Strategy 1 (OBI) is active. Thresholds: Buy >{self.OBI_UPPER_THRESHOLD}, Sell <{self.OBI_LOWER_THRESHOLD}")
        #print(f"⭐ EV Filter Active: Requires Min LTQ of {self.MIN_TRADE_QUANTITY} to fire signal.")

    def _get_oi_support_resistance(self, instrument_key):
        """
        Analyzes the latest option chain data from MongoDB to find support and resistance levels.
        """
        if self.persistor.db is None:
            return None, None

        try:
            latest_oc = self.persistor.db["option_chain"].find_one(
                {"instrument_key": instrument_key},
                sort=[("timestamp", -1)]
            )
            if not latest_oc:
                return None, None

            df = pd.DataFrame(latest_oc['options_chain'])
            support = df.loc[df['pe_open_interest'].idxmax()]['strike_price']
            resistance = df.loc[df['ce_open_interest'].idxmax()]['strike_price']
            return support, resistance
        except Exception as e:
            #print(f"Error analyzing option chain data: {e}", file=sys.stderr)
            return None, None

    def _calculate_order_book_imbalance(self, market_ff: dict) -> float | None:
        """
        Calculates the OBI ratio (Total Buy Qty / Total Sell Qty)
        using 'tbq' (Total Bid Quantity) and 'tsq' (Total Sell Quantity).
        """
        try:
            buy_quantity_total = market_ff.get('tbq', 0)
            sell_quantity_total = market_ff.get('tsq', 0)

            if sell_quantity_total > 0:
                return buy_quantity_total / sell_quantity_total
            elif buy_quantity_total > 0:
                return float('inf')
            else:
                return None

        except Exception as e:
            return None

    def _determine_hvn(self, tick_data: dict) -> float | None:
        """Calculates the HVN."""
        instrument_key = tick_data.get('instrumentKey')
        full_feed = tick_data.get('fullFeed', {})
        ltp_fallback = full_feed.get('marketFF', {}).get('ltpc', {}).get('ltp')
        ltt = full_feed.get('marketFF', {}).get('ltpc', {}).get('ltt')

        db = self.persistor.db
        hvn = calculate_hvn(db, instrument_key,int(ltt))

        if hvn is not None:
            return hvn
        return ltp_fallback


    # ⭐ CRITICAL CHANGE: Added ltq as a parameter for filtering
    def strategy_one_obi(self, key: str, tick_data: dict, ltp: float, ltq: int):
        """
        Strategy 1: Order Book Imbalance (OBI) with HVN Stop Loss.
        Checks for entry signals and delegates position management to the Trade Manager.
        """

        # ⭐ NEW VOLUME FILTER: Check minimum traded quantity for signal conviction
        if ltq < self.MIN_TRADE_QUANTITY:
            # Skip signal generation if the traded quantity is too low, improving EV
            # #print(f"DEBUG STRATEGY FILTER: {key} skipped. LTQ ({ltq}) is below min threshold ({self.MIN_TRADE_QUANTITY}).")
            return

        current_pos = self.trade_manager.positions.get(key, {}).get('position', 'FLAT')

        market_ff = tick_data.get('fullFeed', {}).get('marketFF', {})
        obi_ratio = self._calculate_order_book_imbalance(market_ff)
        hvn_price = self._determine_hvn(tick_data)

        # --- Filter Logging ---
        is_obi_missing = obi_ratio is None
        is_hvn_missing = hvn_price is None or hvn_price == 0.0

        if is_obi_missing or is_hvn_missing:
            print(f"DEBUG STRATEGY FILTER: {key} skipped.", end=' ')
            if is_obi_missing:
                print("Missing OBI ratio.", end=' ')
            if is_hvn_missing:
                print("Missing HVN price.", end=' ')
            print()
            return
        # --- End Filter Logging ---


# --- NEW: Extract Best Bid and Offer Prices for Realistic Execution (BASED ON JSON STRUCTURE) ---
        # The JSON structure shows bidAskQuote is under marketLevel
        market_ff = tick_data.get('fullFeed', {}).get('marketFF', {})
        bid_ask_quote = market_ff.get('marketLevel', {}).get('bidAskQuote', [{}])
        ltt = tick_data.get('fullFeed', {}).get('marketFF', {}).get('ltpc', {}).get('ltt', 0)
        if ltt == 0:
            print(f"DEBUG STRATEGY: {key} missing LTT, cannot proceed." )
            print(tick_data)
            return
        ltt = int(int(ltt)/1000.0)

        # Safely get the best Ask (Offer) price from the first level. Use LTP as fallback.
        best_ask_price = bid_ask_quote[0].get('askP', ltp)
        # Safely get the best Bid price from the first level. Use LTP as fallback.
        best_bid_price = bid_ask_quote[0].get('bidP', ltp)

        # Define a slippage tolerance (e.g., 0.50 points)
        SLIPPAGE_TOLERANCE = 0.50

        #print(f"DEBUG STRATEGY ENTRY: {key} LTP={ltp:.2f}, OBI={obi_ratio:.3f}, HVN={hvn_price:.2f}, LTQ={ltq}, LTT={ltt}")

        # 1. Check for Entry Signal (Execution)
        support, resistance = self._get_oi_support_resistance(key)

        # LONG Entry Trigger: Strong Buy Imbalance (Ratio > 1.10)
        if obi_ratio > self.OBI_UPPER_THRESHOLD and ( current_pos != 'LONG' or current_pos != 'BUY'):
            if resistance and ltp > resistance:
                #print(f"DEBUG STRATEGY: {key} BUY signal skipped. LTP ({ltp}) is above resistance ({resistance}).")
                return

            # Set SL anchored below the HVN (support)
            sl_price = hvn_price - self.HVN_SL_BUFFER


            # SL Distance Check
            if (ltp - sl_price) < self.MIN_SL_DISTANCE:
                #print(f"DEBUG STRATEGY: {key} BUY signal skipped. SL distance ({ltp - sl_price:.2f}) is too small (<{self.MIN_SL_DISTANCE}).")
                return

            # Set the realistic entry price to the Best Ask Price
            entry_price_used = best_ask_price
            # Price Filter: Skip if Best Ask has moved too far above the trigger LTP (Slippage Check)
            if (entry_price_used - ltp) > SLIPPAGE_TOLERANCE:
                #print(f"DEBUG: {key} BUY skipped (Ask too high). Ask: {entry_price_used:.2f}, Trigger LTP: {ltp:.2f}. Slippage > {SLIPPAGE_TOLERANCE}")
                return # Skip trade
             # Execute the trade using the Best Ask as the realistic entry price
            self.trade_manager.place_order('BUY',ltt, key, entry_price_used, hvn_price, sl_price, f"OBI: {obi_ratio:.2f} (Exec at Ask)")
        # SHORT Entry Trigger: Strong Sell Imbalance (Ratio < 0.90)
        elif obi_ratio < self.OBI_LOWER_THRESHOLD and current_pos != 'SELL':
            if support and ltp < support:
                #print(f"DEBUG STRATEGY: {key} SELL signal skipped. LTP ({ltp}) is below support ({support}).")
                return

            # Set SL anchored above the HVN (resistance)
            sl_price = hvn_price + self.HVN_SL_BUFFER

            # SL Distance Check
            if (sl_price - ltp) < self.MIN_SL_DISTANCE:
                #print(f"DEBUG STRATEGY: {key} SELL signal skipped. SL distance ({sl_price - ltp:.2f}) is too small (<{self.MIN_SL_DISTANCE}).")
                return
            # Set the realistic entry price to the Best Bid Price
            entry_price_used = best_bid_price

            # Price Filter: Skip if Best Bid has moved too far below the trigger LTP (Slippage Check)
            if (ltp - entry_price_used) > SLIPPAGE_TOLERANCE:
                #print(f"DEBUG: {key} SELL skipped (Bid too low). Bid: {entry_price_used:.2f}, Trigger LTP: {ltp:.2f}. Slippage > {SLIPPAGE_TOLERANCE}")
                return # Skip trade

            # Execute the trade using the Best Bid as the realistic entry price
            self.trade_manager.place_order('SELL',ltt, key, entry_price_used, hvn_price, sl_price, f"OBI: {obi_ratio:.2f} (Exec at Bid)")
        # else:
        #     #print(f"DEBUG STRATEGY: {key} OBI ({obi_ratio:.3f}) is within the deadband. No action.")


        # 2. Check for Exit Signal
        self.trade_manager.check_positions(key,ltt, ltp, best_bid_price, best_ask_price)

    # ⭐ CRITICAL CHANGE: Added ltq as a parameter
    def process_tick(self, tick_data: dict, ltq: int):
        """
        Receives an INDIVIDUAL decoded Protobuf tick (feed item) and routes it to the active strategy.
        """
        instrument_key = tick_data.get('instrumentKey')

        full_feed = tick_data.get('fullFeed', {})
        ltp = full_feed.get('marketFF', {}).get('ltpc', {}).get('ltp')

        # ltp = full_feed.get('marketFF', {}).get('ltpc', {}).get('ltp')
        ltt = full_feed.get('marketFF', {}).get('ltpc', {}).get('ltt')
        ltt = int(int(ltt)/1000.0)

        if not instrument_key or ltp is None:
            return
        bid_ask_quote = full_feed.get('marketFF', {}).get('marketLevel', {}).get('bidAskQuote', [{}])

        # Safely get the best Ask (Offer) price from the first level. Use LTP as fallback.
        best_ask_price = bid_ask_quote[0].get('askP', ltp)
        # Safely get the best Bid price from the first level. Use LTP as fallback.
        best_bid_price = bid_ask_quote[0].get('bidP', ltp)

        # Check for open positions and attempt to close them (SL/TP check)
        # --- FIX: Pass bid and ask prices ---
        self.trade_manager.check_positions(instrument_key,ltt, float(ltp), best_bid_price, best_ask_price) # <-- UPDATED CALL

        # Pass the ltq to the engine for the conviction filter
        self.strategy_one_obi(instrument_key, tick_data, ltp, ltq)

# --- WSS Client Functions (UPDATED) ---

def get_market_data_feed_authorize_v3(access_token: str) -> dict:
    """Step 1: Get the authorized WebSocket redirect URI."""
    #print("Step 1: Requesting WebSocket authorization URI...")
    if access_token == 'YOUR_ACTUAL_ACCESS_TOKEN':
        #print("CRITICAL ERROR: ACCESS_TOKEN placeholder is not set. Cannot authorize.", file=sys.stderr)
        sys.exit(1)

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    try:
        response = requests.get(url=url, headers=headers)
        response.raise_for_status()
        response_json = response.json()
        #print("Authorization successful.")
        return response_json
    except requests.exceptions.RequestException as e:
        #print(f"Error during authorization request: {e}", file=sys.stderr)
        sys.exit(1)


def decode_protobuf(buffer: bytes) -> pb.FeedResponse:
    """Decode the binary Protobuf message into a Python object."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response

# --- Global Constants for Reconnection ---
MAX_RECONNECT_ATTEMPTS = 10
BASE_RECONNECT_DELAY_SECONDS = 5.0


# ⭐ CRITICAL CHANGE: Rewriting the function with a proper reconnection loop
async def fetch_market_data( instrument_keys: list):
    """
    Connect to WebSocket, subscribe, and feed ticks to the StrategyEngine with
    robust reconnection and exponential backoff.
    """

    # 1. Initialize Core Components
    persistor = DataPersistor()

    # Start the option chain fetcher task
    asyncio.create_task(fetch_and_store_option_chain())

    trade_manager = PaperTradeManager(persistor=persistor)
    strategy_engine = StrategyEngine(persistor=persistor, trade_manager=trade_manager)

    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    keys_to_subscribe = instrument_keys
    if len(instrument_keys) > 200:
        #print(f"Limiting subscription to first 200 keys out of {len(instrument_keys)} found...")
        keys_to_subscribe = instrument_keys[:200]

    if not keys_to_subscribe:
        #print("No instrument keys found or available for subscription. Exiting.", file=sys.stderr)
        return

    # --- START RECONNECTION LOOP ---
    reconnect_attempts = 0
    while reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
        try:
            #print(f"Attempting WebSocket connection (Attempt {reconnect_attempts + 1})...")
                # 1. Get Authorization
            auth_response = get_market_data_feed_authorize_v3(ACCESS_TOKEN)

            # Extract WSS URI
            wss_uri = auth_response.get("data", {}).get("authorized_redirect_uri")

            if not wss_uri:
                #print("ERROR: Could not find 'authorized_redirect_uri' in auth response.", file=sys.stderr)
                sys.exit(1)
            async with websockets.connect(wss_uri, ssl=ssl_context) as websocket:
                # Reset attempts on successful connection
                reconnect_attempts = 0
                #print(f"\nConnection established. Subscribing to {len(keys_to_subscribe)} keys in '{SUBSCRIPTION_MODE}' mode...")

                await asyncio.sleep(1)

                # Send subscription request (re-send every time we connect)
                subscription_data = {
                    "guid": WSS_GUID,
                    "method": "sub",
                    "data": {
                        "mode": SUBSCRIPTION_MODE,
                        "instrumentKeys": keys_to_subscribe
                    }
                }
                binary_data = json.dumps(subscription_data).encode('utf-8')
                await websocket.send(binary_data)
                #print("Subscription request sent. Strategy is analyzing incoming ticks...")

                # --- INNER DATA RECEPTION LOOP ---
                while True:
                    # ORIGINAL PROBLEM LINE 664: message = await websocket.recv()
                    message = await websocket.recv()

                    if isinstance(message, bytes):
                        # Decode binary tick
                        decoded_data = decode_protobuf(message)
                        data_dict = MessageToDict(decoded_data)
                        feeds = data_dict.get('feeds', {})

                        if not feeds:
                            continue

                        for instrument_key, feed_data in feeds.items():
                            feed_data['instrumentKey'] = instrument_key

                            # 3. LOG RAW TICK DATA TO REAL MONGODB
                            persistor.log_tick(feed_data)

                            full_feed = feed_data.get('fullFeed', {})
                            ltpc_data = full_feed.get('marketFF', {}).get('ltpc', {})

                            ltp = ltpc_data.get('ltp')
                            # ⭐ CRITICAL CHANGE: Extract LTQ for the new EV filter
                            ltq = ltpc_data.get('ltq', 0)
                            ltt = ltpc_data.get('ltt', 0)
                            bid_ask_quote = full_feed.get('marketFF', {}).get('marketLevel', {}).get('bidAskQuote', [{}])

                            # Safely get the best Ask (Offer) price from the first level. Use LTP as fallback.
                            best_ask_price = bid_ask_quote[0].get('askP', ltp)
                            # Safely get the best Bid price from the first level. Use LTP as fallback.
                            best_bid_price = bid_ask_quote[0].get('bidP', ltp)

                            try:
                                # Ensure LTQ is an integer for the filter check
                                ltq = int(ltq)
                            except (ValueError, TypeError):
                                ltq = 0 # Default to 0 if parsing fails

                            if ltp is not None:
                                # Check active positions against the new LTP (SL/TP check)
                                ltt = int(int(ltt)/1000.0)
                                trade_manager.check_positions(instrument_key,ltt, float(ltp), best_bid_price ,best_ask_price)

                                # 4. Feed data to the Strategy Engine (for new signals)
                                # Pass LTQ to the engine for the conviction filter
                                strategy_engine.process_tick(feed_data, ltq)

                    else:
                        # Handle text messages (e.g., subscription confirmation, errors)
                        try:
                            status_json = json.loads(message)
                            #print("\n>>> RECEIVED STATUS/ERROR MESSAGE (JSON) <<<")
                            #print(json.dumps(status_json, indent=2))
                            #print("------------------------------------------\n")

                            if status_json.get("status") == "error":
                                print("FATAL ERROR: Subscription failed. Check the JSON above for details.")

                        except json.JSONDecodeError:
                            print(f"Received Unknown Text Message: {message}")

        # --- END OF INNER CONNECTION LOOP ---

        # 3. Handle Expected Connection Errors
        except (websockets.exceptions.ConnectionClosedError, ConnectionAbortedError) as e:
            reconnect_attempts += 1
            #print(f"\n[ERROR] WebSocket Connection Lost/Aborted: {e}")

            if reconnect_attempts < MAX_RECONNECT_ATTEMPTS:
                # Exponential backoff calculation: BASE * (2^attempts) + Jitter
                delay = BASE_RECONNECT_DELAY_SECONDS * (2 ** (reconnect_attempts - 1))
                jitter = random.uniform(0.5, 1.5)
                backoff_time = min(delay + jitter, 120.0)

                #print(f"Reconnecting in {backoff_time:.2f} seconds...")
                await asyncio.sleep(backoff_time)
            else:
                #print(f"❌ Failed to reconnect after {MAX_RECONNECT_ATTEMPTS} attempts. Shutting down.")
                break

        except websockets.exceptions.ConnectionClosedOK:
            #print("\nWebSocket connection closed gracefully.")
            break # Exit the reconnection loop

        except Exception as e:
            #print(f"\n[FATAL ERROR] An unexpected error occurred: {e}", file=sys.stderr)
            traceback.print_exc()
            break # Exit the reconnection loop

    # --- FINAL CLEANUP BLOCK (Runs after reconnection loop finishes) ---
    if 'persistor' in locals() and persistor.db is not None:
         #print("Flushing final tick buffer...")
         persistor._flush_ticks(force=True)
         generate_eod_html_report(persistor.db)

    # if 'trade_manager' in locals():
    #     if trade_manager.positions:
    #         #print(f"\n--- FINAL ACTIVE VIRTUAL POSITIONS ({len(trade_manager.positions)}) ---")
    #         for key, pos in trade_manager.positions.items():
    #             #print(f"  {key}: {pos['position']} @ {pos['entry_price']:.2f} | SL: {pos['sl_price']:.2f} | TP: {pos['tp_price']:.2f}") # Corrected print statement
    #         #print("---------------------------------------------------\n")
    #     # else:
    #     #     #print("\nNo active virtual positions remaining on shutdown.")

backtesting_mode = False
def main():
    """Main function to run the market data client."""
    import data_engine as de
    if backtesting_mode:
        print("Backtesting mode is enabled. Exiting real-time client.")
        return
    else:
        # 0. Load Instrument Keys
        all_keys = de.subscribed_instruments



        # 2. Define the list of items you want to add


        NiftyFO = ["NSE_FO|41910","NSE_FO|41913","NSE_FO|41914","NSE_FO|41915","NSE_FO|41916","NSE_FO|41917","NSE_FO|41918","NSE_FO|41921","NSE_FO|41922","NSE_FO|41923","NSE_FO|41924","NSE_FO|41925","NSE_FO|41926","NSE_FO|41927","NSE_FO|41928","NSE_FO|41935","NSE_FO|41936","NSE_FO|41939","NSE_FO|41940","NSE_FO|41943","NSE_FO|41944","NSE_FO|41945","NSE_FO|41946"]
        BN_FO =["NSE_FO|51414","NSE_FO|51415","NSE_FO|51416","NSE_FO|51417","NSE_FO|51420","NSE_FO|51421","NSE_FO|51439","NSE_FO|51440","NSE_FO|51460","NSE_FO|51461","NSE_FO|51475","NSE_FO|51476","NSE_FO|51493","NSE_FO|51498","NSE_FO|51499","NSE_FO|51500","NSE_FO|51501","NSE_FO|51502","NSE_FO|51507","NSE_FO|51510","NSE_FO|60166","NSE_FO|60167"]
        # 3. Use the update() method to add all elements from the list
        all_keys.update(NiftyFO)
        all_keys.update(BN_FO)
        de.subscribed_instruments.update(all_keys)

        if not all_keys:
            #print(f"Could not load instrument keys . Exiting.")
            sys.exit(1)



        # 2. Start WebSocket Client
        try:
            # Note: asyncio.run() handles KeyboardInterrupt, triggering the cleanup inside fetch_market_data
            asyncio.run(fetch_market_data(  list(all_keys)))
        except KeyboardInterrupt:
            print("\nClient terminated by user.")
        except Exception as e:
            print(f"An unexpected error occurred: {e}", file=sys.stderr)


# --- Reporting Function (Generates HTML File) ---
# (The entire reporting logic remains the same)
def generate_eod_html_report(db):
    """
    Generates an End-of-Day (EOD) PnL and trade summary report
    from the 'trade_signals' MongoDB collection for the current day and saves it as an HTML file.
    """
    if db is None:
        #print("\n[EOD REPORT] Cannot generate report: MongoDB connection is unavailable.")
        return

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    query = {
        "type": "EXIT",
        "timestamp": {"$gte": today.timestamp()}
    }

    try:
        exit_trades = list(db[SIGNAL_COLLECTION].find(query).sort("timestamp", 1))
    except Exception as e:
        #print(f"\n[EOD REPORT] Error querying trade signals: {e}")
        return

    total_trades = len(exit_trades)

    # --- P&L Calculation and Summary Generation ---
    total_pnl = 0.0
    winning_trades = 0
    losing_trades = 0
    trade_summary = {}
    trade_rows = ""
    summary_rows = ""
    today_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for trade in exit_trades:
        pnl = trade.get('pnl', 0.0)
        total_pnl += pnl

        if pnl > 0:
            winning_trades += 1
            pnl_class = 'trade-win'
        elif pnl < 0:
            losing_trades += 1
            pnl_class = 'trade-loss'
        else:
            pnl_class = ''

        key = trade.get('instrumentKey')

        # Build Trade Log Rows
        trade_time = datetime.fromtimestamp(trade.get('timestamp')).strftime('%H:%M:%S')
        trade_rows += f"""
        <tr>
            <td>{trade_time}</td>
            <td>{key}</td>
            <td>{trade.get('position_closed')}</td>
            <td>{trade.get('entry_price'):.2f}</td>
            <td>{trade.get('exit_price'):.2f}</td>
            <td>{trade.get('reason_code')}</td>
            <td class="{pnl_class}">{pnl:.2f}</td>
        </tr>
        """

        if key not in trade_summary:
            trade_summary[key] = []
        trade_summary[key].append(pnl)

    # Calculate Win Rate and determine color classes
    win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0.0
    pnl_sign = "+" if total_pnl >= 0 else ""
    pnl_color = 'pnl-positive' if total_pnl > 0 else ('pnl-negative' if total_pnl < 0 else 'pnl-neutral')
    win_rate_color = 'pnl-positive' if win_rate >= 50 else 'pnl-negative'

    # Build Instrument Summary Rows
    for key, pnls in trade_summary.items():
        net_key_pnl = sum(pnls)
        key_pnl_sign = "+" if net_key_pnl >= 0 else ""
        key_pnl_class = 'trade-win' if net_key_pnl > 0 else ('trade-loss' if net_key_pnl < 0 else '')
        summary_rows += f"""
        <tr>
            <td>{key}</td>
            <td>{len(pnls)}</td>
            <td class="{key_pnl_class}">{key_pnl_sign}{net_key_pnl:.2f}</td>
        </tr>
        """

    # --- HTML Template ---
    html_template = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Paper Trading EOD Report</title>
        <style>
            body {{ font-family: 'Arial', sans-serif; margin: 20px; background-color: #f4f7f6; }}
            .container {{ max-width: 1000px; margin: auto; background: #fff; padding: 25px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1); }}
            h2 {{ text-align: center; color: #1f3b64; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px; margin-bottom: 20px; }}
            .metric-box {{ display: flex; justify-content: space-around; margin-bottom: 20px; }}
            .metric {{ padding: 15px; border-radius: 8px; text-align: center; flex: 1; margin: 0 10px; }}
            .metric h3 {{ margin: 0; font-size: 1.2em; color: #555; }}
            .metric p {{ margin: 5px 0 0; font-size: 1.8em; font-weight: bold; }}
            .pnl-positive {{ background-color: #e6ffe6; color: #008000; border: 1px solid #008000; }}
            .pnl-negative {{ background-color: #ffe6e6; color: #cc0000; border: 1px solid #cc0000; }}
            .pnl-neutral {{ background-color: #f0f8ff; color: #333; border: 1px solid #aaa; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background-color: #1f3b64; color: white; }}
            tr:nth-child(even) {{ background-color: #f9f9f9; }}
            .trade-win {{ color: #008000; font-weight: bold; }}
            .trade-loss {{ color: #cc0000; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h2>📊 Paper Trading End-of-Day Report 📊</h2>
            <p style="text-align: center; color: #777;">Report Time: {today_str}</p>

            <div class="metric-box">
                <div class="metric pnl-neutral">
                    <h3>Total Trades</h3>
                    <p>{total_trades}</p>
                </div>
                <div class="metric {win_rate_color}">
                    <h3>Win Rate</h3>
                    <p>{win_rate:.2f}%</p>
                </div>
                <div class="metric {pnl_color}">
                    <h3>Net Paper P&L</h3>
                    <p>{pnl_sign}{total_pnl:.2f}</p>
                </div>
            </div>

            <h3>Trade Log</h3>
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Instrument</th>
                        <th>Position</th>
                        <th>Entry Price</th>
                        <th>Exit Price</th>
                        <th>Reason</th>
                        <th>P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {trade_rows if total_trades > 0 else '<tr><td colspan="7" style="text-align: center;">No completed trades to display.</td></tr>'}
                </tbody>
            </table>

            <h3>Summary by Instrument</h3>
            <table>
                <thead>
                    <tr>
                        <th>Instrument</th>
                        <th>Trades</th>
                        <th>Net P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {summary_rows if trade_summary else '<tr><td colspan="3" style="text-align: center;">No completed trades to display.</td></tr>'}
                </tbody>
            </table>
        </div>
    </body>
    </html>
    """

    # --- Save to File ---
    filename = f"ORDER_FLOW_eod_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    try:
        with open(filename, 'w', encoding="utf-8") as f:
            f.write(html_template)

        #print(f"\n========================================================")
        #print(f"✅ EOD HTML Report saved successfully to: {filename}")
        #print(f"========================================================")
    except Exception as e:
        #print(f"\n[EOD REPORT] Error saving HTML file: {e}")
        import traceback
        traceback.print_exc()

# --- End Reporting Function ---


if __name__ == "__main__":
    main()