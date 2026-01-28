
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
