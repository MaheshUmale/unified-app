
import sys
import os
import time
import math
from collections import deque
from datetime import datetime, timedelta, time as dt_time

from core.tape_reading_engine_v2 import OrderFlowAnalyzerV2

from datetime import datetime, timedelta, time as dt_time
import math
from collections import deque

class CombinedSignalEngine(OrderFlowAnalyzerV2):
    """
    Combined Strategy Engine:
    Trigger: Failed Auction (Trap) from Tape Reading Engine.
    Confirmation: Order Book Imbalance (OBI) from S9 Strategy.
    """
    def __init__(self, instrument_key, csv_writer,
                 obi_buy_threshold=1.2,
                 obi_sell_threshold=0.8,
                 obi_throttle_sec=1.0,
                 min_hold_time_sec=60,
                 **kwargs):
        super().__init__(instrument_key, csv_writer, **kwargs)

        self.obi_buy_threshold = obi_buy_threshold
        self.obi_sell_threshold = obi_sell_threshold
        self.obi_throttle_sec = obi_throttle_sec
        self.min_hold_time_sec = min_hold_time_sec

        # Optimization: OBI Caching
        self.last_obi_calc_time = 0
        self.current_obi = None

        # Optimization: VWAP State
        self.cum_vol = 0
        self.cum_pv = 0.0
        self.vwap = None

        # Optimization: 20 EMA & Volatility
        self.candles = deque(maxlen=25)
        self.current_minute_candle = {'minute': None, 'open': None, 'high': None, 'low': None, 'close': None}
        self.ema_20 = None
        self.std_dev = None

        self.current_ts_epoch = 0

    def _analyze_side(self, quotes, side_type, ts_game, ltp, ltq, ts_game_dt):
        """
        OVERRIDE: Copied from OrderFlowAnalyzer but REMOVED internal trading logic.
        We only want to track Walls and Broken Walls for the Failed Auction logic.
        """
        if len(quotes) < 3: return

        # 1. Detect Wall
        max_order = max(quotes, key=lambda x: x['q'])
        total_qty = sum(x['q'] for x in quotes)
        avg_qty_others = (total_qty - max_order['q']) / (len(quotes) - 1) if len(quotes) > 1 else max_order['q']
        ratio = max_order['q'] / avg_qty_others if avg_qty_others > 0 else 0

        wall_state = self.bid_wall if side_type == 'BID' else self.ask_wall
        wall_tag = f"WALL_DETECTED_{side_type}"

        if ratio >= self.big_wall_threshold_ratio:
            if wall_state['price'] != max_order['p']:
                # New Wall
                wall_state['price'] = max_order['p']
                wall_state['qty'] = max_order['q']
                wall_state['cum_vol'] = 0
                wall_state['start_time'] = ts_game_dt # Track creation time
                self.log_event(ts_game, wall_tag, f"Price: {max_order['p']} | Qty: {max_order['q']} | Ratio: {ratio:.1f}x")
            else:
                # Existing Wall Reload Check
                if max_order['q'] > wall_state['qty']:
                    self.log_event(ts_game, f"WALL_RELOAD_{side_type}", f"Price: {max_order['p']} | Qty increased to {max_order['q']}")
                wall_state['qty'] = max_order['q']
        else:
             # Wall Gone?
             if wall_state['price']:
                 is_broken = (ltp < wall_state['price']) if side_type == 'BID' else (ltp > wall_state['price'])
                 if is_broken:
                     self.log_event(ts_game, f"WALL_BROKEN_{side_type}", f"Price {ltp} broke wall {wall_state['price']}")

                     # Calculate Duration
                     duration = 0
                     if wall_state.get('start_time'):
                         duration = (ts_game_dt - wall_state['start_time']).total_seconds()

                     # Track Broken Wall for Failed Auction logic
                     self.broken_walls.append({
                        'price': wall_state['price'],
                        'side': side_type,
                        'time': ts_game,
                        'duration': duration,
                        'active': True
                     })
                     # Keep only last 5 broken walls
                     if len(self.broken_walls) > 5:
                        self.broken_walls.pop(0)

                     wall_state['price'] = None
                     wall_state['start_time'] = None # Reset
                 elif wall_state['price'] == max_order['p'] and ratio < (self.big_wall_threshold_ratio * 0.8):
                     self.log_event(ts_game, f"WALL_GONER_{side_type}", f"Order at {wall_state['price']} dropped to normal size")
                     wall_state['price'] = None
                     wall_state['start_time'] = None

        # 2. Check Absorption (Logging ONLY, NO TRADING)
        if wall_state['price'] and ltp == wall_state['price']:
            wall_state['cum_vol'] += ltq

            if wall_state['cum_vol'] > self.absorption_min_qty:
                self.log_event(ts_game, f"ABSORPTION_{side_type}", f"Vol {wall_state['cum_vol']} at {wall_state['price']}")
                wall_state['cum_vol'] = 0

    def _calculate_order_book_imbalance(self, market_ff) -> float:
        try:
            buy_quantity_total = float(market_ff.get('tbq', 0))
            sell_quantity_total = float(market_ff.get('tsq', 0))

            if sell_quantity_total > 0:
                return buy_quantity_total / sell_quantity_total
            elif buy_quantity_total > 0:
                return 999.0
            else:
                return None
        except Exception:
            return None

    def _update_candles(self, ts_epoch, ltp):
        """Aggregate 1-minute OHLC prices and calc EMA/StdDev."""
        current_minute = int(ts_epoch // 60)

        if self.current_minute_candle['minute'] is None:
            self.current_minute_candle['minute'] = current_minute
            self.current_minute_candle['open'] = ltp
            self.current_minute_candle['high'] = ltp
            self.current_minute_candle['low'] = ltp
            self.current_minute_candle['close'] = ltp

        elif current_minute != self.current_minute_candle['minute']:
            # New Candle Closed
            last_candle = {
                'open': self.current_minute_candle['open'],
                'high': self.current_minute_candle['high'],
                'low': self.current_minute_candle['low'],
                'close': self.current_minute_candle['close']
            }
            self.candles.append(last_candle)

            # Start New Candle
            self.current_minute_candle['minute'] = current_minute
            self.current_minute_candle['open'] = ltp
            self.current_minute_candle['high'] = ltp
            self.current_minute_candle['low'] = ltp
            self.current_minute_candle['close'] = ltp

            # Calculate Indicators
            if len(self.candles) >= 20:
                closes = [c['close'] for c in self.candles]

                # EMA 20
                if self.ema_20 is None:
                    self.ema_20 = sum(closes[-20:]) / 20.0
                else:
                    k = 2.0 / (20 + 1)
                    self.ema_20 = (closes[-1] * k) + (self.ema_20 * (1 - k))

                # Std Deviation (last 20)
                mean = sum(closes[-20:]) / 20.0
                variance = sum((x - mean) ** 2 for x in closes[-20:]) / 20.0
                self.std_dev = math.sqrt(variance)
        else:
            # Update Current Candle
            self.current_minute_candle['high'] = max(self.current_minute_candle['high'], ltp)
            self.current_minute_candle['low'] = min(self.current_minute_candle['low'], ltp)
            self.current_minute_candle['close'] = ltp

    def _check_candlestick_pattern(self, signal_type) -> bool:
        """
        Check for confirmatory candlestick patterns on the last CLOSED candle.
        Bulish: Bullish Engulfing, Hammer
        Bearish: Bearish Engulfing, Shooting Star
        """
        if len(self.candles) < 2: return False

        last_candle = self.candles[-1]
        prev_candle = self.candles[-2]

        curr_open = last_candle['open']
        curr_close = last_candle['close']
        curr_high = last_candle['high']
        curr_low = last_candle['low']
        curr_body = abs(curr_close - curr_open)
        curr_range = curr_high - curr_low

        # Avoid Doji/Flat candles for patterns mainly
        if curr_range == 0: return False

        is_green = curr_close > curr_open
        is_red = curr_close < curr_open

        if signal_type == "FAILED_AUCTION_BUY":
            # Looking for BULLISH Patterns

            # 1. Bullish Engulfing
            # Prev Red, Curr Green. Curr Body engulfs Prev Body.
            prev_is_red = prev_candle['close'] < prev_candle['open']
            prev_body = abs(prev_candle['close'] - prev_candle['open'])
            if prev_is_red and is_green:
                if curr_open <= prev_candle['close'] and curr_close >= prev_candle['open']:
                     return True

            # 2. Hammer
            # Lower wick >= 2 * body. Upper wick small.
            lower_wick = min(curr_open, curr_close) - curr_low
            upper_wick = curr_high - max(curr_open, curr_close)

            if lower_wick >= (2 * curr_body) and upper_wick <= (0.5 * curr_body):
                 return True

        elif signal_type == "FAILED_AUCTION_SELL":
            # Looking for BEARISH Patterns

            # 1. Bearish Engulfing
            # Prev Green, Curr Red. Curr Body engulfs Prev Body.
            prev_is_green = prev_candle['close'] > prev_candle['open']
            if prev_is_green and is_red:
                if curr_open >= prev_candle['close'] and curr_close <= prev_candle['open']:
                    return True

            # 2. Shooting Star
            # Upper wick >= 2 * body. Lower wick small.
            upper_wick = curr_high - max(curr_open, curr_close)
            lower_wick = min(curr_open, curr_close) - curr_low

            if upper_wick >= (2 * curr_body) and lower_wick <= (0.5 * curr_body):
                return True

        return False

    def process_tick(self, tick):
        try:
            ff = tick.get('fullFeed', {}).get('marketFF', {})
            ltpc = ff.get('ltpc', {})
            ltp = float(ltpc.get('ltp', 0))
            ltq_curr = int(ltpc.get('ltq', 0))

            # Timestamp for Candles
            ltt = ltpc.get('ltt')
            if ltt:
                ts_epoch = int(ltt) / 1000.0
            else:
                ts_epoch = time.time() # Fallback

            # 1. Update Candles & Indicators
            if ltp > 0:
                self._update_candles(ts_epoch, ltp)

            self.current_ts_epoch = ts_epoch # Store for hold time check

            # --- INTRADAY TIME LOGIC ---
            # Prefer _insertion_time for "Wall Clock" schedule if available (Backtest/Live consistency)
            if '_insertion_time' in tick:
                current_time = tick['_insertion_time'] # Already datetime value in some contexts, or need parsing?
                # In backtesting, it's usually a datetime object from Mongo.
                # If string, parse it.
                if isinstance(current_time, str):
                     try: current_time = datetime.strptime(current_time, '%Y-%m-%d %H:%M:%S')
                     except: current_time = datetime.now()
            else:
                # Fallback to LTT + IST Offset
                current_time = datetime.utcfromtimestamp(ts_epoch) + timedelta(hours=5, minutes=30)

            self.current_dt = current_time

            # --- STRICT OVERNIGHT GUARD ---
            if self.position:
                pos_time_str = self.position.get('time', '')
                if pos_time_str:
                    try:
                        # Assumes 'time' format is "%Y-%m-%d %H:%M:%S"
                        pos_date = datetime.strptime(pos_time_str, '%Y-%m-%d %H:%M:%S').date()
                        current_date = current_time.date()
                        if current_date > pos_date:
                            self._close_position(current_time.strftime('%Y-%m-%d %H:%M:%S'), ltp, "Overnight Gap Protection")
                            return # Stop processing
                    except:
                        pass

            # 1. Square-off at 15:15
            if current_time.time() >= dt_time(15, 15):
                if self.position:
                    self._close_position(current_time.strftime('%Y-%m-%d %H:%M:%S'), ltp, "Intraday Square-off")
                return # Stop processing (No further signals)

            # 2. VWAP Calculation
            if ltp > 0 and ltq_curr > 0:
                self.cum_vol += ltq_curr
                self.cum_pv += (ltp * ltq_curr)
                if self.cum_vol > 0:
                    self.vwap = self.cum_pv / self.cum_vol

            # 3. OBI Calculation (Throttled)
            now = time.time()
            if (now - self.last_obi_calc_time) > self.obi_throttle_sec:
                obi = self._calculate_order_book_imbalance(ff)
                if obi is not None:
                    self.current_obi = obi
                    self.last_obi_calc_time = now
        except:
            pass

        super().process_tick(tick)

    def _check_reclaims(self, ts_game, ltp):
        # --- ENTRY CUTOFF (15:00) ---
        if hasattr(self, 'current_dt') and self.current_dt.time() >= dt_time(15, 0):
            return

        # Iterate broken walls to find reclaims (Traps)
        for wall in self.broken_walls[:]:
            if not wall['active']: continue

            # --- FILTER 1: WALL DURABILITY ---
            if wall.get('duration', 0) < 30.0:
                 continue

            reclaimed = False
            signal_type = None

            if wall['side'] == 'BID' and ltp > wall['price']:
                reclaimed = True
                signal_type = "FAILED_AUCTION_BUY"
            elif wall['side'] == 'ASK' and ltp < wall['price']:
                reclaimed = True
                signal_type = "FAILED_AUCTION_SELL"

            if reclaimed:
                # --- FILTER 2: DYNAMIC MODE (Trend vs Reversion) ---
                is_trend_valid = True
                mode = "TREND"

                # Check Volatility Bands (EMA +/- SD)
                if self.ema_20 and self.std_dev:
                    # Trend Zone: Tight to EMA (0.5 SD)
                    trend_upper = self.ema_20 + (0.5 * self.std_dev)
                    trend_lower = self.ema_20 - (0.5 * self.std_dev)

                    # Reversion Zone: Extreme (2.5 SD)
                    reversion_upper = self.ema_20 + (2.5 * self.std_dev)
                    reversion_lower = self.ema_20 - (2.5 * self.std_dev)

                    if ltp > reversion_upper:
                        # Extreme Overbought -> Mode REVERSION (Look for Shorts)
                        mode = "REVERSION_SHORT"
                    elif ltp < reversion_lower:
                        # Extreme Oversold -> Mode REVERSION (Look for Longs)
                        mode = "REVERSION_LONG"
                    elif trend_lower <= ltp <= trend_upper:
                        # Normal/Tight -> Mode TREND
                        mode = "TREND"
                    else:
                        # In the "No Trade Zone" (Between 0.5 and 2.5 SD)
                        mode = "SKIP"

                # Apply Logic based on Mode
                if mode == "SKIP":
                    continue

                if mode == "TREND":
                    # STRICT VWAP RULES
                    if self.vwap:
                        if signal_type == "FAILED_AUCTION_BUY" and ltp < (self.vwap * 0.999):
                            is_trend_valid = False # Counter-Trend Long
                        elif signal_type == "FAILED_AUCTION_SELL" and ltp > (self.vwap * 1.001):
                            is_trend_valid = False # Counter-Trend Short

                elif mode == "REVERSION_SHORT":
                    # We are Overbought. Only take Shorts.
                    if signal_type == "FAILED_AUCTION_BUY":
                        is_trend_valid = False # Don't buy if already overbought

                elif mode == "REVERSION_LONG":
                    # We are Oversold. Only take Longs.
                    if signal_type == "FAILED_AUCTION_SELL":
                        is_trend_valid = False # Don't sell if already oversold

                if not is_trend_valid:
                    continue

                # --- NEW: OBI CONFIRMATION CHECK ---
                obi_confirmed = False
                obi_val = self.current_obi if self.current_obi is not None else 1.0

                if signal_type == "FAILED_AUCTION_BUY":
                    if obi_val > self.obi_buy_threshold: obi_confirmed = True
                elif signal_type == "FAILED_AUCTION_SELL":
                    if obi_val < self.obi_sell_threshold: obi_confirmed = True

                if not obi_confirmed:
                    return

                # --- NEW: CANDLESTICK CONFIRMATION ---
                # Check if the last closed candle supports the direction
                # This adds a delay (waiting for candle close) or confirms rapid moves?
                # The user asked for "candlestick patterns to confirm".
                # If we rely on LAST CLOSED candle, we might be 'late' if the move is happening NOW.
                # But for 'Failed Auction', we usually want to see a rejection.
                # Let's start with Logging matching patterns, and optionally filtering.
                # For now, I'll log it. If I return False, I might miss too many trades.
                # The user said "use candlestick patterns... to confirm". That implies a filter.

                pattern_found = self._check_candlestick_pattern(signal_type)
                if not pattern_found:
                    # Optional: We could be lenient if tape speed is VERY high?
                    # For now, strictly enforce as requested.
                     # self.log_event(ts_game, "PATTERN_FAIL", f"No matching candle pattern for {signal_type}")
                     # Wait, if we require a closed candle pattern, we might be 30s late.
                     # But 'Failed Auction' is often a re-test.
                     # Let's enforce it.
                     pass
                     # self.log_event(ts_game, "DEBUG", "Candle Pattern not found. Skipping.")
                     # return # Enable this to STRICTLY enforce.
                     # For the first run, let's just log if it WAS found to verify detection.
                     # User said "can we use... to confirm". I should probably use it.
                     pass

                # ENABLE FILTER:
                if not pattern_found:
                    return

                # --- Original Logic ---
                speed, aggression = self.get_metrics()

                # --- Original Logic ---
                speed, aggression = self.get_metrics()
                confirmed = False
                if speed > 0.2:
                    if signal_type == "FAILED_AUCTION_BUY" and aggression > -0.2: confirmed = True
                    elif signal_type == "FAILED_AUCTION_SELL" and aggression < 0.2: confirmed = True

                if confirmed:
                    # --- MIN HOLD TIME CHECK (Prevent Rapid Reversals) ---
                    if self.position and (self.current_ts_epoch - self.position.get('created_at', 0)) < self.min_hold_time_sec:
                         # Too soon to reverse. Ignore signal.
                         continue

                    log_msg = f"CONFLUENCE ({mode}): Price {ltp} reclaimed {wall['side']} | VWAP: {self.vwap:.2f} | EMA: {self.ema_20:.2f}"
                    self.log_event(ts_game, signal_type, log_msg)
                    wall['active'] = False

                    # --- EXECUTION ---
                    if signal_type == "FAILED_AUCTION_BUY":
                         if self.position is None:
                             self.log_event(ts_game, "TRADE_ENTRY", f"LONG at {ltp}")
                             self.position = {'side': 'LONG', 'price': ltp, 'time': ts_game, 'created_at': self.current_ts_epoch}
                             self.stats["TRADES_TAKEN"] += 1
                         elif self.position['side'] == 'SHORT':
                             self._close_position(ts_game, wall['price'], "Reversal")

                    elif signal_type == "FAILED_AUCTION_SELL":
                         if self.position is None:
                             self.log_event(ts_game, "TRADE_ENTRY", f"SHORT at {ltp}")
                             self.position = {'side': 'SHORT', 'price': ltp, 'time': ts_game, 'created_at': self.current_ts_epoch}
                             self.stats["TRADES_TAKEN"] += 1
                         elif self.position['side'] == 'LONG':
                             self._close_position(ts_game, wall['price'], "Reversal")
