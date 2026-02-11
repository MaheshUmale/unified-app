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

from config import OPTIONS_UNDERLYINGS
from external.tv_options_scanner import fetch_option_chain
from external.tv_options_wss import OptionsWSS
from external.trendlyne_api import trendlyne_api
from external.nse_api import fetch_nse_oi_data
from external.tv_api import tv_api
from db.local_db import db

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
        self.wss_clients: Dict[str, OptionsWSS] = {}
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
        while current <= end_time:
            time_slots.append(current.strftime("%H:%M"))
            current += timedelta(minutes=15)
        
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
                
                # Get historical spot prices
                hist_spot = await asyncio.to_thread(tv_api.get_hist_candles, underlying, '15', 100)
                spot_map = {c[0]: c[4] for c in hist_spot} if hist_spot else {}
                
                stock_id = await trendlyne_api.get_stock_id(tl_symbol)
                if not stock_id:
                    continue
                
                expiries = await trendlyne_api.get_expiry_dates(stock_id)
                if not expiries:
                    continue
                default_expiry = expiries[0]
                
                for ts_str in time_slots:
                    data = await trendlyne_api.get_oi_data(stock_id, default_expiry, ts_str)
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
        
        # Calculate days to expiry
        expiry_date = datetime.strptime(expiry, "%Y-%m-%d").date()
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
                'time_value': call_greeks['time_value']
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
                'time_value': put_greeks['time_value']
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
        
        spot_price = await self._get_spot_price(underlying)
        
        try:
            if underlying not in self.symbol_map_cache or not self.symbol_map_cache[underlying]:
                await self._refresh_wss_symbols(underlying)
            
            wss_data = self.latest_chains.get(underlying, {})
            stock_id = await trendlyne_api.get_stock_id(tl_symbol)
            
            oi_data, default_expiry, oi_source = await self._fetch_oi_data(
                underlying, stock_id, tl_symbol
            )
            
            if not oi_data:
                return await self._take_snapshot_tv(underlying)
            
            rows = self._process_oi_data(
                oi_data, underlying, default_expiry, wss_data, spot_price
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
    
    async def _get_spot_price(self, underlying: str) -> float:
        """Get current spot price with multi-layer fallback."""
        try:
            from core.symbol_mapper import symbol_mapper
            hrn = symbol_mapper.get_hrn(underlying)
            
            # Layer 1: Ticks Table (Live Feed)
            res = db.query("""
                SELECT price FROM ticks
                WHERE instrumentKey IN (?, ?, ?)
                OR instrumentKey LIKE ?
                ORDER BY ts_ms DESC LIMIT 1
            """, (
                underlying,
                underlying.replace(':', '|'),
                "NSE_INDEX|NIFTY 50" if hrn == "NIFTY" else "NSE_INDEX|NIFTY BANK" if hrn == "BANKNIFTY" else hrn,
                f"%{hrn}%"
            ))
            
            if res and res[0]['price'] > 0:
                logger.info(f"Spot Price discovered from Ticks for {underlying}: {res[0]['price']}")
                return res[0]['price']

            # Layer 2: Historical Candles (TradingView API/Scraper)
            logger.info(f"Spot not in ticks for {underlying}, trying historical candles...")
            hist = await asyncio.to_thread(tv_api.get_hist_candles, underlying, '1', 5)
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
    
    async def _fetch_oi_data(
        self,
        underlying: str,
        stock_id: Optional[str],
        tl_symbol: str
    ) -> tuple:
        """Fetch OI data from available sources."""
        oi_data = None
        default_expiry = None
        oi_source = "trendlyne"
        
        ist = pytz.timezone('Asia/Kolkata')
        now_ist = datetime.now(ist)
        ts_str = now_ist.strftime("%H:%M")
        
        if stock_id:
            expiries = await trendlyne_api.get_expiry_dates(stock_id)
            if expiries:
                default_expiry = expiries[0]
                data = await trendlyne_api.get_oi_data(stock_id, default_expiry, ts_str)
                if data and data.get('head', {}).get('status') == '0':
                    oi_data = data.get('body', {}).get('oiData', {})
        
        if not oi_data:
            logger.info(f"Trendlyne failed for {underlying}, trying NSE fallback...")
            nse_symbol = underlying.split(":")[-1]
            if nse_symbol == "CNXFINANCE":
                nse_symbol = "FINNIFTY"
            
            nse_data = await asyncio.to_thread(fetch_nse_oi_data, nse_symbol)
            if nse_data and 'records' in nse_data:
                oi_source = "nse"
                records = nse_data['records']
                default_expiry = records['expiryDates'][0]
                oi_data = {}
                for item in nse_data.get('filtered', {}).get('data', []):
                    strike = str(item['strikePrice'])
                    oi_data[strike] = {
                        'callOi': item.get('CE', {}).get('openInterest', 0),
                        'callOiChange': item.get('CE', {}).get('changeinOpenInterest', 0),
                        'callVol': item.get('CE', {}).get('totalTradedVolume', 0),
                        'callLtp': item.get('CE', {}).get('lastPrice', 0),
                        'putOi': item.get('PE', {}).get('openInterest', 0),
                        'putOiChange': item.get('PE', {}).get('changeinOpenInterest', 0),
                        'putVol': item.get('PE', {}).get('totalTradedVolume', 0),
                        'putLtp': item.get('PE', {}).get('lastPrice', 0),
                    }
        
        return oi_data, default_expiry, oi_source
    
    def _process_oi_data(
        self,
        oi_data: Dict[str, Any],
        underlying: str,
        default_expiry: str,
        wss_data: Dict[str, Any],
        spot_price: float
    ) -> List[Dict[str, Any]]:
        """Process OI data with enhanced metrics."""
        rows = []
        timestamp = datetime.now(pytz.utc)
        
        expiry_date = datetime.strptime(default_expiry, "%Y-%m-%d").date() if isinstance(default_expiry, str) else None
        
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
                'time_value': call_greeks['time_value']
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
                'time_value': put_greeks['time_value']
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
        """Fallback to TradingView data."""
        data = await fetch_option_chain(underlying)
        if not data or 'symbols' not in data:
            return
        
        timestamp = datetime.now(pytz.utc)
        rows = []
        symbols = []
        
        if underlying not in self.symbol_map_cache:
            self.symbol_map_cache[underlying] = {}
        
        for item in data['symbols']:
            f = item['f']
            try:
                symbol = f[0]
                strike = float(f[3]) if f[3] is not None else 0
                opt_type = str(f[2]).lower()
                
                symbols.append(symbol)
                self.symbol_map_cache[underlying][f"{strike}_{opt_type}"] = symbol
                
                rows.append({
                    'timestamp': timestamp,
                    'underlying': underlying,
                    'symbol': symbol,
                    'expiry': None,
                    'strike': strike,
                    'option_type': opt_type,
                    'oi': 0,
                    'oi_change': 0,
                    'volume': int(f[4]) if f[4] is not None else 0,
                    'ltp': float(f[5]) if f[5] is not None else 0,
                    'iv': 0,
                    'delta': 0.5 if opt_type == 'call' else -0.5,
                    'gamma': 0,
                    'theta': 0,
                    'vega': 0,
                    'intrinsic_value': 0,
                    'time_value': 0
                })
            except:
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
        data = await fetch_option_chain(underlying)
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
        underlying_price = spot_price
        try:
            res = db.query(
                "SELECT price FROM ticks WHERE instrumentKey = ? ORDER BY ts_ms DESC LIMIT 1",
                (underlying,)
            )
            if res:
                underlying_price = res[0]['price']
        except Exception as e:
            logger.error(f"Error fetching spot for PCR: {e}")
        
        db.insert_pcr_history({
            'timestamp': timestamp,
            'underlying': underlying,
            'pcr_oi': pcr_oi,
            'pcr_vol': pcr_vol,
            'pcr_oi_change': pcr_oi_change,
            'underlying_price': underlying_price or spot_price,
            'max_pain': max_pain,
            'spot_price': spot_price or underlying_price
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
        
        # Fetch spot price from pcr_history
        spot_res = db.query(
            "SELECT spot_price, underlying_price FROM pcr_history WHERE underlying = ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 1",
            (underlying, latest_ts)
        )
        spot_price = 0
        if spot_res:
            spot_price = spot_res[0].get('spot_price') or spot_res[0].get('underlying_price') or 0

        return {"timestamp": latest_ts, "chain": chain, "spot_price": spot_price}
    
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


# Global instance
options_manager = OptionsManager()
