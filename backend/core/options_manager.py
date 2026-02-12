"""
Enhanced Options Manager Module
Integrates Greeks, IV Analysis, OI Buildup, Strategy Builder, and Alerts
"""

import asyncio
import logging
import json
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd

from config import OPTIONS_UNDERLYINGS, SNAPSHOT_CONFIG
from db.local_db import db
from core.interfaces import ILiveStreamProvider
from core.provider_registry import options_data_registry, historical_data_registry
from external.tv_options_wss import OptionsWSS

# Import new modules
from core.greeks_calculator import greeks_calculator
from core.iv_analyzer import iv_analyzer
from core.oi_buildup_analyzer import oi_buildup_analyzer
from core.strategy_builder import strategy_builder
from core.alert_system import alert_system

logger = logging.getLogger(__name__)


class OptionsManager:
    """
    Enhanced Options Manager with comprehensive analysis features.
    
    New Features:
    - Real-time Greeks calculation
    - IV Rank and Percentile tracking
    - OI Buildup pattern detection
    - Strategy builder integration
    - Alert system integration
    """
    
    def __init__(self):
        self.active_underlyings = OPTIONS_UNDERLYINGS
        self.tl_symbol_map = {
            "NSE:NIFTY": "NIFTY 50",
            "NSE:BANKNIFTY": "BANKNIFTY",
            "NSE:FINNIFTY": "FINNIFTY"
        }
        self.running = False
        self._task = None
        self.wss_clients: Dict[str, ILiveStreamProvider] = {}
        self.latest_chains: Dict[str, Dict[str, Any]] = {}
        self.symbol_map_cache: Dict[str, Dict[str, str]] = {}
        self.sio = None
        self.loop = None
        
        # New feature: Store previous chain data for buildup analysis
        self.previous_chains: Dict[str, List[Dict[str, Any]]] = {}
        
        # New feature: IV tracking per underlying
        self.iv_history: Dict[str, List[float]] = {}
        
    def set_socketio(self, sio, loop=None):
        self.sio = sio
        self.loop = loop
        
        # Register alert callback
        alert_system.register_callback(self._on_alert_triggered)
    
    def _on_alert_triggered(self, alert_data: Dict[str, Any]):
        """Handle triggered alerts."""
        if self.sio:
            asyncio.run_coroutine_threadsafe(
                self.sio.emit('options_alert', alert_data),
                self.loop
            )
    
    async def start(self):
        if self.running:
            return
        self.running = True
        
        # Initialize symbols cache
        for underlying in self.active_underlyings:
            try:
                await self._refresh_wss_symbols(underlying)
            except Exception as e:
                logger.error(f"Error initializing symbols for {underlying}: {e}")
        
        # Trigger backfill in background
        asyncio.create_task(self.backfill_today())
        
        self._task = asyncio.create_task(self._snapshot_loop())
        
        # Start WSS for active underlyings
        for underlying in self.active_underlyings:
            self.start_wss(underlying)
        
        # Create preset alerts
        for underlying in self.active_underlyings:
            alert_system.create_preset_alerts(underlying)
        
        logger.info("Enhanced Options management started")
    
    async def backfill_today(self):
        """Backfill today's (or most recent) options data with enhanced metrics."""
        logger.info("Starting enhanced options backfill...")
        
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)

        # If weekend, go back to Friday
        if now.weekday() == 5: # Saturday
            now = now - timedelta(days=1)
        elif now.weekday() == 6: # Sunday
            now = now - timedelta(days=2)

        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # If before market open, try previous day
        if now < market_open:
            now = now - timedelta(days=1)
            # Skip if previous day was weekend
            if now.weekday() == 5: now = now - timedelta(days=1)
            if now.weekday() == 6: now = now - timedelta(days=2)
            market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
            market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
            logger.info(f"Market not open yet. Trying backfill for {now.strftime('%Y-%m-%d')}")

        end_time = min(datetime.now(ist), market_close)
        current = market_open
        time_slots = []
        backfill_interval = SNAPSHOT_CONFIG.get('backfill_interval_minutes', 5)
        while current <= end_time:
            time_slots.append(current.strftime("%H:%M"))
            current += timedelta(minutes=backfill_interval)
        
        if not time_slots:
            logger.warning("No time slots to backfill.")
            return
        
        target_date_str = now.strftime('%Y-%m-%d')

        for underlying in self.active_underlyings:
            tl_symbol = self.tl_symbol_map.get(underlying)
            try:
                logger.info(f"Processing backfill for {underlying} on {target_date_str}")
                
                # Check if already backfilled for this date
                existing = db.query(
                    "SELECT COUNT(*) as count FROM pcr_history WHERE underlying = ? AND CAST(timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS DATE) = ?",
                    (underlying, target_date_str)
                )
                if existing and existing[0]['count'] > (len(time_slots) * 0.8):
                    logger.info(f"Sufficient data already exists for {underlying} on {target_date_str}, skipping.")
                    continue
                
                # Get historical spot prices using primary historical provider
                hist_provider = historical_data_registry.get_primary()
                hist_spot = await hist_provider.get_hist_candles(underlying, '5', 300)
                spot_map = {c[0]: c[4] for c in hist_spot} if hist_spot else {}
                
                # Use primary options provider
                opt_provider = options_data_registry.get_primary()
                expiries = await opt_provider.get_expiry_dates(underlying)
                if not expiries:
                    continue
                default_expiry = expiries[0]
                
                for ts_str in time_slots:
                    data = await opt_provider.get_oi_data(underlying, default_expiry, ts_str)
                    if not data or data.get('head', {}).get('status') != '0':
                        continue
                    
                    body = data.get('body', {})
                    oi_data = body.get('oiData', {})
                    
                    ist_dt = now.replace(
                        hour=int(ts_str.split(':')[0]),
                        minute=int(ts_str.split(':')[1]),
                        second=0, microsecond=0
                    )
                    snapshot_time = ist_dt.astimezone(pytz.utc)
                    unix_ts = int(ist_dt.timestamp())
                    
                    # Find closest spot price
                    spot_price = spot_map.get(unix_ts, 0)
                    if not spot_price:
                        sorted_ts = sorted(spot_map.keys())
                        for ts in sorted_ts:
                            if ts <= unix_ts:
                                spot_price = spot_map[ts]
                    
                    # Process chain data with enhanced metrics
                    rows = self._process_chain_data(
                        oi_data, underlying, snapshot_time, default_expiry, spot_price
                    )
                    
                    if rows:
                        db.insert_options_snapshot(rows)
                        await self._calculate_pcr(underlying, snapshot_time, rows, spot_price)
                
                logger.info(f"Backfill complete for {underlying}")
                await asyncio.sleep(1)
                
            except Exception as e:
                logger.error(f"Error backfilling {underlying}: {e}")
    
    def _process_chain_data(
        self,
        oi_data: Dict[str, Any],
        underlying: str,
        timestamp: datetime,
        expiry: str,
        spot_price: float
    ) -> List[Dict[str, Any]]:
        """Process chain data with Greeks calculation."""
        rows = []
        
        # Robust date parsing
        expiry_date = None
        if isinstance(expiry, str):
            for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
                try:
                    expiry_date = datetime.strptime(expiry, fmt).date()
                    break
                except:
                    continue

        if not expiry_date:
             return []

        today = datetime.now(pytz.timezone('Asia/Kolkata')).date()
        days_to_expiry = max((expiry_date - today).days, 0)
        time_to_expiry = days_to_expiry / 365.0
        
        for strike_str, strike_data in oi_data.items():
            strike = float(strike_str)
            call_sym = self.symbol_map_cache.get(underlying, {}).get(f"{strike}_call")
            put_sym = self.symbol_map_cache.get(underlying, {}).get(f"{strike}_put")
            
            # Call option data
            call_ltp = float(strike_data.get('callLtp', 0) or strike_data.get('callLastPrice', 0))
            call_oi = int(strike_data.get('callOi', 0))
            call_oi_change = int(strike_data.get('callOiChange', 0))
            
            # Calculate Greeks for call
            call_greeks = greeks_calculator.calculate_all_greeks(
                spot_price, strike, time_to_expiry, 0.20, 'call', call_ltp
            )
            
            rows.append({
                'timestamp': timestamp,
                'underlying': underlying,
                'symbol': call_sym,
                'expiry': expiry_date,
                'strike': strike,
                'option_type': 'call',
                'oi': call_oi,
                'oi_change': call_oi_change,
                'volume': int(strike_data.get('callVol', 0) or strike_data.get('callVolume', 0)),
                'ltp': call_ltp,
                'iv': call_greeks['implied_volatility'],
                'delta': call_greeks['delta'],
                'gamma': call_greeks['gamma'],
                'theta': call_greeks['theta'],
                'vega': call_greeks['vega'],
                'intrinsic_value': call_greeks['intrinsic_value'],
                'time_value': call_greeks['time_value'],
                'source': 'backfill'
            })
            
            # Put option data
            put_ltp = float(strike_data.get('putLtp', 0) or strike_data.get('putLastPrice', 0))
            put_oi = int(strike_data.get('putOi', 0))
            put_oi_change = int(strike_data.get('putOiChange', 0))
            
            # Calculate Greeks for put
            put_greeks = greeks_calculator.calculate_all_greeks(
                spot_price, strike, time_to_expiry, 0.20, 'put', put_ltp
            )
            
            rows.append({
                'timestamp': timestamp,
                'underlying': underlying,
                'symbol': put_sym,
                'expiry': expiry_date,
                'strike': strike,
                'option_type': 'put',
                'oi': put_oi,
                'oi_change': put_oi_change,
                'volume': int(strike_data.get('putVol', 0) or strike_data.get('putVolume', 0)),
                'ltp': put_ltp,
                'iv': put_greeks['implied_volatility'],
                'delta': put_greeks['delta'],
                'gamma': put_greeks['gamma'],
                'theta': put_greeks['theta'],
                'vega': put_greeks['vega'],
                'intrinsic_value': put_greeks['intrinsic_value'],
                'time_value': put_greeks['time_value'],
                'source': 'backfill'
            })
        
        return rows
    
    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        for wss in self.wss_clients.values():
            wss.stop()
        self.wss_clients.clear()
        
        logger.info("Options management stopped")
    
    def start_wss(self, underlying: str):
        if underlying in self.wss_clients:
            return
        
        def on_data(data):
            self.handle_wss_data(underlying, data)
        
        wss = OptionsWSS(underlying, on_data)
        wss.start()
        self.wss_clients[underlying] = wss
    
    def handle_wss_data(self, underlying: str, data: Any):
        symbol = data.get('symbol')
        if not symbol:
            return
        
        if underlying not in self.latest_chains:
            self.latest_chains[underlying] = {}
        
        existing = self.latest_chains[underlying].get(symbol, {})
        for k, v in data.items():
            if v is not None:
                existing[k] = v
        self.latest_chains[underlying][symbol] = existing
        
        if self.sio:
            event_data = {
                'underlying': underlying,
                'symbol': symbol,
                'lp': data.get('lp'),
                'volume': data.get('volume'),
                'bid': data.get('bid'),
                'ask': data.get('ask')
            }
            
            async def emit():
                try:
                    await self.sio.emit('options_quote_update', event_data, room=f"options_{underlying}")
                except Exception as e:
                    logger.error(f"Error emitting options quote: {e}")
            
            if self.loop:
                asyncio.run_coroutine_threadsafe(emit(), self.loop)
    
    def is_market_open(self):
        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        if now.weekday() >= 5:
            return False
        start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return start <= now <= end
    
    async def _snapshot_loop(self):
        while self.running:
            if self.is_market_open():
                for underlying in self.active_underlyings:
                    try:
                        await self.take_snapshot(underlying)
                    except Exception as e:
                        logger.error(f"Error taking snapshot for {underlying}: {e}")
            await asyncio.sleep(180)
    
    async def take_snapshot(self, underlying: str):
        """Take enhanced snapshot with all metrics."""
        tl_symbol = self.tl_symbol_map.get(underlying)
        if not tl_symbol:
            return
        
        spot_price = await self.get_spot_price(underlying)
        
        try:
            if underlying not in self.symbol_map_cache or not self.symbol_map_cache[underlying]:
                await self._refresh_wss_symbols(underlying)
            
            wss_data = self.latest_chains.get(underlying, {})
            
            oi_data, default_expiry, oi_source = await self._fetch_oi_data(underlying)
            
            if not oi_data:
                return await self._take_snapshot_tv(underlying)
            
            rows = self._process_oi_data(
                oi_data, underlying, default_expiry, wss_data, spot_price, oi_source
            )
            
            if rows:
                # Store previous chain for buildup analysis
                self.previous_chains[underlying] = rows.copy()
                
                db.insert_options_snapshot(rows)
                # Use the same timestamp as in rows
                snap_ts = rows[0]['timestamp'] if rows else datetime.now(pytz.utc)
                await self._calculate_pcr(underlying, snap_ts, rows, spot_price)
                
                # Check alerts
                self._check_alerts(underlying, rows, spot_price)
                
                logger.info(f"Saved enhanced {oi_source} snapshot for {underlying} with {len(rows)} rows")
                
        except Exception as e:
            logger.error(f"Error in taking snapshot for {underlying}: {e}")
            await self._take_snapshot_tv(underlying)
    
    async def get_spot_price(self, underlying: str) -> float:
        """Get current spot price with multi-layer fallback."""
        try:
            from core.symbol_mapper import symbol_mapper
            hrn = symbol_mapper.get_hrn(underlying)
            
            # Layer 1: Ticks Table (Live Feed)
            # Use explicit keys to avoid matching option symbols (e.g. NIFTY260217P...)
            target_keys = [underlying, underlying.replace(':', '|')]
            if hrn == "NIFTY":
                target_keys.extend(["NSE_INDEX|NIFTY 50", "NSE|NIFTY", "NIFTY"])
            elif hrn == "BANKNIFTY":
                target_keys.extend(["NSE_INDEX|NIFTY BANK", "NSE|BANKNIFTY", "BANKNIFTY"])
            elif hrn == "FINNIFTY":
                target_keys.extend(["NSE_INDEX|NIFTY FIN SERVICE", "NSE|CNXFINANCE", "FINNIFTY"])

            placeholders = ",".join(["?"] * len(target_keys))
            res = db.query(f"""
                SELECT price FROM ticks
                WHERE instrumentKey IN ({placeholders})
                ORDER BY ts_ms DESC LIMIT 1
            """, tuple(target_keys))
            
            if res and res[0]['price'] > 0:
                logger.info(f"Spot Price discovered from Ticks for {underlying}: {res[0]['price']}")
                return res[0]['price']

            # Layer 2: Historical Candles (Provider Registry)
            logger.info(f"Spot not in ticks for {underlying}, trying historical candles...")
            hist_provider = historical_data_registry.get_primary()
            hist = await hist_provider.get_hist_candles(underlying, '1', 5)
            if hist and len(hist) > 0:
                price = hist[0][4]  # Close of most recent candle
                if price > 0:
                    logger.info(f"Spot Price discovered from Hist Candles for {underlying}: {price}")
                    return price

            # Layer 3: PCR History (Last recorded price)
            logger.info(f"Hist candles failed for {underlying}, trying PCR history fallback...")
            last_pcr = db.query("""
                SELECT spot_price, underlying_price FROM pcr_history
                WHERE underlying = ? AND (spot_price > 0 OR underlying_price > 0)
                ORDER BY timestamp DESC LIMIT 1
            """, (underlying,))

            if last_pcr:
                price = last_pcr[0].get('spot_price') or last_pcr[0].get('underlying_price') or 0
                if price > 0:
                    logger.warning(f"Using STALE Spot Price from PCR History for {underlying}: {price}")
                    return price

            # Layer 4: Last known snapshot price
            logger.info(f"PCR history failed for {underlying}, trying last snapshot LTP...")
            last_snap = db.query("""
                SELECT ltp FROM options_snapshots
                WHERE underlying = ? AND ltp > 0
                ORDER BY timestamp DESC LIMIT 1
            """, (underlying,))
            if last_snap:
                logger.warning(f"Using STALE Spot Price from last Snapshot for {underlying}: {last_snap[0]['ltp']}")
                return last_snap[0]['ltp']

        except Exception as e:
            logger.error(f"Error in multi-layer spot discovery for {underlying}: {e}")
        
        logger.error(f"CRITICAL: Could not discover any Spot Price for {underlying}")
        return 0
    
    async def _fetch_oi_data(self, underlying: str) -> tuple:
        """Fetch OI data using Registry with automatic failover."""
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        ts_str = now_ist.strftime("%H:%M")
        
        for name, provider in options_data_registry.providers.items():
            try:
                expiries = await provider.get_expiry_dates(underlying)
                if expiries:
                    default_expiry = expiries[0]
                    data = await provider.get_oi_data(underlying, default_expiry, ts_str)
                    if data and data.get('head', {}).get('status') == '0':
                        oi_data = data.get('body', {}).get('oiData', {})
                        return oi_data, default_expiry, name
            except Exception as e:
                logger.warning(f"Provider {name} failed for {underlying}: {e}")
                continue

        return None, None, None
    
    def _process_oi_data(
        self,
        oi_data: Dict[str, Any],
        underlying: str,
        default_expiry: str,
        wss_data: Dict[str, Any],
        spot_price: float,
        name: str = "unknown"
    ) -> List[Dict[str, Any]]:
        """Process OI data with enhanced metrics."""
        rows = []
        timestamp = datetime.now(pytz.utc)
        
        # Robust date parsing
        expiry_date = None
        if isinstance(default_expiry, str):
            for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y"):
                try:
                    expiry_date = datetime.strptime(default_expiry, fmt).date()
                    break
                except:
                    continue
        
        # Calculate time to expiry
        if expiry_date:
            today = datetime.now(pytz.timezone('Asia/Kolkata')).date()
            days_to_expiry = max((expiry_date - today).days, 0)
            time_to_expiry = days_to_expiry / 365.0
        else:
            time_to_expiry = 0.03  # Default ~11 days
        
        for strike_str, strike_data in oi_data.items():
            strike = float(strike_str)
            c_sym = self.symbol_map_cache.get(underlying, {}).get(f"{strike}_call")
            p_sym = self.symbol_map_cache.get(underlying, {}).get(f"{strike}_put")
            c_wss = wss_data.get(c_sym, {}) if c_sym else {}
            p_wss = wss_data.get(p_sym, {}) if p_sym else {}
            
            # Call option
            call_ltp = c_wss.get('lp', 0.0) or float(strike_data.get('callLtp', 0) or 0)
            call_greeks = greeks_calculator.calculate_all_greeks(
                spot_price, strike, time_to_expiry, 0.20, 'call', call_ltp
            )
            
            rows.append({
                'timestamp': timestamp,
                'underlying': underlying,
                'symbol': c_sym,
                'expiry': expiry_date,
                'strike': strike,
                'option_type': 'call',
                'oi': int(strike_data.get('callOi', 0)),
                'oi_change': int(strike_data.get('callOiChange', 0)),
                'volume': c_wss.get('volume', 0) or int(strike_data.get('callVol', 0) or 0),
                'ltp': call_ltp,
                'iv': call_greeks['implied_volatility'],
                'delta': call_greeks['delta'],
                'gamma': call_greeks['gamma'],
                'theta': call_greeks['theta'],
                'vega': call_greeks['vega'],
                'intrinsic_value': call_greeks['intrinsic_value'],
                'time_value': call_greeks['time_value'],
                'source': name
            })
            
            # Put option
            put_ltp = p_wss.get('lp', 0.0) or float(strike_data.get('putLtp', 0) or 0)
            put_greeks = greeks_calculator.calculate_all_greeks(
                spot_price, strike, time_to_expiry, 0.20, 'put', put_ltp
            )
            
            rows.append({
                'timestamp': timestamp,
                'underlying': underlying,
                'symbol': p_sym,
                'expiry': expiry_date,
                'strike': strike,
                'option_type': 'put',
                'oi': int(strike_data.get('putOi', 0)),
                'oi_change': int(strike_data.get('putOiChange', 0)),
                'volume': p_wss.get('volume', 0) or int(strike_data.get('putVol', 0) or 0),
                'ltp': put_ltp,
                'iv': put_greeks['implied_volatility'],
                'delta': put_greeks['delta'],
                'gamma': put_greeks['gamma'],
                'theta': put_greeks['theta'],
                'vega': put_greeks['vega'],
                'intrinsic_value': put_greeks['intrinsic_value'],
                'time_value': put_greeks['time_value'],
                'source': name
            })
        
        return rows
    
    def _check_alerts(self, underlying: str, rows: List[Dict[str, Any]], spot_price: float):
        """Check and trigger alerts."""
        # Calculate PCR
        calls = [r for r in rows if r['option_type'] == 'call']
        puts = [r for r in rows if r['option_type'] == 'put']
        
        total_call_oi = sum(r['oi'] for r in calls)
        total_put_oi = sum(r['oi'] for r in puts)
        pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        
        # Prepare alert data
        alert_data = {
            'underlying': underlying,
            'price': spot_price,
            'pcr': round(pcr, 2),
            'timestamp': datetime.now(pytz.utc).isoformat()
        }
        
        # Check alerts
        triggered = alert_system.check_alerts(underlying, alert_data)
        
        if triggered:
            logger.info(f"Triggered {len(triggered)} alerts for {underlying}")
    
    async def _take_snapshot_tv(self, underlying: str):
        """Fallback to TradingView data via Registry."""
        # Use first provider that gives a chain (usually trendlyne or nse adapter)
        provider = options_data_registry.get_primary()
        data = await provider.get_option_chain(underlying)
        if not data or 'symbols' not in data:
            return
        
        spot_price = await self.get_spot_price(underlying)
        timestamp = datetime.now(pytz.utc)
        rows = []
        
        if underlying not in self.symbol_map_cache:
            self.symbol_map_cache[underlying] = {}
        
        for item in data['symbols']:
            f = item['f']
            try:
                symbol = f[0]
                strike = float(f[3]) if f[3] is not None else 0
                opt_type = str(f[2]).lower()
                volume = int(f[4]) if f[4] is not None else 0
                ltp = float(f[5]) if f[5] is not None else 0

                # Expiration and Greeks from augmented TV scanner columns
                expiration_val = f[6] if len(f) > 6 else None
                oi = 0 # OI not available in current TV scanner for NSE

                expiry_date = None
                time_to_expiry = 0.01 # Default ~4 days
                if expiration_val:
                    if isinstance(expiration_val, int) and expiration_val > 20000000:
                        try:
                            expiry_date = datetime.strptime(str(expiration_val), "%Y%m%d").date()
                        except:
                            pass

                    if not expiry_date:
                        try:
                            expiry_date = datetime.fromtimestamp(expiration_val, pytz.utc).date()
                        except:
                            pass

                    if expiry_date:
                        days_to_expiry = max((expiry_date - timestamp.date()).days, 0)
                        time_to_expiry = days_to_expiry / 365.0

                # Use Greeks from TV if available, else calculate
                tv_delta = f[9] if len(f) > 9 else None
                tv_gamma = f[10] if len(f) > 10 else None
                tv_iv = f[11] if len(f) > 11 else None
                tv_theta = f[13] if len(f) > 13 else None
                tv_vega = f[14] if len(f) > 14 else None

                if tv_iv is not None and tv_iv > 0:
                    greeks = {
                        'implied_volatility': tv_iv,
                        'delta': tv_delta or 0,
                        'gamma': tv_gamma or 0,
                        'theta': tv_theta or 0,
                        'vega': tv_vega or 0,
                        'intrinsic_value': 0, # Not provided by TV directly
                        'time_value': 0
                    }
                else:
                    greeks = greeks_calculator.calculate_all_greeks(
                        spot_price, strike, time_to_expiry, 0.20, opt_type, ltp
                    )
                
                self.symbol_map_cache[underlying][f"{strike}_{opt_type}"] = symbol
                
                rows.append({
                    'timestamp': timestamp,
                    'underlying': underlying,
                    'symbol': symbol,
                    'expiry': expiry_date,
                    'strike': strike,
                    'option_type': opt_type,
                    'oi': oi,
                    'oi_change': 0,
                    'volume': volume,
                    'ltp': ltp,
                    'iv': greeks['implied_volatility'],
                    'delta': greeks['delta'],
                    'gamma': greeks['gamma'],
                    'theta': greeks['theta'],
                    'vega': greeks['vega'],
                    'intrinsic_value': greeks.get('intrinsic_value', 0),
                    'time_value': greeks.get('time_value', 0),
                    'source': 'tradingview_fallback'
                })
            except Exception as e:
                logger.debug(f"Error parsing TV symbol {item}: {e}")
                continue
        
        if rows:
            db.insert_options_snapshot(rows)
            await self._calculate_pcr(underlying, timestamp, rows)
            logger.info(f"Saved TV snapshot for {underlying} with {len(rows)} rows")
            
            if underlying in self.wss_clients:
                atm_strike = sum(r['strike'] for r in rows) / len(rows) if rows else 0
                filtered_symbols = [
                    r['symbol'] for r in rows
                    if r['symbol'] and (atm_strike == 0 or abs(r['strike'] - atm_strike) / atm_strike < 0.05)
                ]
                self.wss_clients[underlying].add_symbols(filtered_symbols[:400])
    
    async def _refresh_wss_symbols(self, underlying: str):
        provider = options_data_registry.get_primary()
        data = await provider.get_option_chain(underlying)
        if data and 'symbols' in data:
            if underlying not in self.symbol_map_cache:
                self.symbol_map_cache[underlying] = {}
            
            all_symbols = []
            for item in data['symbols']:
                symbol = item['f'][0]
                strike = float(item['f'][3]) if item['f'][3] is not None else 0
                opt_type = str(item['f'][2]).lower()
                
                all_symbols.append(symbol)
                self.symbol_map_cache[underlying][f"{strike}_{opt_type}"] = symbol
            
            if underlying in self.wss_clients:
                self.wss_clients[underlying].add_symbols(all_symbols[:300])
    
    async def _calculate_pcr(self, underlying, timestamp, rows, spot_price=0):
        """Calculate PCR with enhanced metrics."""
        calls = [r for r in rows if r['option_type'] == 'call']
        puts = [r for r in rows if r['option_type'] == 'put']
        
        total_call_oi = sum(r['oi'] for r in calls)
        total_put_oi = sum(r['oi'] for r in puts)
        total_call_vol = sum(r['volume'] for r in calls)
        total_put_vol = sum(r['volume'] for r in puts)
        total_call_oi_chg = sum(r['oi_change'] for r in calls)
        total_put_oi_chg = sum(r['oi_change'] for r in puts)
        
        total_oi = total_call_oi + total_put_oi
        total_oi_change = total_call_oi_chg + total_put_oi_chg

        pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0
        pcr_oi_change = total_put_oi_chg / total_call_oi_chg if total_call_oi_chg != 0 else 0
        
        # Calculate max pain
        strikes = sorted(list(set(r['strike'] for r in rows)))
        min_pain = float('inf')
        max_pain = strikes[0] if strikes else 0
        
        for s in strikes:
            pain = 0
            for r in calls:
                if s > r['strike']:
                    pain += (s - r['strike']) * r['oi']
            for r in puts:
                if r['strike'] > s:
                    pain += (r['strike'] - s) * r['oi']
            if pain < min_pain:
                min_pain = pain
                max_pain = s
        
        # Get underlying price
        # We now rely on the robust spot_price discovery performed by the caller (take_snapshot)
        underlying_price = spot_price
        
        db.insert_pcr_history({
            'timestamp': timestamp,
            'underlying': underlying,
            'pcr_oi': pcr_oi,
            'pcr_vol': pcr_vol,
            'pcr_oi_change': pcr_oi_change,
            'underlying_price': underlying_price,
            'max_pain': max_pain,
            'spot_price': spot_price,
            'total_oi': total_oi,
            'total_oi_change': total_oi_change
        })
        
        # Track IV for analysis
        avg_iv = sum(r.get('iv', 0) for r in rows) / len(rows) if rows else 0
        if underlying not in self.iv_history:
            self.iv_history[underlying] = []
        self.iv_history[underlying].append(avg_iv)
        
        # Keep only last 252 data points
        self.iv_history[underlying] = self.iv_history[underlying][-252:]
    
    # New API methods for enhanced features
    
    def get_chain_with_greeks(self, underlying: str) -> Dict[str, Any]:
        """Get option chain with Greeks calculated."""
        latest_ts_res = db.query(
            "SELECT MAX(timestamp) as ts FROM options_snapshots WHERE underlying = ?",
            (underlying,)
        )
        
        if not latest_ts_res or latest_ts_res[0]['ts'] is None:
            return {"chain": []}
        
        latest_ts = latest_ts_res[0]['ts']
        chain = db.query(
            "SELECT * FROM options_snapshots WHERE underlying = ? AND timestamp = ? ORDER BY strike ASC",
            (underlying, latest_ts),
            json_serialize=True
        )

        source = chain[0].get('source', 'unknown') if chain else 'unknown'
        
        # Calculate PCR and Max Pain from this specific snapshot
        calls = [r for r in chain if r['option_type'] == 'call']
        puts = [r for r in chain if r['option_type'] == 'put']

        total_call_oi = sum(r.get('oi', 0) or 0 for r in calls)
        total_put_oi = sum(r.get('oi', 0) or 0 for r in puts)
        total_call_vol = sum(r.get('volume', 0) or 0 for r in calls)
        total_put_vol = sum(r.get('volume', 0) or 0 for r in puts)
        total_call_oi_chg = sum(r.get('oi_change', 0) or 0 for r in calls)
        total_put_oi_chg = sum(r.get('oi_change', 0) or 0 for r in puts)

        pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0
        pcr_oi_change = total_put_oi_chg / total_call_oi_chg if total_call_oi_chg != 0 else 0

        # Max Pain calculation
        strikes = sorted(list(set(r['strike'] for r in chain)))
        min_pain = float('inf')
        max_pain = strikes[0] if strikes else 0

        for s in strikes:
            pain = 0
            for r in calls:
                if s > r['strike']:
                    pain += (s - r['strike']) * (r.get('oi', 0) or 0)
            for r in puts:
                if r['strike'] > s:
                    pain += (r['strike'] - s) * (r.get('oi', 0) or 0)
            if pain < min_pain:
                min_pain = pain
                max_pain = s

        # Fetch spot price from pcr_history
        spot_res = db.query(
            "SELECT spot_price, underlying_price FROM pcr_history WHERE underlying = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
            (underlying, latest_ts)
        )
        spot_price = 0
        if spot_res:
            spot_price = spot_res[0].get('spot_price') or spot_res[0].get('underlying_price') or 0

        # Calculate aggregate Greeks
        net_delta = sum(item.get('delta', 0) * (item.get('oi', 0) or 0) for item in chain)
        net_theta = sum(item.get('theta', 0) * (item.get('oi', 0) or 0) for item in chain)

        return {
            "timestamp": latest_ts,
            "chain": chain,
            "spot_price": spot_price,
            "source": source,
            "net_delta": round(net_delta, 2),
            "net_theta": round(net_theta, 2),
            "pcr_oi": round(pcr_oi, 2),
            "pcr_vol": round(pcr_vol, 2),
            "pcr_oi_change": round(pcr_oi_change, 2),
            "max_pain": max_pain
        }
    
    def get_oi_buildup_analysis(self, underlying: str) -> Dict[str, Any]:
        """Get OI buildup analysis."""
        current_chain = self.get_chain_with_greeks(underlying).get('chain', [])
        previous_chain = self.previous_chains.get(underlying, [])
        
        return oi_buildup_analyzer.analyze_chain_buildup(current_chain, previous_chain)
    
    def get_iv_analysis(self, underlying: str) -> Dict[str, Any]:
        """Get IV analysis for underlying."""
        current_iv = 20.0  # Default
        
        if underlying in self.iv_history and self.iv_history[underlying]:
            current_iv = self.iv_history[underlying][-1]
        
        metrics = iv_analyzer.get_iv_metrics(underlying, current_iv)
        signal = iv_analyzer.get_iv_signal(metrics.iv_rank, metrics.iv_percentile)
        
        return {
            'current_iv': metrics.current_iv,
            'iv_rank': metrics.iv_rank,
            'iv_percentile': metrics.iv_percentile,
            'iv_52w_high': metrics.iv_52w_high,
            'iv_52w_low': metrics.iv_52w_low,
            'iv_20d_avg': metrics.iv_20d_avg,
            'signal': signal
        }
    
    def get_support_resistance(self, underlying: str) -> Dict[str, Any]:
        """Get support and resistance levels based on OI."""
        chain = self.get_chain_with_greeks(underlying).get('chain', [])
        return oi_buildup_analyzer.get_support_resistance_from_oi(chain)

    async def get_price_boundaries(self, underlying: str) -> Dict[str, Any]:
        """Calculates the realistic price boundaries for the day."""
        spot = await self.get_spot_price(underlying)
        if spot == 0: return {"lower": 0, "upper": 0}

        # Using 1% as a default daily IV for boundary calculation if historical not available
        # Boundaries = Spot * (1 +/- IV * sqrt(1/365))
        # For NIFTY, 1% daily move is a reasonable "realistic" boundary
        daily_iv = 0.01

        upper = spot * (1 + daily_iv)
        lower = spot * (1 - daily_iv)

        # Fine tune with OI concentrations
        sr = self.get_support_resistance(underlying)
        if sr.get('resistance_levels'):
            upper = min(upper, sr['resistance_levels'][0]['strike'])
        if sr.get('support_levels'):
            lower = max(lower, sr['support_levels'][0]['strike'])

        return {
            "lower": round(lower, 2),
            "upper": round(upper, 2),
            "spot": spot
        }

    def get_high_activity_strikes(self, underlying: str) -> List[Dict[str, Any]]:
        """Highlights strikes with maximum OI, volume, and activity."""
        chain = self.get_chain_with_greeks(underlying).get('chain', [])
        if not chain: return []

        # Sort by Net Score: OI + Volume + |OI Change|
        scored = []
        for item in chain:
            score = item.get('oi', 0) + item.get('volume', 0) + abs(item.get('oi_change', 0))
            scored.append({**item, 'activity_score': score})

        top_active = sorted(scored, key=lambda x: x['activity_score'], reverse=True)
        return top_active[:5]

    async def get_genie_insights(self, underlying: str) -> Dict[str, Any]:
        """Consolidated Genie insights for the dashboard."""
        chain_res = self.get_chain_with_greeks(underlying)
        chain = chain_res.get('chain', [])
        spot = chain_res.get('spot_price', 0)

        distribution = oi_buildup_analyzer.detect_institutional_distribution(chain, spot)
        control = oi_buildup_analyzer.detect_market_control(chain)

        # Fetch history for sideways prediction
        history_res = db.query(
            "SELECT spot_price, underlying_price FROM pcr_history WHERE underlying = ? ORDER BY timestamp DESC LIMIT 10",
            (underlying,)
        )
        sideways = oi_buildup_analyzer.predict_sideways_session(history_res)

        boundaries = await self.get_price_boundaries(underlying)

        return {
            "distribution": distribution,
            "control": control,
            "sideways_expected": sideways,
            "boundaries": boundaries,
            "sentiment": "BULLISH" if control == "BUYERS_IN_CONTROL" else "BEARISH" if control == "SELLERS_IN_CONTROL" else "NEUTRAL",
            "pcr": chain_res.get('pcr_oi', 0)
        }


# Global instance
options_manager = OptionsManager()
