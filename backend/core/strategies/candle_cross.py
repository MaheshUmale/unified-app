import sys
import os
from pymongo import MongoClient
from typing import Dict, Any
# Helper function (place outside or inside the class)
from collections import deque
from typing import Deque

from db.mongodb import get_db, SIGNAL_COLLECTION_NAME

class DataPersistor:
    """Manages MongoDB connection and logging to the 'trade_signals' collection."""
    def __init__(self):
        self.db = get_db()
        if self.db is None:
             print("MongoDB connection failed in DataPersistor.", file=sys.stderr)
        else:
             print("DataPersistor initialized with MongoDB.")

    def log_signal(self, log_entry: Dict[str, Any]):
        """Inserts a trade signal document into the 'trade_signals' collection."""
        try:
            db = get_db()
            if db is not None:
                db[SIGNAL_COLLECTION_NAME].insert_one(log_entry)
        except Exception as e:
            print(f"MongoDB insertion error (trade signal): {e}", file=sys.stderr)



import sys
import time
import math
import uuid
from datetime import datetime, timedelta, time as dt_time
from collections import deque
from typing import Dict, Any, Deque, List, Optional

# Constants for persistence logging
RR_RATIO = 1.5
DEFAULT_QTY = 50
STRATEGY_NAME = 'CANDLE_CROSS_DYN_PIVOT' # Used as 'strategy' field in DB log

# --- A. MODIFIED TradingBase (Handles Exit Logging) ---

def _calculate_sma(data: Deque[float], length: int) -> Optional[float]:
    """Calculates Simple Moving Average (SMA)."""
    if len(data) < length:
        return None
    return sum(list(data)[-length:]) / length

class TradingBase:
    """Provides essential logging, position tracking, and DB persistence integration."""
    def __init__(self, instrument_key: str, csv_writer: Any, persistor: Optional[Any] = None, **kwargs):
        self.instrument_key = instrument_key
        self.csv_writer = csv_writer
        self.persistor = persistor # Data Persistor Instance
        self.position: Optional[Dict[str, Any]] = None
        self.stats = {"TRADES_TAKEN": 0, "PNL": 0.0}
        self.current_dt = datetime.now()
        self.current_ts_epoch = 0 # In seconds
        self.last_ltp = 0.0

    def log_event(self, ts: str, event_type: str, message: str):
        print(f"[{ts}] [{self.instrument_key}] {event_type}: {message}")

    def _calculate_pnl(self, position_side: str, entry_price: float, exit_price: float, quantity: int) -> float:
        """Calculates P&L (Points PnL)."""
        if position_side == 'LONG':
            return (exit_price - entry_price) * quantity
        elif position_side == 'SHORT':
            return (entry_price - exit_price) * quantity
        return 0.0

    def _close_position(self, ts: str, exit_price: float, reason: str):
        if self.position is None:
            return

        closed_pos = self.position.copy()
        side = closed_pos['side']
        quantity = closed_pos.get('quantity', DEFAULT_QTY)

        # 1. Calculate PnL (in points)
        pnl = self._calculate_pnl(side, closed_pos['price'], exit_price, quantity)
        self.stats["PNL"] += pnl

        # 2. Log SQUARE_OFF to DB (using user's requested structure)
        if self.persistor:
            # Map strategy position ('LONG'/'SHORT') to persistence position ('BUY'/'SELL' or similar)
            pos_closed_db = 'BUY' if side == 'LONG' else 'SELL'

            log_entry = {
                'timestamp': time.time() * 1000, # LTT in milliseconds
                'signal': 'SQUARE_OFF',
                'instrumentKey': self.instrument_key,
                'trade_id': closed_pos.get('trade_id', 'UNKNOWN'),
                'exit_price': exit_price,
                'entry_price': closed_pos['price'],
                'position_closed': pos_closed_db,
                'quantity': quantity,
                # These fields are expected to be set in self.position by CandleCrossStrategy
                'sl_price': closed_pos.get('stop_loss'),
                'tp_price': closed_pos.get('take_profit'),
                'hvn': closed_pos.get('dyn_pivot_value'), # Equivalent for 'hvn'
                'pnl': round(pnl, 4),
                'reason_code': reason,
                'strategy': STRATEGY_NAME,
                'type': 'EXIT'
            }
            self.persistor.log_signal(log_entry)

        # 3. Log to console
        self.log_event(ts, "TRADE_EXIT",
                       f"{side} closed at {closed_pos['price']:.2f} -> {exit_price:.2f}. PNL: {pnl:.2f}. Reason: {reason}")

        # 4. Reset position
        self.position = None


# --- B. CandleCrossStrategy (Contains process_tick and Entry Logging) ---

class CandleCrossStrategy(TradingBase):



    """
    1-Minute Candle Close Crossover Strategy with DB Persistence.
    """
    def __init__(self, instrument_key: str, csv_writer: Any,
                 ema_len: int=20, evwma_len: int=10,
                 force_len: int=50, pivot_len: int=10,
                 is_backtesting: bool=False,
                 persistor: Optional[Any] = None,
                 **kwargs):
        super().__init__(instrument_key, csv_writer, persistor, **kwargs)

        # Strategy Parameters
        self.ema_len = ema_len
        self.evwma_len = evwma_len
        self.force_len = force_len
        self.pivot_len = pivot_len
        self.is_backtesting = is_backtesting
        self.is_backtesting = is_backtesting # Ensure this is stored

        # Historical Data Storage for Indicators (Needed for backtesting lookback)
        self.closes_history: Deque[float] = deque(maxlen=max(ema_len, pivot_len))
        # ... (rest of indicator initialization remains the same) ...
        # NEW: History deque for backtesting indicator calculations
        self.closes_history: Deque[float] = deque(maxlen=max(ema_len, pivot_len) * 2)
        # Last calculated indicator values
        self.ema: Optional[float] = None
        self.evwma: Optional[float] = None
        self.dyn_pivot: Optional[float] = None

        # Mock VWAP State
        self.cum_vol = 0
        self.cum_pv = 0.0
        self.vwap: Optional[float] = None
        # Candle Aggregation State <-- FIX HERE
        self.current_minute_candle: Dict[str, Any] = {'minute': None, 'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}

        self.pending_long_entry: Optional[Dict[str, Any]] = None
        self.pivot_len = pivot_len # Ensure pivot_len is initialized
        self.is_backtesting = is_backtesting

        # State Initialization
        self.current_minute_candle: Dict[str, Any] = {'minute': None, 'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.pending_long_entry: Optional[Dict[str, Any]] = None

        # NEW: History deque for backtesting indicator calculations
        self.closes_history: Deque[float] = deque(maxlen=max(ema_len, pivot_len) * 2)


        # ... (rest of indicator initializations) ...
        self.ema_len = ema_len
        self.pivot_len = pivot_len # Ensure pivot_len is initialized
        self.is_backtesting = is_backtesting

        # State Initialization
        self.current_minute_candle: Dict[str, Any] = {'minute': None, 'open': None, 'high': None, 'low': None, 'close': None, 'volume': 0}
        self.pending_long_entry: Optional[Dict[str, Any]] = None

        # NEW: History deque for backtesting indicator calculations
        self.closes_history: Deque[float] = deque(maxlen=max(ema_len, pivot_len) * 2)
    # ... (Utility and Indicator Calculation methods omitted for brevity) ...




# Inside CandleCrossStrategy class:

    def _calculate_all_indicators(self, closed_candle_close: float) -> bool:
        """
        Calculates all required indicators based on the current history.
        NOTE: This implementation mocks the Dynamic Pivot with a Simple Moving Average (SMA)
        based on `self.pivot_len` to ensure signals can fire during backtesting.
        """

        # 1. Calculate Dynamic Pivot (Mocked with SMA)
        # Assuming you store closes in self.closes_history (initialized in __init__)
        self.dyn_pivot = _calculate_sma(self.closes_history, self.pivot_len)

        # 2. Calculate EMA (Mocked)
        self.ema = _calculate_sma(self.closes_history, self.ema_len)

        # Ensure we have enough data for the main pivot
        if self.dyn_pivot is None:
            return False
        return True
    def _monitor_pending_entry(self, ltp: float, ts_game: str):
        """Checks if a pending order should be executed on the current tick/LTP."""
        if self.position is not None or self.pending_long_entry is None:
            return

        entry_params = self.pending_long_entry

        # 1. Check for LONG entry trigger
        if ltp >= entry_params['entry_price']:
            self.log_event(ts_game, "TRADE_ENTRY", f"LONG at {entry_params['entry_price']:.2f} (Triggered)")

            # --- Position setup logic (including persistence fields) ---
            self.position = {
                'side': 'LONG',
                'price': entry_params['entry_price'],
                'time': ts_game,
                'created_at': self.current_ts_epoch,
                'stop_loss': entry_params['stop_loss'],
                'take_profit': entry_params['take_profit'],
                'trade_id': entry_params['trade_id'], # <-- PERSISTENCE FIELD
                'dyn_pivot_value': entry_params['dyn_pivot_value'], # <-- PERSISTENCE FIELD
                'quantity': entry_params['quantity'], # <-- PERSISTENCE FIELD
            }
            self.stats["TRADES_TAKEN"] += 1
            # del self.pending_long_entry
            self.pending_long_entry = None
    def _process_closed_candle_logic(self, closed_candle: Dict[str, float], ts_game: str, ts_epoch: float):
        """
        Calculates indicators and checks for a new signal. Also handles ENTRY persistence logging.
        """

        # 1. Update Indicators (omitted) ...
        # self._calc_ema(...); self._calc_evwma(...); self._calc_dynamic_pivot(...)

        # 2. Check for the LONG Entry Signal (Placeholder for brevity)
        # if self.dyn_pivot is None: # Use a check for completeness
        #      print("Dynamic Pivot not calculated yet.")
        #      return
        current_close = closed_candle['close']

        # 1. <<< CRITICAL STEP: CALCULATE INDICATORS >>>
        if not self._calculate_all_indicators(current_close):
            # Not enough history (e.g., less than self.pivot_len)
            # print("Not enough data to calculate indicators yet.")
            return

        # 2. CHECK FOR LONG ENTRY SIGNAL (Using calculated indicator)

        # --- Simplified Trade Logic to Force a Signal (Replace this with your actual logic) ---
        # Signal: Close is above the Dynamic Pivot (mocked SMA), and we are flat.
        if self.position is None and current_close > self.dyn_pivot:

            # --- LONG SIGNAL FOUND ---

            # Calculate SL/TP based on the closed candle
            entry_price = closed_candle['high']
            stop_loss = closed_candle['low']
            initial_risk = entry_price - stop_loss

            if initial_risk <= 0: return

            take_profit = entry_price + (3 * initial_risk) # Example: 3:1 RR

            # --- PERSISTENCE LOGIC: LOG ENTRY SIGNAL ---
            trade_id = str(uuid.uuid4())
            hvn_price = self.dyn_pivot # Using Dynamic Pivot as the 'HVN' equivalent for logging

            if self.persistor:
                pos_after_db = 'BUY'

                log_entry = {
                    'timestamp': ts_epoch * 1000, # LTT in milliseconds
                    'signal': 'ENTRY',
                    'instrumentKey': self.instrument_key,
                    'trade_id': trade_id,
                    'ltp': current_close,
                    'hvn': hvn_price,
                    'position_after': pos_after_db,
                    'reason': 'CANDLE_CROSS_TRIGGER',
                    'sl_price': stop_loss,
                    'tp_price': take_profit,
                    'quantity': DEFAULT_QTY,
                    'strategy': STRATEGY_NAME,
                    'type': 'ENTRY'
                }
                self.persistor.log_signal(log_entry)

            # 3. Store Pending Entry
            self.pending_long_entry = {
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'signal_time_epoch': ts_epoch,
                'trade_id': trade_id,
                'dyn_pivot_value': hvn_price,
                'quantity': DEFAULT_QTY,
            }
            self.log_event(ts_game, "LONG_PENDING",
                           f"Signal found! Close > DynPivot ({current_close:.2f} > {self.dyn_pivot:.2f}). Entry: {entry_price:.2f}. ID: {trade_id}")
    # ... (_monitor_pending_entry and _monitor_long_exit remain the same, ensuring position fields are set) ...

    # --- Live Data Entry Point (Using Tick Data) ---

    def process_tick(self, tick: Dict[str, Any]):
        """
        Handles live tick data. Aggregates to 1-minute candle, monitors entry/exit.
        Only calculates indicators when a candle closes.
        """
        if self.is_backtesting:
            self.log_event("N/A", "WARNING", "Called process_tick while in backtesting mode. Use backtest_data_feed instead.")
            return
        # print("Processing tick for ", self.instrument_key)
        # 1. Tick Data Extraction and Time Calculation
        ff = tick.get('fullFeed', {}).get('marketFF', {})
        ltpc = ff.get('ltpc', {})
        ltp = float(ltpc.get('ltp', 0))
        ltq_curr = int(ltpc.get('ltq', 0))

        if ltp == 0 or ltq_curr == 0: return

        ltt = ltpc.get('ltt')
        # Use millisecond LTT for accurate time tracking
        ts_epoch = int(ltt) / 1000.0 if ltt else time.time()
        self.current_ts_epoch = ts_epoch
        self.last_ltp = ltp

        self.current_dt = datetime.utcfromtimestamp(ts_epoch) + timedelta(hours=5, minutes=30)
        ts_game = self.current_dt.strftime('%Y-%m-%d %H:%M:%S')

        current_minute_epoch = int(ts_epoch // 60)

        # 2. Update VWAP State
        self.cum_vol += ltq_curr
        self.cum_pv += (ltp * ltq_curr)
        if self.cum_vol > 0:
            self.vwap = self.cum_pv / self.cum_vol

        # 3. Candle Aggregation & Signal Check
        if self.current_minute_candle['minute'] is None:
            self.current_minute_candle = {'minute': current_minute_epoch, 'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp, 'volume': ltq_curr}

        elif current_minute_epoch != self.current_minute_candle['minute']:
            last_candle = self.current_minute_candle.copy()

            # --- SIGNAL GENERATION (LOW OVERHEAD) ---
            # This calls the method that logs the ENTRY signal to the DB
            self._process_closed_candle_logic(last_candle, ts_game, ts_epoch)

            # Start New Candle
            self.current_minute_candle = {'minute': current_minute_epoch, 'open': ltp, 'high': ltp, 'low': ltp, 'close': ltp, 'volume': ltq_curr}
        else:
            # Update Current Candle
            self.current_minute_candle['high'] = max(self.current_minute_candle['high'], ltp)
            self.current_minute_candle['low'] = min(self.current_minute_candle['low'], ltp)
            self.current_minute_candle['close'] = ltp
            self.current_minute_candle['volume'] += ltq_curr

        # 4. Real-Time Monitoring
        if self.position:
             # This calls _close_position if SL/TP hit, which logs the SQUARE_OFF (EXIT) signal
             self._monitor_long_exit(ltp, ts_game)
        else:
             self._monitor_pending_entry(ltp, ts_game) # Handles entry fulfillment

        # 5. Intraday Square-off
        if self.current_dt.time() >= dt_time(15, 15):
            if self.position:
                self._close_position(ts_game, ltp, "Intraday Square-off")
            return


# --- NEW: UPSTOX DATA PARSING HELPER ---
    def _convert_upstox_candle(self, upstox_candle: List[Any]) -> Dict[str, Any]:
        """
        Converts the Upstox API candle format (list) to the strategy's dictionary format.
        Format: ['2025-12-10T09:24:00+05:30', Open, High, Low, Close, Volume, 0]
        """
        timestamp_str = upstox_candle[0]
        dt_obj = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

        # Ensure we have a uniform time format (epoch in seconds)
        ts_epoch = dt_obj.timestamp()

        return {
            'time_str': dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
            'ts_epoch': ts_epoch,
            'open': upstox_candle[1],
            'high': upstox_candle[2],
            'low': upstox_candle[3],
            'close': upstox_candle[4],
            'volume': upstox_candle[5]
        }

    # --- NEW: BACKTESTING EXECUTION LOGIC ---

    def _check_backtest_exits(self, closed_candle: Dict[str, float]):
        """Checks if SL or TP was hit within the closed candle."""
        if self.position is None:
            return

        pos = self.position
        high = closed_candle['high']
        low = closed_candle['low']

        sl_price = pos.get('stop_loss')
        tp_price = pos.get('take_profit')

        # Exit priority: Assume SL hit takes precedence over TP hit if both are in the candle

        if pos['side'] == 'LONG':
            # Check SL: If low crosses below SL price
            if sl_price and low <= sl_price:
                exit_price = min(sl_price, closed_candle['open']) # Assume exit at SL price or better (open)
                self._close_position(closed_candle['time_str'], exit_price, "Stop Loss Hit (Backtest)")
                return

            # Check TP: If high crosses above TP price
            if tp_price and high >= tp_price:
                exit_price = max(tp_price, closed_candle['open']) # Assume exit at TP price or better (open)
                self._close_position(closed_candle['time_str'], exit_price, "Take Profit Hit (Backtest)")
                return

        elif pos['side'] == 'SHORT':
            # Check SL: If high crosses above SL price
            if sl_price and high >= sl_price:
                exit_price = max(sl_price, closed_candle['open'])
                self._close_position(closed_candle['time_str'], exit_price, "Stop Loss Hit (Backtest)")
                return

            # Check TP: If low crosses below TP price
            if tp_price and low <= tp_price:
                exit_price = min(tp_price, closed_candle['open'])
                self._close_position(closed_candle['time_str'], exit_price, "Take Profit Hit (Backtest)")
                return

    def _check_backtest_entries(self, closed_candle: Dict[str, float]):
        """Checks if a pending order was triggered by the closed candle's price range."""
        if self.position is not None or self.pending_long_entry is None:
            return

        entry_params = self.pending_long_entry
        high = closed_candle['high']
        low = closed_candle['low']

        # Check for LONG entry trigger (entry price is typically High of signal candle)
        if high >= entry_params['entry_price']:

            # Entry logic: The trade is triggered at the entry_price (or first price in the next candle)
            # For simplicity, we assume execution at entry_price if the candle hits it.
            entry_price = entry_params['entry_price']

            # If the entry price was hit AND the stop loss was also hit in the SAME candle (low < SL),
            # we should assume a loss (i.e., the trade was immediately stopped out).
            if entry_params['stop_loss'] and low < entry_params['stop_loss']:
                self.log_event(closed_candle['time_str'], "SIM_TRADE_SKIP",
                               f"LONG signal skipped. Immediate SL hit in entry candle. Entry: {entry_price:.2f}, SL: {entry_params['stop_loss']:.2f}")
                # del self.pending_long_entry
                self.pending_long_entry = None
                return

            # Execute the trade (position creation logic is the same as live)
            self.log_event(closed_candle['time_str'], "TRADE_ENTRY_SIM", f"LONG at {entry_price:.2f} (Triggered in backtest)")

            self.position = {
                'side': 'LONG',
                'price': entry_price,
                'time': closed_candle['time_str'],
                'created_at': closed_candle['ts_epoch'],
                'stop_loss': entry_params['stop_loss'],
                'take_profit': entry_params['take_profit'],
                'trade_id': entry_params['trade_id'],
                'dyn_pivot_value': entry_params['dyn_pivot_value'],
                'quantity': entry_params['quantity'],
            }
            self.stats["TRADES_TAKEN"] += 1
            # del self.pending_long_entry
            self.pending_long_entry = None


    # --- THE MISSING METHOD: backtest_data_feed ---

    def backtest_data_feed(self, historical_candles: List[List[Any]]):
        """
        Processes historical candles for backtesting, sequentially handling exits,
        signal generation, and entries for each closed candle.
        """
        self.is_backtesting = True

        # Determine the minimum candles needed for EMA, Dynamic Pivot, etc.
        min_candles_required = max(self.ema_len, self.pivot_len)

        for i, upstox_candle in enumerate(historical_candles):
            closed_candle = self._convert_upstox_candle(upstox_candle)

            # Update strategy time and price for monitoring/logging
            self.current_ts_epoch = closed_candle['ts_epoch']
            self.current_dt = datetime.fromtimestamp(self.current_ts_epoch)
            ts_game = closed_candle['time_str']
            self.last_ltp = closed_candle['close'] # Use close price for general checks

            # Add close to history for indicator calculation
            self.closes_history.append(closed_candle['close'])

            # 1. Skip if not enough data for indicators
            if len(self.closes_history) < min_candles_required:
                continue

            # **CRITICAL CHANGE**: In backtesting, we check for an exit in the current candle
            # before checking for a new signal or a new entry in the same candle.

            # 2. Check for Exits on the CURRENT candle's price range
            if self.position:
                self._check_backtest_exits(closed_candle)

            # 3. Process the Closed Candle and Check for New Signal (logs ENTRY signal)
            # The signal trigger is based on data *before* this closed_candle
            self._process_closed_candle_logic(closed_candle, ts_game, self.current_ts_epoch)

            # 4. Check for Entry on the CURRENT candle's price range
            if self.pending_long_entry:
                self._check_backtest_entries(closed_candle)

            # 5. Check for Intraday Square-off
            if self.current_dt.time() >= dt_time(15, 15):
                if self.position:
                    self._close_position(ts_game, closed_candle['close'], "Intraday Square-off (Backtest)")
                self.pending_long_entry = None # Cancel any pending order
    # --- Backtesting Data Entry Point (Using Candle Data) ---

    # def backtest_data_feed(self, historical_candles: List[Dict[str, Any]]):
    #     """
    #     Processes a list of closed 1-minute historical candles for backtesting.
    #     This simulates tick movement within each candle for order fulfillment.
    #     """
    #     self.is_backtesting = True

    #     for candle in historical_candles:
    #         ts_game = candle.get('time', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    #         ts_epoch = candle.get('ts_epoch', time.time()) # Should be part of candle data
    #         ltp_close = candle['close']

    #         self.current_ts_epoch = ts_epoch
    #         self.last_ltp = ltp_close

    #         # 1. Calculate and Generate Signal (Runs only once per candle)
    #         # We must simulate VWAP calculation during backtesting too, usually based on Volume and Close.
    #         # Simplified VWAP update (assuming the candle data provides total volume/close for the minute)
    #         self.cum_vol += candle.get('volume', 1)
    #         self.cum_pv += (ltp_close * candle.get('volume', 1))
    #         if self.cum_vol > 0:
    #             self.vwap = self.cum_pv / self.cum_vol

    #         self._process_closed_candle_logic(candle, ts_game, ts_epoch)

    #         # 2. Check for Entry/Exit Fulfillment within this candle (Simulate Tick Monitoring)

    #         # --- EXIT CHECK (Prioritized: SL/TP) ---
    #         if self.position and self.position['side'] == 'LONG':
    #             sl = self.position['stop_loss']
    #             tp = self.position['take_profit']

    #             # Check if SL was hit (price reached Low)
    #             if candle['low'] <= sl:
    #                 # Check if TP was also hit (price reached High). If so, assume SL hit first (Worst case).
    #                 if candle['high'] >= tp:
    #                     self.log_event(ts_game, "SIMULATION_WARNING", f"SL and TP hit within candle. Assuming SL: {sl}")
    #                 self._close_position(ts_game, sl, "Simulated Stop Loss Hit")
    #                 continue # Position closed

    #             # Check if TP was hit (price reached High)
    #             if candle['high'] >= tp:
    #                 self._close_position(ts_game, tp, "Simulated Take Profit Hit")
    #                 continue # Position closed

    #             # Check for Trailing SL trigger (Trail condition is checked by _process_closed_candle_logic)
    #             self._monitor_long_exit(ltp_close, ts_game) # Uses the closed candle Ltp to finalize state/exit

    #         # --- ENTRY CHECK (Executed last) ---
    #         if self.pending_long_entry:
    #             entry_price = self.pending_long_entry['entry_price']

    #             # Entry fulfilled if candle High reached the entry price
    #             if candle['high'] >= entry_price:

    #                 # We assume entry happened at the exact entry price, NOT the candle close.
    #                 self.log_event(ts_game, "TRADE_ENTRY", f"LONG at {entry_price:.2f} (Simulated Trigger)")

    #                 # Entry fills at `entry_price`
    #                 self.position = {
    #                     'side': 'LONG',
    #                     'price': entry_price,
    #                     'time': ts_game,
    #                     'created_at': ts_epoch,
    #                     'stop_loss': self.pending_long_entry['stop_loss'],
    #                     'take_profit': self.pending_long_entry['take_profit'],
    #                 }
    #                 self.stats["TRADES_TAKEN"] += 1
    #                 del self.pending_long_entry

    #         # 3. Handle pending order expiration (not usually needed in candle-by-candle backtest, but for completeness)
    #         else:
    #              # If no entry was hit in the signal candle, it expires immediately at the start of the next candle.
    #              pass

    #     # Print final results
    #     if self.stats['TRADES_TAKEN'] > 0:
    #         print("\n--- Backtesting Results ---FOR ", self.instrument_key)
    #         print(f"Total Trades: {self.stats['TRADES_TAKEN']}")
    #         print(f"Total PNL (Points): {self.stats['PNL']:.2f}")
    #     else:
    #         print("\nNo trades were taken during backtesting for ", self.instrument_key)
