import logging
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
import asyncio
import json
import csv
import os
import time
from scipy.signal import find_peaks
from core.options_manager import options_manager
from core.oi_buildup_analyzer import oi_buildup_analyzer

logger = logging.getLogger(__name__)

class DataStreamer:
    """Handles WSS connections for Underlying, ATM Call, and ATM Put."""
    def __init__(self, scalper):
        self.scalper = scalper
        self.buffers = {
            'underlying': pd.DataFrame(columns=['ts', 'o', 'h', 'l', 'c', 'v']),
            'atm_call': pd.DataFrame(columns=['ts', 'o', 'h', 'l', 'c', 'v']),
            'atm_put': pd.DataFrame(columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        }
        self.tick_buffer = [] # Circular buffer of last 500 ticks
        self.instrument_map = {} # instrumentKey -> 'underlying'|'atm_call'|'atm_put'
        self.symbols = {} # 'underlying'|'atm_call'|'atm_put' -> instrumentKey
        self.cum_vol = {'underlying': 0, 'atm_call': 0, 'atm_put': 0}
        self.cum_pv = {'underlying': 0, 'atm_call': 0, 'atm_put': 0}
        self.vwap = {'underlying': 0, 'atm_call': 0, 'atm_put': 0}

    def on_tick(self, instrument_key, tick_data):
        target = self.instrument_map.get(instrument_key)
        if not target: return

        price = float(tick_data.get('last_price', 0))
        volume = int(tick_data.get('ltq', 0))

        tick = {
            'ts': tick_data.get('ts_ms', time.time()*1000),
            'last_price': price,
            'ltq': volume
        }

        # Calculate VWAP
        if volume > 0:
            self.cum_vol[target] += volume
            self.cum_pv[target] += price * volume
            self.vwap[target] = self.cum_pv[target] / self.cum_vol[target]

        if target == 'underlying':
            self.scalper.current_spot = price
            self.tick_buffer.append(tick)
            if len(self.tick_buffer) > 500: self.tick_buffer.pop(0)

            # Re-calculate HVN every 100 ticks
            if len(self.tick_buffer) % 100 == 0:
                self.scalper.engine.calculate_volume_profile(self.tick_buffer)

        self.scalper.last_ticks[target] = tick

    def on_ohlcv(self, instrument_key, candle_data):
        target = self.instrument_map.get(instrument_key)
        if not target: return

        if not candle_data or 'ohlcv' not in candle_data: return

        new_df = pd.DataFrame(candle_data['ohlcv'], columns=['ts', 'o', 'h', 'l', 'c', 'v'])
        self.buffers[target] = new_df

        # Update levels
        if target == 'underlying':
            self.scalper.engine.find_levels(new_df, 'underlying')
        else:
            self.scalper.engine.update_option_levels(instrument_key, new_df)

    async def subscribe(self, underlying):
        from core.options_manager import options_manager
        from core.provider_registry import live_stream_registry

        self.symbols['underlying'] = underlying
        self.instrument_map[underlying] = 'underlying'

        # Find ATM options
        spot = await options_manager.get_spot_price(underlying)
        if spot == 0:
            logger.error(f"Cannot subscribe for {underlying}: Spot price 0")
            return

        self.scalper.current_spot = spot
        atm_strike = round(spot / 100) * 100

        # Ensure symbols are cached
        await options_manager._refresh_wss_symbols(underlying)
        # Find specific ATM Call and Put
        call_sym = options_manager.symbol_map_cache.get(underlying, {}).get(f"{atm_strike}_call")
        put_sym = options_manager.symbol_map_cache.get(underlying, {}).get(f"{atm_strike}_put")

        if not call_sym or not put_sym:
            logger.error(f"ATM symbols not found for {underlying} at {atm_strike}")
            return

        self.symbols['atm_call'] = call_sym
        self.symbols['atm_put'] = put_sym
        self.instrument_map[call_sym] = 'atm_call'
        self.instrument_map[put_sym] = 'atm_put'

        # Use registry for live stream
        provider = live_stream_registry.get_primary()
        provider.set_callback(self.scalper._handle_wss_message)
        provider.start()
        provider.subscribe([underlying, call_sym, put_sym], interval="1")

        self.scalper.log(f"Subscribed via {type(provider).__name__} to {underlying}, {call_sym}, {put_sym}")

class ConfluenceEngine:
    """Identifies Zones of Interest and generates signals."""
    def __init__(self, scalper):
        self.scalper = scalper
        self.underlying_levels = [] # List of prices
        self.hvn_levels = []
        self.option_levels = {} # {symbol: {'orb_h':, 'orb_l':, 'prev_15_h':, 'prev_15_l':}}
        self.pcr_history = []

    def find_levels(self, df, symbol_type='underlying'):
        """Identify Swing Highs/Lows using find_peaks."""
        if df.empty or len(df) < 20: return []

        # Highs
        highs, _ = find_peaks(df['h'].values, distance=5)
        # Lows (negative peaks)
        lows, _ = find_peaks(-df['l'].values, distance=5)

        levels = sorted(list(set(df['h'].iloc[highs].tolist() + df['l'].iloc[lows].tolist())))
        if symbol_type == 'underlying':
            self.underlying_levels = levels
        return levels

    def calculate_volume_profile(self, ticks):
        """Calculate High Volume Nodes (HVN)."""
        if not ticks: return []

        df = pd.DataFrame(ticks)
        if 'last_price' not in df.columns or 'ltq' not in df.columns:
            return []

        # Group by price and sum volume
        vp = df.groupby('last_price')['ltq'].sum().sort_values(ascending=False)
        # Top 3 HVNs
        self.hvn_levels = vp.head(3).index.tolist()
        return self.hvn_levels

    def update_option_levels(self, symbol, df_1m):
        """Track ORB and Previous 15-min High/Low."""
        if df_1m.empty: return

        # ORB (First 15 mins of day)
        # For simplicity, assume df_1m starts at market open or has enough history
        # In real-time, we'd check if current time is > 9:30 AM
        orb_df = df_1m.iloc[:15]
        orb_h = orb_df['h'].max()
        orb_l = orb_df['l'].min()

        # Prev 15 min
        prev_15 = df_1m.iloc[-16:-1] if len(df_1m) > 16 else df_1m
        p15_h = prev_15['h'].max()
        p15_l = prev_15['l'].min()

        self.option_levels[symbol] = {
            'orb_h': orb_h, 'orb_l': orb_l,
            'p15_h': p15_h, 'p15_l': p15_l,
            'last_swing_h': df_1m['h'].iloc[-5:].max(),
            'last_swing_l': df_1m['l'].iloc[-5:].min()
        }

    def is_in_signal_zone(self, price):
        """Underlying within 0.05% of a major level."""
        major_levels = self.underlying_levels + self.hvn_levels
        for level in major_levels:
            if abs(price - level) / level <= 0.0005:
                return True, level
        return False, None

    def calculate_pcr(self, chain_data):
        """Calculate live PCR based on the total OI of the nearest 5 strikes."""
        if not chain_data: return 0

        # Assume chain_data is a list of strike objects with 'oi', 'option_type', 'strike'
        # Sort by proximity to current spot
        spot = self.scalper.current_spot
        chain_data.sort(key=lambda x: abs(x['strike'] - spot))

        nearest_5 = chain_data[:10] # 5 strikes * 2 (call/put)
        call_oi = sum(x['oi'] for x in nearest_5 if x['option_type'] == 'call')
        put_oi = sum(x['oi'] for x in nearest_5 if x['option_type'] == 'put')

        pcr = put_oi / call_oi if call_oi > 0 else 0
        self.pcr_history.append(pcr)
        if len(self.pcr_history) > 60: self.pcr_history.pop(0)
        return pcr

    def get_oi_spurt(self, current_chain, prev_chain):
        """Monitor Change in OI for spurts."""
        spurts = {'call': 0, 'put': 0}

        for curr in current_chain:
            # Find same strike in prev_chain
            prev = next((x for x in prev_chain if x['strike'] == curr['strike'] and x['option_type'] == curr['option_type']), None)
            if prev:
                change = curr['oi'] - prev['oi']
                spurts[curr['option_type']] += change

        return spurts

    def get_buildup_status(self, price_change, oi_change):
        """Identify buildup type based on price and OI correlation."""
        if price_change > 0 and oi_change > 0: return "LONG_BUILDUP"
        if price_change > 0 and oi_change < 0: return "SHORT_COVERING"
        if price_change < 0 and oi_change > 0: return "SHORT_BUILDUP"
        if price_change < 0 and oi_change < 0: return "LONG_UNWINDING"
        return "NEUTRAL"

class ExecutionManager:
    """Handles order execution and risk management."""
    def __init__(self, scalper):
        self.scalper = scalper
        self.active_trades = [] # List of trade dicts
        self.trades_file = "trades.csv"
        self.risk_per_trade = 2000 # INR

    def execute_buy(self, symbol, side, entry_price, sl_level):
        """Execute a Buy order with limit price + jumper."""
        jumper = 0.50
        limit_price = entry_price + jumper

        # Simple quantity calculation based on risk
        # Risk = (Entry - SL) * Qty
        risk_amount = abs(entry_price - sl_level)
        if risk_amount == 0: risk_amount = entry_price * 0.15 # Fallback to 15%

        quantity = int(self.risk_per_trade / risk_amount)
        if quantity == 0: quantity = 1

        trade = {
            'symbol': symbol,
            'side': side, # 'CALL' or 'PUT'
            'entry_price': entry_price,
            'limit_price': limit_price,
            'sl': sl_level,
            'tp': entry_price + (risk_amount * 2.5),
            'quantity': quantity,
            'entry_time': datetime.now(),
            'last_price': entry_price,
            'max_price': entry_price,
            'status': 'OPEN',
            'be_moved': False,
            'underlying_entry': self.scalper.current_spot
        }

        self.active_trades.append(trade)
        self.scalper.log(f"BUY {side} {symbol} @ {limit_price} | Qty: {quantity} | SL: {trade['sl']} | TP: {trade['tp']}")
        return trade

    def manage_risk(self):
        """Manage open trades: SL, TP, Trailing, Theta protection."""
        for trade in self.active_trades[:]:
            current_tick = self.scalper.last_ticks.get('atm_call' if trade['side'] == 'CALL' else 'atm_put')
            if not current_tick: continue

            price = current_tick['last_price']
            trade['last_price'] = price
            trade['max_price'] = max(trade['max_price'], price)

            # 1. Target Hit
            if price >= trade['tp']:
                self._close_trade(trade, "TARGET HIT")
                continue

            # 2. Stop Loss Hit
            if price <= trade['sl']:
                self._close_trade(trade, "SL HIT")
                continue

            # 3. Trailing SL (Move to BE after +10%)
            if not trade['be_moved'] and (price - trade['entry_price']) / trade['entry_price'] >= 0.10:
                trade['sl'] = trade['entry_price']
                trade['be_moved'] = True
                self.scalper.log(f"Trailing SL moved to Break-even for {trade['side']}")

            # 4. Theta Protection (3 min inactivity)
            elapsed = (datetime.now() - trade['entry_time']).total_seconds()
            if elapsed > 180: # 3 minutes
                # Check if underlying moved in favor
                curr_spot = self.scalper.current_spot
                entry_spot = trade.get('underlying_entry', 0)
                underlying_in_favor = (curr_spot > entry_spot) if trade['side'] == 'CALL' else (curr_spot < entry_spot)

                # If underlying moved in favor but premium did not move by > 1%
                if underlying_in_favor and (price - trade['entry_price']) / trade['entry_price'] < 0.01:
                    self._close_trade(trade, "THETA PROTECTION")
                    continue

    def _close_trade(self, trade, reason):
        trade['status'] = 'CLOSED'
        trade['exit_price'] = trade['last_price']
        trade['exit_time'] = datetime.now()
        trade['pnl'] = (trade['exit_price'] - trade['entry_price']) * trade['quantity']

        self.scalper.log(f"CLOSE {trade['side']} @ {trade['exit_price']} | Reason: {reason} | PnL: {trade['pnl']}")
        self.log_trade(trade)
        self.active_trades.remove(trade)

    def log_trade(self, trade):
        """Save trade to trades.csv."""
        file_exists = os.path.isfile(self.trades_file)

        try:
            with open(self.trades_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'symbol', 'side', 'entry_price', 'limit_price', 'sl', 'tp',
                    'quantity', 'entry_time', 'exit_price', 'exit_time', 'status', 'pnl'
                ])
                if not file_exists:
                    writer.writeheader()

                # Create a copy for logging
                log_data = {k: trade.get(k) for k in writer.fieldnames}
                writer.writerow(log_data)
        except Exception as e:
            logger.error(f"Error logging trade to CSV: {e}")

class NSEConfluenceScalper:
    """Main orchestrator for the NSE Confluence-Based Option Buying Scalper."""
    def __init__(self, underlying="NSE:NIFTY"):
        self.underlying = underlying
        self.is_running = False
        self.streamer = DataStreamer(self)
        self.engine = ConfluenceEngine(self)
        self.executor = ExecutionManager(self)
        self.sio = None
        self.loop = None
        self.current_spot = 0
        self.last_ticks = {} # target -> last tick
        self.prev_chain = []

    def set_socketio(self, sio, loop):
        self.sio = sio
        self.loop = loop

    def log(self, message):
        ist = pytz.timezone('Asia/Kolkata')
        timestamp = datetime.now(ist).strftime("%H:%M:%S")
        formatted_msg = f"[{timestamp}] {message}"
        logger.info(formatted_msg)
        if self.sio and self.loop:
            asyncio.run_coroutine_threadsafe(
                self.sio.emit('scalper_log', {'message': formatted_msg}),
                self.loop
            )

    async def start(self):
        if self.is_running: return
        self.is_running = True
        self.log(f"Starting Scalper for {self.underlying}...")
        await self.streamer.subscribe(self.underlying)
        asyncio.create_task(self._main_loop())

    def _handle_wss_message(self, data):
        if data.get('type') == 'live_feed':
            for inst_key, tick in data.get('feeds', {}).items():
                self.streamer.on_tick(inst_key, tick)
        elif data.get('type') == 'chart_update':
            self.streamer.on_ohlcv(data.get('instrumentKey'), data.get('data'))

    async def stop(self):
        self.is_running = False
        self.log("Stopping Scalper...")

    async def _main_loop(self):
        while self.is_running:
            try:
                # 1. Check for Signals
                self._check_signals()

                # 2. Manage Active Trades
                self.executor.manage_risk()

            except Exception as e:
                logger.error(f"Error in scalper main loop: {e}")

            await asyncio.sleep(0.5) # High speed cycle

    def _check_signals(self):
        if len(self.executor.active_trades) > 0: return # Only one trade at a time

        # 1. Level Hunting (Technical + OI)
        spot = self.current_spot
        in_zone, level = self.engine.is_in_signal_zone(spot)

        # Also check OI based levels
        oi_levels = options_manager.get_support_resistance(self.underlying)
        sup_oi = [x['strike'] for x in oi_levels.get('support_levels', [])]
        res_oi = [x['strike'] for x in oi_levels.get('resistance_levels', [])]

        # 2. OI/PCR Check
        chain_res = options_manager.get_chain_with_greeks(self.underlying)
        chain_data = chain_res.get('chain', [])
        # Fallback to chain_res['spot_price'] if self.current_spot is 0
        if spot == 0: spot = chain_res.get('spot_price', 0)

        if not chain_data: return

        pcr = self.engine.calculate_pcr(chain_data)

        # OI Spurts
        spurts = {'call': 0, 'put': 0}
        if self.prev_chain:
            spurts = self.engine.get_oi_spurt(chain_data, self.prev_chain)
        self.prev_chain = chain_data

        # Determine trend from PCR
        if len(self.engine.pcr_history) < 2: return
        pcr_rising = self.engine.pcr_history[-1] > self.engine.pcr_history[-2]

        # Price-OI Correlation
        price_chg = 0
        if len(self.streamer.tick_buffer) >= 2:
            price_chg = self.streamer.tick_buffer[-1]['last_price'] - self.streamer.tick_buffer[-2]['last_price']

        net_spurt = spurts['put'] - spurts['call']
        oi_status = self.engine.get_buildup_status(price_chg, net_spurt)

        # Bullish/Bearish Confirmation
        bullish_oi = (pcr_rising and spurts['put'] > spurts['call']) or (oi_status in ["LONG_BUILDUP", "SHORT_COVERING"])
        bearish_oi = (not pcr_rising and spurts['call'] > spurts['put']) or (oi_status in ["SHORT_BUILDUP", "LONG_UNWINDING"])

        # 3. Instrument data
        call_sym = self.streamer.symbols.get('atm_call')
        put_sym = self.streamer.symbols.get('atm_put')
        call_levels = self.engine.option_levels.get(call_sym, {})
        put_levels = self.engine.option_levels.get(put_sym, {})
        call_tick = self.last_ticks.get('atm_call')
        put_tick = self.last_ticks.get('atm_put')

        if not call_tick or not put_tick or not call_levels or not put_levels: return

        call_vwap = self.streamer.vwap.get('atm_call', 0)
        put_vwap = self.streamer.vwap.get('atm_put', 0)

        # Bullish/Bearish Condition Checks
        is_at_support = (in_zone and spot <= level * 1.0005) or any(abs(spot-s)/s < 0.0005 for s in sup_oi)
        is_brk_resistance = (in_zone and spot >= level * 0.9995) or any(abs(spot-r)/r < 0.0005 for r in res_oi)

        # Breakout Levels: Must break above Recent Swing High AND VWAP AND ORB High AND Prev 15m High
        # We use max of these as the hurdle to ensure a true breakout
        call_brk = call_tick['last_price'] > max(call_levels.get('last_swing_h', 0), call_vwap, call_levels.get('p15_h', 0), call_levels.get('orb_h', 0))
        put_brk_dwn = put_tick['last_price'] < min(put_levels.get('last_swing_l', 999999), put_levels.get('p15_l', 999999), put_levels.get('orb_l', 999999))

        put_brk = put_tick['last_price'] > max(put_levels.get('last_swing_h', 0), put_vwap, put_levels.get('p15_h', 0), put_levels.get('orb_h', 0))
        call_brk_dwn = call_tick['last_price'] < min(call_levels.get('last_swing_l', 999999), call_levels.get('p15_l', 999999), call_levels.get('orb_l', 999999))

        # Confluence metrics for UI
        oi_conf = "BULLISH" if bullish_oi else "BEARISH" if bearish_oi else "NEUTRAL"

        if self.sio and self.loop:
            oi_power = "STRONG" if abs(net_spurt) > 500000 else "MODERATE" if abs(net_spurt) > 100000 else "WEAK"
            asyncio.run_coroutine_threadsafe(
                self.sio.emit('scalper_metrics', {
                    'pcr': round(pcr, 2),
                    'oi_power': oi_power,
                    'oi_sentiment': oi_conf,
                    'oi_status': oi_status,
                    'underlying_level': level or (sup_oi[0] if sup_oi else 0),
                    'vwap': {
                        'call': round(call_vwap, 2),
                        'put': round(put_vwap, 2)
                    },
                    'oi_levels': {
                        'support': sup_oi[:2],
                        'resistance': res_oi[:2]
                    },
                    'confluence': {
                        'lvl': is_at_support or is_brk_resistance,
                        'pcr': pcr_rising,
                        'oi': spurts['put'] > spurts['call'] if bullish_oi else spurts['call'] > spurts['put'],
                        'opt_brk': call_brk if bullish_oi else put_brk,
                        'inv_dwn': put_brk_dwn if bullish_oi else call_brk_dwn
                    }
                }),
                self.loop
            )

        # Bullish Signal (CALL Buying)
        if (is_at_support or is_brk_resistance) and bullish_oi:
            if call_brk and put_brk_dwn:
                self.log(f"[SIGNAL] BULLISH CONFLUENCE - BUYING CALL @ {call_tick['last_price']}")
                self.executor.execute_buy(call_sym, 'CALL', call_tick['last_price'], call_levels['last_swing_l'])

        # Bearish Signal (PUT Buying)
        elif (is_at_support or is_brk_resistance) and bearish_oi:
            # Put Option breaks local Swing High OR VWAP
            put_brk = put_tick['last_price'] > max(put_levels['last_swing_h'], put_vwap if put_vwap > 0 else 0)
            # Call Option breaking down below local Swing Low
            call_brk_dwn = call_tick['last_price'] < call_levels['last_swing_l']

            if put_brk and call_brk_dwn:
                self.log(f"[SIGNAL] BEARISH CONFLUENCE - BUYING PUT @ {put_tick['last_price']}")
                self.executor.execute_buy(put_sym, 'PUT', put_tick['last_price'], put_levels['last_swing_l'])

# Global instance
scalper = NSEConfluenceScalper()
