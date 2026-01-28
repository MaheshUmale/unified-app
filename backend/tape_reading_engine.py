
import pymongo
from pymongo import MongoClient
from datetime import datetime
import time
import database


class OrderFlowAnalyzer:
    def __init__(self, instrument_key, csv_writer, big_wall_threshold_ratio=3.0, absorption_min_qty=1000):
        self.instrument_key = instrument_key
        self.big_wall_threshold_ratio = big_wall_threshold_ratio
        self.absorption_min_qty = absorption_min_qty
        self.csv_writer = csv_writer

        # State
        self.bid_wall = {'price': None, 'qty': 0, 'start_time': None, 'cum_vol': 0}
        self.ask_wall = {'price': None, 'qty': 0, 'start_time': None, 'cum_vol': 0}

        # Trade State
        self.position = None
        self.trades = []

        # Stats
        self.events = []
        self.stats = {"WALL_DETECTED_BID": 0, "WALL_DETECTED_ASK": 0,
                      "ABSORPTION_BID": 0, "ABSORPTION_ASK": 0,
                      "BUY_SIGNAL": 0, "EXIT_SIGNAL": 0,
                      "SELL_SIGNAL": 0, "TRADES_TAKEN": 0}

        safe_key = instrument_key.replace('|', '_')
        self.log_file = open(f"backtest_results_{safe_key}.txt", "w")
# --- MONGODB INTEGRATION ---
        self.signals_collection = database.get_trade_signals_collection()
        if self.signals_collection is not None:
            print(f"✅ Analyzer connected to MongoDB collection: {database.SIGNAL_COLLECTION_NAME}")
        else:
            print("❌ MongoDB connection failed. Signals will only be logged to file.")
        # ---------------------------

        # Failed Auction / Trap Logic State
        self.broken_walls = [] # List of {'price', 'side', 'time', 'active': True}
        self.tape_speed_window = [] # List of timestamps for trades
        self.last_ltp = None

    def log_event(self, timestamp_str, event_type, details, trade_id=None, extra_data=None):
        """
        Logs event to file and inserts trade signals into MongoDB.
        timestamp_str: string formatted as 'YYYY-MM-DD HH:MM:SS'
        trade_id: Manually passed for TRADE_EXIT to link it to the ENTRY.
        extra_data: Dictionary of data to include in the Mongo document (e.g., strategy, pnl, etc.)
        """

       # 1. Prepare base event data
        event = {
            "timestamp_str": timestamp_str,
            "type": event_type,
            "details": details,
            "instrumentKey": self.instrument_key
        }
        self.events.append(event)

        # Convert timestamp string to datetime object and then to epoch time
        dt_obj = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
        epoch_timestamp = dt_obj.timestamp()

        # 2. Log to file
        log_line = f"[{timestamp_str}] {self.instrument_key} {event_type}: {details}"
        self.log_file.write(log_line + "\n")

        if "SIGNAL" in event_type or "TRADE_ENTRY" in event_type:
             print(f">>> {log_line}")

        if event_type in self.stats:
            self.stats[event_type] += 1

        # 3. --- MONGODB INSERTION LOGIC ---
        if self.signals_collection:
            mongo_doc = {
                "timestamp": epoch_timestamp, # Required by your API for sorting and querying
                "instrumentKey": self.instrument_key,
                "type": "OTHER", # Default
                "log_message": log_line
            }
            if extra_data:
                mongo_doc.update(extra_data)

            if 'TRADE_ENTRY' in event_type:
                # Assuming entry details are passed in extra_data
                mongo_doc.update({
                    "type": "ENTRY",
                    "trade_id": self.current_trade_id, # Use the ID set by _check_reclaims or _analyze_side
                    "ltp": extra_data.get('price'),
                    "position_after": extra_data.get('side', '').replace('LONG', 'BUY').replace('SHORT', 'SELL')
                })
                self.signals_collection.insert_one(mongo_doc)

            elif 'TRADE_EXIT' in event_type:
                # Assuming exit details are passed in extra_data
                mongo_doc.update({
                    "type": "EXIT",
                    "trade_id": trade_id, # Passed from _close_position
                    "exit_price": extra_data.get('price'),
                    "pnl": extra_data.get('pnl'),
                    "reason_code": extra_data.get('reason'),
                    "position_closed": extra_data.get('side'),
                })
                self.signals_collection.insert_one(mongo_doc)

            elif 'FAILED_AUCTION' in event_type:
                # Log supporting signals
                mongo_doc.update({
                    "type": "SIGNAL",
                    "signal_type": event_type,
                    "details": details
                })
                self.signals_collection.insert_one(mongo_doc)

        # -----------------------------------

    def _update_metrics(self, ltp, ltq, bids, asks, current_time):
        # 1. Tape Speed (Event Count)
        self.tape_speed_window.append({'time': current_time, 'qty': ltq, 'side': 'UNKNOWN'})

        # 2. Determine Side (Aggression)
        # If LTP >= BestAsk -> BUY
        # If LTP <= BestBid -> SELL
        side = 'UNKNOWN'
        if asks and ltp >= asks[0]['p']:
            side = 'BUY'
        elif bids and ltp <= bids[0]['p']:
            side = 'SELL'

        self.tape_speed_window[-1]['side'] = side

        # Prune old events (> 5 seconds ago)
        cutoff_time = current_time.timestamp() - 5.0
        self.tape_speed_window = [t for t in self.tape_speed_window if t['time'].timestamp() > cutoff_time]

    def get_metrics(self):
        count = len(self.tape_speed_window)
        speed = count / 5.0

        buy_vol = sum(t['qty'] for t in self.tape_speed_window if t['side'] == 'BUY')
        sell_vol = sum(t['qty'] for t in self.tape_speed_window if t['side'] == 'SELL')
        total_vol = buy_vol + sell_vol

        aggression = 0
        if total_vol > 0:
            aggression = (buy_vol - sell_vol) / total_vol # -1.0 to +1.0

        return speed, aggression

    def _check_reclaims(self, ts_game, ltp):
        # Check if price reclaimed any broken wall
        # Reclaim = Price moves BACK into the range (Reverse of the break)

        for wall in self.broken_walls[:]: # Copy to iterate
            if not wall['active']: continue

            # Simple Logic:
            # If Support (BID) was broken (Price went Down), Reclaim is Price Going Up > Wall Price
            # If Resistance (ASK) was broken (Price went Up), Reclaim is Price Going Down < Wall Price

            reclaimed = False
            if wall['side'] == 'BID' and ltp > wall['price']:
                reclaimed = True
                signal_type = "FAILED_AUCTION_BUY" # Bull Trap for Sellers (They sold low, now trapped)

            elif wall['side'] == 'ASK' and ltp < wall['price']:
                reclaimed = True
                signal_type = "FAILED_AUCTION_SELL" # Bear Trap for Buyers (They bought high, now trapped)

            if reclaimed:
                # --- CONFIRMATION CHECK ---
                speed, aggression = self.get_metrics()

                # Filter: Speed > 0.5 (at least some activity)
                # Filter: Aggression supports the reversal?
                # If BUY Signal (Price went up), we want Aggression > 0 (More Buying)
                # If SELL Signal (Price went down), we want Aggression < 0 (More Selling)

                confirmed = False
                if speed > 0.2: # Loose filter for now
                    if signal_type == "FAILED_AUCTION_BUY" and aggression > 0.2: # Not heavily selling
                         confirmed = True
                    elif signal_type == "FAILED_AUCTION_SELL" and aggression < -0.2: # Not heavily buying
                         confirmed = True

                if confirmed:
                    self.log_event(ts_game, signal_type, f"Price {ltp} reclaimed broken {wall['side']} wall at {wall['price']} | Spd: {speed:.1f} | Agg: {aggression:.2f}")
                    wall['active'] = False # Disable after one trigger

                # --- STRATEGY ENTRY ON FAILED AUCTION ---
                # A Failed Auction is a high conviction reversal signal
                if signal_type == "FAILED_AUCTION_BUY": # Bullish
                     if self.position is None:
                        #  self.log_event(ts_game, "TRADE_ENTRY", f"LONG (Failed Auction) at {ltp}")
                         self.log_event(ts_game, "TRADE_ENTRY", f"LONG at {ltp}",
                                        extra_data={'price': ltp, 'side': 'LONG', 'strategy': 'FAILED_AUCTION'})
                         self.position = {'side': 'LONG', 'price': ltp, 'time': ts_game}
                         self.stats["TRADES_TAKEN"] += 1
                     elif self.position['side'] == 'SHORT':
                         self._close_position(ts_game, wall['price'], "Reversal (Failed Auction)")
                         # Reverse?

                elif signal_type == "FAILED_AUCTION_SELL": # Bearish
                     if self.position is None:
                        #  self.log_event(ts_game, "TRADE_ENTRY", f"SHORT (Failed Auction) at {ltp}")
                         self.log_event(ts_game, "TRADE_ENTRY", f"SHORT at {ltp}",
                                        extra_data={'price': ltp, 'side': 'SHORT', 'strategy': 'ABSORPTION'})
                         self.position = {'side': 'SHORT', 'price': ltp, 'time': ts_game}
                         self.stats["TRADES_TAKEN"] += 1
                     elif self.position['side'] == 'LONG':
                         self._close_position(ts_game, wall['price'], "Reversal (Failed Auction)")

    def _analyze_side(self, quotes, side_type, ts_game, ltp, ltq, ts_game_dt):
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
                        'duration': duration, # NEW
                        'active': True
                     })
                     # Keep only last 5 broken walls to avoid noise
                     if len(self.broken_walls) > 5:
                        self.broken_walls.pop(0)

                     wall_state['price'] = None
                     wall_state['start_time'] = None # Reset
                 elif wall_state['price'] == max_order['p'] and ratio < (self.big_wall_threshold_ratio * 0.8):
                     self.log_event(ts_game, f"WALL_GONER_{side_type}", f"Order at {wall_state['price']} dropped to normal size")
                     wall_state['price'] = None
                     wall_state['start_time'] = None

        # 2. Check Absorption (Testing the Wall)
        if wall_state['price'] and ltp == wall_state['price']:
            wall_state['cum_vol'] += ltq

            if wall_state['cum_vol'] > self.absorption_min_qty:
                self.log_event(ts_game, f"ABSORPTION_{side_type}", f"Vol {wall_state['cum_vol']} at {wall_state['price']}")
                wall_state['cum_vol'] = 0

                # --- IMMEDIATE ENTRY SIGNAL (Simple Strategy) ---
                if side_type == 'BID':
                     # Buy Signal (Support Absorption)
                     self.log_event(ts_game, "BUY_SIGNAL", f"Support Absorbed at {wall_state['price']}")
                     if self.position is None:
                        #  self.log_event(ts_game, "TRADE_ENTRY", f"LONG at {ltp}")
                         self.log_event(ts_game, "TRADE_ENTRY", f"LONG at {ltp}",
                                        extra_data={'price': ltp, 'side': 'LONG', 'strategy': 'ABSORPTION'})
                         self.position = {'side': 'LONG', 'price': ltp, 'time': ts_game}
                         self.stats["TRADES_TAKEN"] += 1
                     elif self.position['side'] == 'SHORT':
                         self._close_position(ts_game, wall_state['price'], "Target (Support Hit)")

                else:
                     # Sell Signal (Resistance Absorption)
                     self.log_event(ts_game, "SELL_SIGNAL", f"Resistance Absorbed at {wall_state['price']}")
                     if self.position is None:
                        #  self.log_event(ts_game, "TRADE_ENTRY", f"SHORT at {ltp}")
                         self.log_event(ts_game, "TRADE_ENTRY", f"SHORT at {ltp}",
                                        extra_data={'price': ltp, 'side': 'SHORT', 'strategy': 'ABSORPTION'})
                         self.position = {'side': 'SHORT', 'price': ltp, 'time': ts_game}
                         self.stats["TRADES_TAKEN"] += 1
                     elif self.position['side'] == 'LONG':
                         self._close_position(ts_game, wall_state['price'], "Target (Resistance Hit)")

    def _close_position(self, ts, price, reason):
        if not self.position: return

        entry_price = self.position['price']
        side = self.position['side']

        if side == 'LONG':
            pnl = price - entry_price
        else:
            pnl = entry_price - price

        # Log TRADE_EXIT (Logged to file and Mongo)
        self.log_event(ts, "TRADE_EXIT", f"Closed {side} at {price} | PnL: {pnl:.2f} | Reason: {reason}",
                       trade_id=trade_id,
                       extra_data={'price': price, 'pnl': pnl, 'reason': reason, 'side': side})
        self.csv_writer.write(f"{self.instrument_key},{self.position['time']},{side},{entry_price},{ts},{price},{pnl:.2f},{reason}\n")

        self.trades.append({'entry_time': self.position['time'], 'side': side, 'entry_price': entry_price, 'exit_time': ts, 'exit_price': price, 'pnl': pnl})
        self.position = None
        self.current_trade_id = None # Trade closed, reset ID

    def process_tick(self, tick):
        try:
            ff = tick.get('fullFeed', {}).get('marketFF', {})
            if not ff: return

            ltpc = ff.get('ltpc', {})
            ltp = ltpc.get('ltp')
            ltq = int(ltpc.get('ltq', 0))
            ltt = ltpc.get('ltt')

            market_level = ff.get('marketLevel', {})
            quotes = market_level.get('bidAskQuote', [])

            if ltt:
                ts_game_dt = datetime.fromtimestamp(int(ltt)/1000)
                ts_game = ts_game_dt.strftime('%Y-%m-%d %H:%M:%S')
            else:
                ts_game_dt = tick['_insertion_time']
                ts_game = ts_game_dt.strftime('%Y-%m-%d %H:%M:%S')

            if not ltp or not quotes: return

            # --- STOP LOSS CHECK (Global) ---
            # Removed "Strict Stop Loss at Entry" (User Feedback: Too tight)
            # relying on V2 Trailing Stop or Reversal logic.
            # if self.position: ...

            # Parse Bids and Asks
            valid_bids = []
            valid_asks = []
            for q in quotes:
                try:
                    # Bids
                    bq = int(q.get('bidQ', 0))
                    bp = float(q.get('bidP', 0))
                    if bq > 0: valid_bids.append({'p': bp, 'q': bq})

                    # Asks
                    aq = int(q.get('askQ', 0))
                    ap = float(q.get('askP', 0))
                    if aq > 0: valid_asks.append({'p': ap, 'q': aq})
                except: continue

            # Update Market Metrics (Tape Speed & Aggression)
            self._update_metrics(ltp, ltq, valid_bids, valid_asks, ts_game_dt)

            # Analyze Order Flow
            self._analyze_side(valid_bids, 'BID', ts_game, ltp, ltq, ts_game_dt)
            self._analyze_side(valid_asks, 'ASK', ts_game, ltp, ltq, ts_game_dt)

            # Check for Reclaims (Failed Auctions)
            self._check_reclaims(ts_game, ltp)

            self.last_ltp = ltp

        except Exception as e:
            # print(f"Error: {e}")
            pass

    def finish(self):
        self.log_file.close()
