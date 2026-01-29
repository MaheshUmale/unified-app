
"""
Enhanced Tape Reading Engine (V2)
Adds Trailing Stop, Profit Targets, and Time-based Exits.
"""

from tape_reading_engine import OrderFlowAnalyzer
from datetime import datetime
import time

class OrderFlowAnalyzerV2(OrderFlowAnalyzer):
    def __init__(self, instrument_key, csv_writer,
                 trailing_stop_points=5.0,
                 target_1_points=10.0,
                 max_hold_time_sec=300,
                 **kwargs):
        super().__init__(instrument_key, csv_writer, **kwargs)

        self.trailing_stop_points = trailing_stop_points
        self.target_1_points = target_1_points
        self.max_hold_time_sec = max_hold_time_sec

        # Enhanced State
        self.highest_price_since_entry = 0.0
        self.lowest_price_since_entry = float('inf')
        self.entry_time_val = None

    def _check_exits(self, ts_game, ltp):
        if not self.position:
            return

        pos = self.position
        entry_price = pos['price']

        # Initialize stats if new position
        if self.entry_time_val != pos['time']:
            self.entry_time_val = pos['time']
            self.highest_price_since_entry = entry_price
            self.lowest_price_since_entry = entry_price

        # Update High/Low
        self.highest_price_since_entry = max(self.highest_price_since_entry, ltp)
        self.lowest_price_since_entry = min(self.lowest_price_since_entry, ltp)

        # 1. Trailing Stop Logic
        if pos['side'] == 'LONG':
            # Stop moves up as price moves up
            dynamic_stop = self.highest_price_since_entry - self.trailing_stop_points
            if ltp < dynamic_stop:
                self._close_position(ts_game, ltp, f"Trailing Stop Hit (High: {self.highest_price_since_entry})")
                return

        elif pos['side'] == 'SHORT':
            # Stop moves down as price moves down
            dynamic_stop = self.lowest_price_since_entry + self.trailing_stop_points
            if ltp > dynamic_stop:
                self._close_position(ts_game, ltp, f"Trailing Stop Hit (Low: {self.lowest_price_since_entry})")
                return

        # 2. Profit Target
        if pos['side'] == 'LONG' and ltp >= (entry_price + self.target_1_points):
             self._close_position(ts_game, ltp, "Target 1 Hit")
             return
        elif pos['side'] == 'SHORT' and ltp <= (entry_price - self.target_1_points):
             self._close_position(ts_game, ltp, "Target 1 Hit")
             return

        # 3. Time Exit (requires timestamp parsing logic from ts_game or using system time if live)
        # Note: ts_game is a string 'HH:MM:SS'. For robustness, we might need datetime objects.
        # super().process_tick passes ts_game_dt. We should override process_tick or capture it.
        pass

    # Override process_tick to inject exit check
    def process_tick(self, tick):
        super().process_tick(tick)

        # After processing, checking exits if we have a position
        if self.position and self.last_ltp:
            # Extract timestamp from tick (same logic as base class)
            if '_insertion_time' in tick:
                 ts_game = tick['_insertion_time'].strftime('%Y-%m-%d %H:%M:%S')
            else:
                 ts_game = datetime.now().strftime('%Y-%m-%d %H:%M:%S') # Fallback

            self._check_exits(ts_game, self.last_ltp)
