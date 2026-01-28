import asyncio
import json
import ssl
import concurrent.futures
import websockets
import requests
from google.protobuf.json_format import MessageToDict
import sys
import time
from collections import deque
from datetime import datetime, timedelta
import uuid
import random
import traceback
import pandas as pd
import os
from concurrent.futures import ThreadPoolExecutor

# --- Dependencies & Configuration ---
# NOTE: The imports below are commented out or adjusted to ensure the backtester
# runs without needing external files like 'config.py' or 'option_chain_fetcher.py'.
# If you run this in a live environment, uncomment the necessary imports.

# try:
#     sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
#     from config import ACCESS_TOKEN
#     # from option_chain_fetcher import get_api_client, get_option_chain, store_option_chain_data
# except ImportError as e:
#     # Define a placeholder token for backtesting if config is missing
#     ACCESS_TOKEN = "BACKTESTING_ONLY_TOKEN"
#     pass

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# --- MongoDB Client Setup ---
try:
    from pymongo import MongoClient
    from pymongo.errors import BulkWriteError
except ImportError:
    print("Error: pymongo library not found. Please install it using 'pip install pymongo'", file=sys.stderr)
    sys.exit(1)

# --- MongoDB Configuration (REQUIRED) ---
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "upstox_strategy_db"
TICK_COLLECTION = "tick_data"
# NOTE: Trade signals will be logged to 'backtest_signals' collection.
SIGNAL_COLLECTION_BACKTEST = "backtest_signals"


# -----------------------------------------------------
# --- Data Persistence/Journaling Engine ---
# -----------------------------------------------------

class DataPersistor:
    """Manages connection and logging to MongoDB."""
    def __init__(self):
        self.client = None
        self.db = None
        self._connect_db()

    def _connect_db(self):
        """Initializes MongoDB connection."""
        try:
            self.client = MongoClient(MONGO_URI)
            self.db = self.client[MONGO_DB_NAME]
            # Verify connection by checking database status (optional, but good practice)
            self.db.command('ping')
        except Exception as e:
            print(f"MongoDB connection failed: {e}", file=sys.stderr)
            self.client = None
            self.db = None

    def log_signal(self, log_entry: dict):
        """Inserts a trade signal document into the backtest collection."""
        try:
            if self.db is None:
                return
            self.db[SIGNAL_COLLECTION_BACKTEST].insert_one(log_entry)
        except Exception as e:
            # print(f"MongoDB insertion error (backtest signal): {e}", file=sys.stderr)
            pass

    def clear_backtest_signals(self):
        """Clears the backtest signal collection before a new run."""
        if self.db is not None:
            self.db[SIGNAL_COLLECTION_BACKTEST].delete_many({})
            print(f"Cleared existing '{SIGNAL_COLLECTION_BACKTEST}' collection.")


# -----------------------------------------------------
# --- Paper Trading Engine (Single Position Per Key) ---
# -----------------------------------------------------

class PaperTradeManager:
    """
    Manages virtual positions (assumes one open position per instrument key),
    Stop Loss (SL), and Take Profit (TP) checks.
    """

    RR_RATIO = 1.5 # Fixed Risk-Reward ratio (Adjustable)
    DEFAULT_QTY = 50

    def __init__(self, persistor: DataPersistor):
        self.persistor = persistor
        # Structure: {'instrumentKey': {trade_data_dict}}
        self.positions = {}
        self.closed_trades = deque(maxlen=1000)
        print("NEW PaperTradeManager initialized.")

    def place_order(self, direction: str, ltt_ms: int, key: str, entry_price: float, hvn_price: float, sl_price: float, signal_reason: str):
        """Places a new virtual order, handling reversals by closing the opposite position first."""

        current_pos_data = self.positions.get(key)
        current_pos_direction = current_pos_data.get('position', 'FLAT') if current_pos_data else 'FLAT'

        # --- Check for Reversal Condition ---
        is_reversal = (direction == 'BUY' and current_pos_direction == 'SELL') or \
                      (direction == 'SELL' and current_pos_direction == 'BUY')

        if is_reversal:
            # Exit the current opposite position at the current market price (entry_price)
            # We close using a simplified signature, P&L is calculated inside close_trade.
            self.close_trade(key, ltt_ms ,entry_price, 'REVERSAL') # <--- FIXED CALL

        # 2. Open the new position (Reverse or new entry)
        if current_pos_direction == 'FLAT' or is_reversal:

            risk = abs(entry_price - sl_price)

            # --- Minimum Risk Check (Optional, but good practice) ---
            # if risk < 0.05:
            #     return

            # Calculate TP
            tp_price = 0.0
            if direction == 'BUY':
                tp_price = entry_price + (risk * self.RR_RATIO)
            elif direction == 'SELL':
                tp_price = entry_price - (risk * self.RR_RATIO)

            trade_id = str(uuid.uuid4())
            tp_price = round(tp_price, 2)

            # Store the new trade (Overwrites existing entry for this key)
            self.positions[key] = {
                'trade_id': trade_id,
                'position': direction,
                'entry_time': ltt_ms,
                'entry_price': entry_price,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'hvn_price': hvn_price,
                'quantity': self.DEFAULT_QTY,
                'signal_reason': signal_reason
            }

            self._log_signal(
                ltt_ms=ltt_ms,
                signal='ENTRY',
                key=key,
                ltp_price=entry_price,
                hvn=hvn_price,
                new_pos=direction,
                reason=signal_reason,
                sl_price=sl_price,
                tp_price=tp_price,
                trade_id=trade_id,
                quantity=self.DEFAULT_QTY
            )
            # --- DEBUGGING CONFIRMATION ---
            print(f"✅ ENTRY PLACED: {key} {direction} at {entry_price:.2f} (Risk: {risk:.4f}, SL: {sl_price:.2f}, TP: {tp_price:.2f}) - Reason: {signal_reason}")


    def _log_signal(self, ltt_ms, signal: str, key: str, ltp_price: float, hvn: float, new_pos: str, reason: str, sl_price: float, tp_price: float, trade_id, quantity: int):
        """Helper function for consistent entry signal logging and persistence."""
        log_entry = {
            'timestamp': ltt_ms / 1000.0, # Log in seconds
            'signal': signal,
            'instrumentKey': key,
            'trade_id': trade_id,
            'ltp': ltp_price,
            'hvn': hvn,
            'position_after': new_pos,
            'reason': reason,
            'sl_price': sl_price,
            'tp_price': tp_price,
            'quantity': quantity,
            'strategy': 'OBI_HVN_AUCTION_BAR',
            'type': 'ENTRY'
        }
        try:
            self.persistor.log_signal(log_entry)
        except Exception as e:
            print(f"[PERSISTENCE ERROR] Failed to log ENTRY signal for {key}: {e}")



    def _log_square_off(self, key, ltt_ms, exit_price, closed_pos, pnl, reason_code, trade_id):
        """Helper function for consistent square-off logging and persistence."""
        log_entry = {
            'timestamp': ltt_ms / 1000.0, # Log in seconds
            'signal': 'SQUARE_OFF',
            'instrumentKey': key,
            'trade_id': trade_id,
            'exit_price': exit_price,
            'entry_price': closed_pos['entry_price'],
            'position_closed': closed_pos['position'],
            'quantity': closed_pos.get('quantity', self.DEFAULT_QTY),
            'sl_price': closed_pos['sl_price'],
            'tp_price': closed_pos['tp_price'],
            'hvn': closed_pos.get('hvn_price'),
            'pnl': round(pnl, 4),
            'reason_code': reason_code,
            'strategy': 'OBI_HVN_AUCTION_BAR',
            'type': 'EXIT'
        }
        try:
            self.persistor.log_signal(log_entry)
        except Exception as e:
            print(f"[PERSISTENCE ERROR] Failed to log EXIT signal for {key}: {e}")

    def _calculate_pnl(self, position: str, entry_price: float, exit_price: float, quantity: int) -> float:
        """Calculates P&L for a closed position."""
        if position == 'BUY':
            return (exit_price - entry_price) * quantity
        elif position == 'SELL':
            return (entry_price - exit_price) * quantity
        return 0.0

    # --- CRITICAL FIX 1: check_positions (Single-Position, Intra-Bar, Type Error Fix) ---
    def check_positions(self, key, ltt_ms, close_price, current_bid, current_ask, high_price, low_price):
        """
        Checks the single open position against SL/TP criteria using
        INTRA-BAR (high/low) pricing.
        """
        if key not in self.positions:
            return

        pos = self.positions[key] # Position data dictionary

        # 🚨 FIX FOR TypeError: string indices must be integers, not 'str' 🚨
        # This resolves the type error by ensuring we are accessing the dictionary directly.
        if not isinstance(pos, dict):
            print(f"[CRITICAL ERROR] Position data for {key} is corrupted. Removing key.")
            self.positions.pop(key, None)
            return

        entry_p = pos.get('entry_price') # <--- FIX: Use 'pos'
        sl_p = pos.get('sl_price')       # <--- FIX: Use 'pos'
        tp_p = pos.get('tp_price')       # <--- FIX: Use 'pos'

        sl_hit = False
        tp_hit = False

        # --- 1. INTRA-BAR CHECK (Most Critical) ---
        if pos['position'] == 'BUY': # <--- FIX: Use 'pos'
            if low_price <= sl_p: sl_hit = True
            if high_price >= tp_p: tp_hit = True

        elif pos['position'] == 'SELL': # <--- FIX: Use 'pos'
            if high_price >= sl_p: sl_hit = True
            if low_price <= tp_p: tp_hit = True

        # --- 2. Determine Exit Price and Priority ---
        if sl_hit or tp_hit:
            reason = ""
            exit_price = 0.0

            if sl_hit and tp_hit:
                # CONSERVATIVE ASSUMPTION: Assume SL was hit first
                reason = "SL_HIT"
                exit_price = sl_p
            elif sl_hit:
                reason = "SL_HIT"
                exit_price = sl_p
            elif tp_hit:
                reason = "TP_HIT"
                exit_price = tp_p

            # Close the trade using the determined exit price and reason
            self.close_trade(key, ltt_ms, exit_price, reason)

    # --- CRITICAL FIX 2: Simplified close_trade (P&L calculation moved here) ---
    def close_trade(self, key, exit_time_ms, exit_price, reason_code):
        """
        Closes the single open trade for the given key. P&L is calculated internally.
        """
        if key not in self.positions:
            print(f"[ERROR] Attempted to close non-existent trade for {key}")
            return

        # Get the position data before popping
        closed_pos = self.positions.pop(key)
        trade_id = closed_pos['trade_id']

        # Calculate P&L using the determined exit price
        pnl = self._calculate_pnl(
            closed_pos['position'],
            closed_pos['entry_price'],
            exit_price,
            closed_pos['quantity']
        )

        closed_trade = {
            'instrumentKey': key,
            'trade_id': trade_id,
            'entry_time': closed_pos['entry_time'],
            'exit_time': exit_time_ms,
            'entry_price': closed_pos['entry_price'],
            'exit_price': exit_price,
            'pnl': pnl,
            'reason_code': reason_code
        }
        self.closed_trades.append(closed_trade)

        self._log_square_off(
            key, exit_time_ms, exit_price, closed_pos, pnl, reason_code, trade_id
        )

        print(f"[TRADE] {key} - EXIT {closed_pos['position']} @ {exit_price:.2f}. PnL: {pnl:.2f} ({reason_code})")


# -----------------------------------------------------
# --- Trading Strategy Engine (Simple Bar Rejection) ---
# -----------------------------------------------------

class SimpleBarRejectionStrategyEngine:
    """
    Implements the Simple Bar Rejection Strategy:
    A bar's extreme breaches the previous bar's extreme, and the close
    is in the top/bottom 50% of the bar's range, confirming the rejection.
    """

    # Strategy Constants (Adjustable)
    MIN_PRICE_DIFF = 1e-6     # Keep epsilon for robust floating point comparisons
    SL_BUFFER_PCT = 0.001     # 0.1% buffer for SL placement
    HVN_LOOKBACK_BARS = 2     # Need current bar and previous bar for the signal

    def __init__(self, persistor: DataPersistor, trade_manager: PaperTradeManager):
        self.persistor = persistor
        self.trade_manager = trade_manager
        self.bar_history = {}

    def _get_bar_history(self, key):
        """Initializes or retrieves the 5-min bar history deque."""
        if key not in self.bar_history:
            self.bar_history[key] = deque(maxlen=self.HVN_LOOKBACK_BARS)
        return self.bar_history[key]

    def _check_simple_rejection_long(self, current_bar: dict, history: deque) -> tuple[bool, float | None]:
        """
        Long Trigger: Bear Trap. Low takes out previous low, bar closes strong (top half).
        """
        if len(history) < 1: return False, None
        previous_bar = history[-1]

        # 1. TRAP: Current bar's low must breach the previous bar's low.
        trap_triggered = current_bar['low'] < (previous_bar['low'] - self.MIN_PRICE_DIFF)

        # 2. CONFIRMATION (Rejection): The bar must close in the top half of its range.
        bar_range = current_bar['high'] - current_bar['low']
        # Midpoint of the current bar
        midpoint = current_bar['low'] + (bar_range / 2.0)
        rejection_confirmed = current_bar['close'] > midpoint

        if trap_triggered and rejection_confirmed:
            # Stop Loss is the low of the trap bar (current bar low)
            sl_price = current_bar['low'] * (1 - self.SL_BUFFER_PCT)
            return True, sl_price

        return False, None

    def _check_simple_rejection_short(self, current_bar: dict, history: deque) -> tuple[bool, float | None]:
        """
        Short Trigger: Bull Trap. High takes out previous high, bar closes weak (bottom half).
        """
        if len(history) < 1: return False, None
        previous_bar = history[-1]

        # 1. TRAP: Current bar's high must breach the previous bar's high.
        trap_triggered = current_bar['high'] > (previous_bar['high'] + self.MIN_PRICE_DIFF)

        # 2. CONFIRMATION (Rejection): The bar must close in the bottom half of its range.
        bar_range = current_bar['high'] - current_bar['low']
        # Midpoint of the current bar
        midpoint = current_bar['low'] + (bar_range / 2.0)
        rejection_confirmed = current_bar['close'] < midpoint

        if trap_triggered and rejection_confirmed:
            # Stop Loss is the high of the trap bar (current bar high)
            sl_price = current_bar['high'] * (1 + self.SL_BUFFER_PCT)
            return True, sl_price

        return False, None

    def process_bar(self, bar_data: dict):
        """Receives an aggregated 5-minute bar and applies the strategy."""
        key = bar_data['key']
        ltt_ms = bar_data['ltt_ms']

        history = self._get_bar_history(key)
        # 1. Check for Exit Signal (SL/TP)
        # NOTE: This call is redundant if the check is done in the BacktestingEngine.run loop,
        # but it's kept here for strategy flexibility.
        self.trade_manager.check_positions(
            key, ltt_ms, bar_data['close'], bar_data['bid'], bar_data['ask'],
            bar_data['high'], bar_data['low']
        )

        # Check if history is sufficient for auction failure logic
        if len(history) < (self.HVN_LOOKBACK_BARS - 1):
            history.append(bar_data)
            return

        # 2. Check for Entry Signal
        long_trigger, long_sl_price = self._check_simple_rejection_long(bar_data, history)
        short_trigger, short_sl_price = self._check_simple_rejection_short(bar_data, history)

        if long_trigger:
            entry_price = bar_data['ask']
            if entry_price == 0.0:
                 entry_price = bar_data['close']
            self.trade_manager.place_order(
                'BUY', ltt_ms, key, entry_price, bar_data['hvn'], long_sl_price,
                f"REJECTION: Low takes out Prev Low, Close is strong"
            )


        if short_trigger:
            entry_price = bar_data['bid']
            if entry_price == 0.0:
                 entry_price = bar_data['close']
            self.trade_manager.place_order(
                'SELL', ltt_ms, key, entry_price, bar_data['hvn'], short_sl_price,
                f"REJECTION: High takes out Prev High, Close is weak"
            )

        # 3. Append the bar to history
        history.append(bar_data)


# -----------------------------------------------------
# --- Backtesting Engine ---
# -----------------------------------------------------

class BacktestingEngine:
    """
    Simulates trading by reading 5-minute aggregated bars from MongoDB.
    """
    def __init__(self, instrument_keys: list):
        self.persistor = DataPersistor()
        self.trade_manager = PaperTradeManager(persistor=self.persistor)
        self.strategy_engine = SimpleBarRejectionStrategyEngine(persistor=self.persistor, trade_manager=self.trade_manager)
        self.instrument_keys = instrument_keys
        self.final_bar_data = {} # Stores the last processed bar for EOD cleanup


    def _calculate_bar_vpoc(self, price_volume_pairs: list) -> float:
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


    def run(self, start_date: datetime, end_date: datetime):
        """Runs the backtest over the specified date range using aggregated 5-minute bars."""

        if self.persistor.db is None:
            print("CRITICAL: Cannot run backtest. MongoDB connection failed.")
            return

        self.persistor.clear_backtest_signals()
        print(f"\n--- Starting Bar-Based Backtest ({start_date.date()} to {end_date.date()}) ---")



        for key in self.instrument_keys:
            print(f"\nProcessing instrument: {key}")


            # Convert Python datetime objects to milliseconds for robust comparison in MongoDB
            start_ms = int(start_date.timestamp() * 1000)
            # Add 1 day to the end date timestamp for inclusive search
            end_ms = int((end_date + timedelta(days=1)).timestamp() * 1000)

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

            cursor = self.persistor.db[TICK_COLLECTION].aggregate(pipeline, allowDiskUse=True)


            # 2. Strategy Processing Loop (Bar-Based)
            bar_count = 0

            for bar_data in cursor:
                bar_count += 1

                timestamp_ms = bar_data.get('timestamp_ms')
                if timestamp_ms is None:
                    continue

                try:
                    vpoc_price = self._calculate_bar_vpoc(bar_data['price_volume_pairs'])

                    final_bid_data = bar_data.get('final_bid', 0.0)
                    final_ask_data = bar_data.get('final_ask', 0.0)

                    if isinstance(final_bid_data, list) and final_bid_data:
                        final_bid_data = final_bid_data[0]
                    elif not final_bid_data:
                        final_bid_data = 0.0

                    if isinstance(final_ask_data, list) and final_ask_data:
                        final_ask_data = final_ask_data[0]
                    elif not final_ask_data:
                        final_ask_data = 0.0

                    # 2b. Prepare bar for strategy
                    # The bar LTT is the bar_time + interval (300000ms = 5 minutes)
                    processed_bar = {
                        'key': bar_data['instrumentKey'],
                        'ltt_ms': timestamp_ms + 300000,

                        'close': float(bar_data.get('close', 0.0)),
                        'high': float(bar_data.get('high', 0.0)),
                        'low': float(bar_data.get('low', 0.0)),
                        'open': float(bar_data.get('open', 0.0)),
                        'volume': bar_data['volume'],
                        'hvn': vpoc_price,

                        'bid': float(final_bid_data),
                        'ask': float(final_ask_data)
                    }

                    # Store the last bar data for EOD cleanup
                    self.final_bar_data[processed_bar['key']] = processed_bar

                    # 3. Process the bar using the streamlined strategy
                    self.strategy_engine.process_bar(processed_bar)

                    # --- CRITICAL FIX: Intra-Bar Exit Check (Mandatory on every bar) ---
                    # The strategy engine already calls this, but redundant call here is fine.
                    # self.trade_manager.check_positions(
                    #     processed_bar['key'],
                    #     processed_bar['ltt_ms'],
                    #     processed_bar['close'],
                    #     processed_bar['bid'],
                    #     processed_bar['ask'],
                    #     processed_bar['high'],
                    #     processed_bar['low']
                    # )
                    # --- END CRITICAL FIX ---

                    if bar_count % 1000 == 0:
                        print(f"Processed {bar_count} bars... Active Positions: {len(self.trade_manager.positions)}")

                except Exception as e:
                    print(f"\n[CRITICAL BAR ERROR] Error processing bar {bar_count} for {bar_data.get('instrumentKey')}: {e}")
                    import traceback
                    traceback.print_exc()
                    pass

        print(f"\nBacktest finished. Total 5-min bars processed: {bar_count}")
        self._final_cleanup_and_report()
        self.generate_backtest_report()


    # --- CRITICAL FIX 3: Simplified EOD Cleanup ---
    def _final_cleanup_and_report(self):
        """
        Closes all remaining open trades at the final bar's price.
        """
        print("\nStarting final cleanup of open positions...")

        closed_count = 0

        # Iterate over a copy of the keys to safely modify the self.trade_manager.positions dictionary
        for inst_key in list(self.trade_manager.positions.keys()):

            # Use the final bar data stored for this specific instrument key
            final_bar = self.final_bar_data.get(inst_key)

            if not final_bar:
                # If we don't have the final price for this instrument, skip it
                print(f"[WARNING] Skipping EOD cleanup for {inst_key}: Final bar data not found.")
                continue

            final_ltt_ms = final_bar['ltt_ms']
            final_ltp = final_bar['close']

            # Since it's a single-position model, we just close the single entry
            self.trade_manager.close_trade(
                inst_key,
                final_ltt_ms,
                final_ltp,
                'EOD_CLOSE'
            )
            closed_count += 1

        print(f"Cleanup complete. Closed {closed_count} remaining open positions.")

    # Note: generate_backtest_report and _generate_eod_html_report remain the same


    def generate_backtest_report(self):
        """Generates a summary of the backtesting results and an HTML report."""
        if self.persistor.db is None:
            return

        exit_trades = list(self.persistor.db[SIGNAL_COLLECTION_BACKTEST].find({"type": "EXIT"}).sort("timestamp", 1))

        # Console Summary
        total_pnl = sum(t.get('pnl', 0.0) for t in exit_trades)
        winning_trades = sum(1 for t in exit_trades if t.get('pnl', 0.0) > 0)
        total_trades = len(exit_trades)
        win_rate = (winning_trades / total_trades) * 100 if total_trades > 0 else 0.0

        print("\n========================================================")
        print("          📈 OBI-HVN AUCTION FAILURE BACKTEST REPORT 📉  ")
        print("========================================================")
        print(f"Total Completed Trades: {total_trades}")
        print(f"Winning Trades: {winning_trades}")
        print(f"Losing Trades: {total_trades - winning_trades}")
        print(f"Win Rate: {win_rate:.2f}%")

        pnl_sign = "+" if total_pnl >= 0 else ""
        print(f"Net Paper P&L: {pnl_sign}{total_pnl:.2f}")
        print("========================================================")

        # Generate HTML report
        self._generate_eod_html_report(self.persistor.db)

    def _generate_eod_html_report(self, db):
        """
        Generates an EOD PnL and trade summary report from the 'backtest_signals' MongoDB collection.
        """
        SIGNAL_COLLECTION_FOR_REPORT = SIGNAL_COLLECTION_BACKTEST
        try:
            exit_trades = list(db[SIGNAL_COLLECTION_FOR_REPORT].aggregate([
                        {
                            '$lookup': {
                                'from': 'backtest_signals',
                                'let': {
                                    'trade_id_exit': '$trade_id'
                                },
                                'pipeline': [
                                    {
                                        '$match': {
                                            '$expr': {
                                                '$and': [
                                                    {
                                                        '$eq': [
                                                            '$trade_id', '$$trade_id_exit'
                                                        ]
                                                    }, {
                                                        '$eq': [
                                                            '$type', 'ENTRY'
                                                        ]
                                                    }
                                                ]
                                            }
                                        }
                                    }, {
                                        '$project': {
                                            'timestamp': 1,
                                            '_id': 0
                                        }
                                    }
                                ],
                                'as': 'entry_info'
                            }
                        }, {
                            '$unwind': '$entry_info'
                        }, {
                            '$match': {
                                'type': 'EXIT'
                            }
                        }, {
                            '$addFields': {
                                'entryTS': '$entry_info.timestamp'
                            }
                        }, {
                            '$project': {
                                'entry_info': 0
                            }
                        }, {
                            '$sort': {
                                'timestamp': 1
                            }
                        }
                    ]))
        except Exception as e:
            import traceback
            traceback.print_exc()
            return

        total_trades = len(exit_trades)
        total_pnl = 0.0
        winning_trades = 0
        losing_trades = 0
        trade_summary = {}
        trade_rows = ""
        summary_rows = ""
        today_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for trade in exit_trades:
            pnl = trade.get('pnl', 0.0)
            trade_ts_s = trade.get('timestamp')
            entryTS = trade.get('entryTS')
            if trade_ts_s is None: continue

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
            trade_time = datetime.fromtimestamp(trade_ts_s).strftime('%Y-%m-%d %H:%M:%S')
            entryTS_str = datetime.fromtimestamp(entryTS).strftime('%Y-%m-%d %H:%M:%S') if entryTS else "N/A"
            trade_rows += f"""
            <tr>
                <td>{entryTS_str} =>  {trade_time}</td>
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
            <title>OBI-HVN Backtest Report</title>
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
                <h2>📊 OBI-HVN Auction Failure Backtest Report 📊</h2>
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
        filename = f"OBI_HVN_AUCTION_BAR_backtest_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        try:
            with open(filename, 'w', encoding="utf-8") as f:
                f.write(html_template)

            print(f"✅ DETAILED HTML Report saved successfully to: {filename}")
        except Exception as e:
            print(f"[EOD REPORT] Error saving HTML file: {e}")
            traceback.print_exc()


# -----------------------------------------------------
# --- Main Execution Block ---
# -----------------------------------------------------
# import data_engine as de # Not used, commented out
def main():
    """Main function to run the backtester."""

    # --- CONFIGURATION: EDIT THIS SECTION ---
    # 1. List the instrument keys you have data for in your tick_data collection
    instrument_keys_to_test = [
        "NSE_EQ|INE522F01014",
        # Add other instrument keys here (e.g., "NSE_FO|NIFTY 25JAN2025 22000 CE")
    ]

    # These instrument lists are very long, using a short list for example:
    initial_instruments =[ "NSE_EQ|INE585B01010","NSE_EQ|INE139A01034"]
        # NiftyFO = ["NSE_FO|41910"]
        # BN_FO =["NSE_FO|51414"]

    instrument_keys_to_test = ["NSE_EQ|INE585B01010"]#initial_instruments

    # 2. Define the backtest period (must match dates in your MongoDB data)
    start_date = datetime(2025, 12, 9)
    end_date = datetime(2025, 12, 10)

    # --- END CONFIGURATION ---

    if not instrument_keys_to_test:
        print("Please specify a list of 'instrument_keys_to_test' to run the backtest.")
        sys.exit(1)

    print(f"Running Bar-Based Backtest for {len(instrument_keys_to_test)} instruments from {start_date.date()} to {end_date.date()}.")

    tester = BacktestingEngine(instrument_keys=instrument_keys_to_test)
    tester.run(start_date, end_date)


if __name__ == "__main__":
    main()