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

logger = logging.getLogger(__name__)

class OptionsManager:
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
        self.symbol_map_cache: Dict[str, Dict[str, str]] = {} # underlying -> { "strike_type": "technical_symbol" }
        self.sio = None
        self.loop = None

    def set_socketio(self, sio, loop=None):
        self.sio = sio
        self.loop = loop

    async def start(self):
        if self.running: return
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

        logger.info("Options management started")

    async def backfill_today(self):
        logger.info("Starting today's options backfill from Trendlyne...")

        ist = pytz.timezone('Asia/Kolkata')
        now = datetime.now(ist)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)

        if now < market_open:
            logger.info(f"Market not open yet (Current IST: {now.strftime('%H:%M')}), skipping backfill.")
            return

        end_time = min(now, market_close)
        current = market_open
        time_slots = []
        while current <= end_time:
            time_slots.append(current.strftime("%H:%M"))
            current += timedelta(minutes=15)

        if not time_slots: return

        for underlying in self.active_underlyings:
            tl_symbol = self.tl_symbol_map.get(underlying)
            try:
                logger.info(f"Processing backfill for {underlying} (Trendlyne symbol: {tl_symbol})")
                # Check if already backfilled today
                existing = db.query("SELECT COUNT(*) as count FROM pcr_history WHERE underlying = ? AND CAST(timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS DATE) = CURRENT_DATE AT TIME ZONE 'Asia/Kolkata'", (underlying,))
                if existing and existing[0]['count'] > (len(time_slots) * 0.8):
                    logger.info(f"Sufficient data already exists for {underlying} today, skipping backfill.")
                    continue

                # Get historical spot prices for backfill
                from external.tv_api import tv_api
                hist_spot = await asyncio.to_thread(tv_api.get_hist_candles, underlying, '15', 100)
                spot_map = {c[0]: c[4] for c in hist_spot} if hist_spot else {}

                stock_id = await trendlyne_api.get_stock_id(tl_symbol)
                if not stock_id:
                    logger.warning(f"Could not find stock_id for {tl_symbol}")
                    continue

                expiries = await trendlyne_api.get_expiry_dates(stock_id)
                if not expiries: continue
                default_expiry = expiries[0]

                logger.info(f"Backfilling {underlying} (Expiry: {default_expiry}) for {len(time_slots)} slots")

                for ts_str in time_slots:
                    data = await trendlyne_api.get_oi_data(stock_id, default_expiry, ts_str)
                    if not data or data.get('head', {}).get('status') != '0':
                        continue

                    body = data.get('body', {})
                    oi_data = body.get('oiData', {})

                    ist_dt = now.replace(hour=int(ts_str.split(':')[0]), minute=int(ts_str.split(':')[1]), second=0, microsecond=0)
                    snapshot_time = ist_dt.astimezone(pytz.utc).replace(tzinfo=None)
                    unix_ts = int(ist_dt.timestamp())

                    # Find closest spot price
                    spot_price = 0
                    if unix_ts in spot_map:
                        spot_price = spot_map[unix_ts]
                    else:
                        # Find nearest
                        sorted_ts = sorted(spot_map.keys())
                        for ts in sorted_ts:
                            if ts <= unix_ts: spot_price = spot_map[ts]
                            else: break

                    rows = []
                    for strike_str, strike_data in oi_data.items():
                        strike = float(strike_str)
                        call_sym = self.symbol_map_cache.get(underlying, {}).get(f"{strike}_call")
                        put_sym = self.symbol_map_cache.get(underlying, {}).get(f"{strike}_put")

                        # Call
                        rows.append({
                            'timestamp': snapshot_time,
                            'underlying': underlying,
                            'symbol': call_sym,
                            'expiry': datetime.strptime(default_expiry, "%Y-%m-%d").date(),
                            'strike': strike,
                            'option_type': 'call',
                            'oi': int(strike_data.get('callOi', 0)),
                            'oi_change': int(strike_data.get('callOiChange', 0)),
                            'volume': int(strike_data.get('callVol', 0) or strike_data.get('callVolume', 0)),
                            'ltp': float(strike_data.get('callLtp', 0) or strike_data.get('callLastPrice', 0)),
                            'iv': 0
                        })
                        # Put
                        rows.append({
                            'timestamp': snapshot_time,
                            'underlying': underlying,
                            'symbol': put_sym,
                            'expiry': datetime.strptime(default_expiry, "%Y-%m-%d").date(),
                            'strike': strike,
                            'option_type': 'put',
                            'oi': int(strike_data.get('putOi', 0)),
                            'oi_change': int(strike_data.get('putOiChange', 0)),
                            'volume': int(strike_data.get('putVol', 0) or strike_data.get('putVolume', 0)),
                            'ltp': float(strike_data.get('putLtp', 0) or strike_data.get('putLastPrice', 0)),
                            'iv': 0
                        })

                    if rows:
                        db.insert_options_snapshot(rows)
                        await self._calculate_pcr(underlying, snapshot_time, rows, spot_price=spot_price)

                # Register symbols for WSS tracking
                await self._refresh_wss_symbols(underlying)

                logger.info(f"Backfill complete for {underlying}")
                await asyncio.sleep(1) # Be nice to API
            except Exception as e:
                logger.error(f"Error backfilling {underlying}: {e}")

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
        if underlying in self.wss_clients: return

        def on_data(data):
            self.handle_wss_data(underlying, data)

        wss = OptionsWSS(underlying, on_data)
        wss.start()
        self.wss_clients[underlying] = wss

    def handle_wss_data(self, underlying: str, data: Any):
        symbol = data.get('symbol')
        if not symbol: return

        if underlying not in self.latest_chains:
            self.latest_chains[underlying] = {}

        existing = self.latest_chains[underlying].get(symbol, {})
        for k, v in data.items():
            if v is not None:
                existing[k] = v
        self.latest_chains[underlying][symbol] = existing

        if self.sio:
            event_data = {
                'underlying': underlying, 'symbol': symbol, 'lp': data.get('lp'), 'volume': data.get('volume'), 'bid': data.get('bid'), 'ask': data.get('ask')
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
        if now.weekday() >= 5: return False
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
        tl_symbol = self.tl_symbol_map.get(underlying)
        if not tl_symbol: return
        spot_price = 0
        try:
            res = db.query("SELECT price FROM ticks WHERE instrumentKey = ? ORDER BY ts_ms DESC LIMIT 1", (underlying,))
            if res: spot_price = res[0]['price']
        except Exception as e:
            logger.error(f"Error fetching spot for snapshot: {e}")
        try:
            if underlying not in self.symbol_map_cache or not self.symbol_map_cache[underlying]:
                await self._refresh_wss_symbols(underlying)
            wss_data = self.latest_chains.get(underlying, {})
            stock_id = await trendlyne_api.get_stock_id(tl_symbol)
            oi_source = "trendlyne"
            ist = pytz.timezone('Asia/Kolkata')
            now_ist = datetime.now(ist)
            ts_str = now_ist.strftime("%H:%M")
            timestamp = datetime.now(pytz.utc)
            oi_data = None
            default_expiry = None
            if stock_id:
                expiries = await trendlyne_api.get_expiry_dates(stock_id)
                if expiries:
                    default_expiry = expiries[0]
                    data = await trendlyne_api.get_oi_data(stock_id, default_expiry, ts_str)
                    if data and data.get('head', {}).get('status') == '0':
                        oi_data = data.get('body', {}).get('oiData', {})
            if not oi_data:
                logger.info(f"Trendlyne failed or no data for {underlying}, trying NSE fallback...")
                nse_symbol = underlying.split(":")[-1]
                if nse_symbol == "CNXFINANCE": nse_symbol = "FINNIFTY"
                nse_data = await asyncio.to_thread(fetch_nse_oi_data, nse_symbol)
                if nse_data and 'records' in nse_data:
                    oi_source = "nse"
                    records = nse_data['records']
                    default_expiry = records['expiryDates'][0]
                    oi_data = {}
                    for item in nse_data.get('filtered', {}).get('data', []):
                        strike = str(item['strikePrice'])
                        oi_data[strike] = {
                            'callOi': item.get('CE', {}).get('openInterest', 0), 'callOiChange': item.get('CE', {}).get('changeinOpenInterest', 0),
                            'callVol': item.get('CE', {}).get('totalTradedVolume', 0), 'callLtp': item.get('CE', {}).get('lastPrice', 0),
                            'putOi': item.get('PE', {}).get('openInterest', 0), 'putOiChange': item.get('PE', {}).get('changeinOpenInterest', 0),
                            'putVol': item.get('PE', {}).get('totalTradedVolume', 0), 'putLtp': item.get('PE', {}).get('lastPrice', 0),
                        }
            if not oi_data:
                logger.warning(f"Both Trendlyne and NSE failed for {underlying}, fallback to TV")
                return await self._take_snapshot_tv(underlying)
            rows = []
            for strike_str, strike_data in oi_data.items():
                strike = float(strike_str)
                c_sym = self.symbol_map_cache.get(underlying, {}).get(f"{strike}_call")
                p_sym = self.symbol_map_cache.get(underlying, {}).get(f"{strike}_put")
                c_wss = wss_data.get(c_sym, {}) if c_sym else {}
                p_wss = wss_data.get(p_sym, {}) if p_sym else {}
                rows.append({
                    'timestamp': timestamp, 'underlying': underlying, 'symbol': c_sym,
                    'expiry': datetime.strptime(default_expiry, "%Y-%m-%d").date() if isinstance(default_expiry, str) and "-" in default_expiry else None,
                    'strike': strike, 'option_type': 'call', 'oi': int(strike_data.get('callOi', 0)), 'oi_change': int(strike_data.get('callOiChange', 0)),
                    'volume': c_wss.get('volume', 0) or int(strike_data.get('callVol', 0) or 0),
                    'ltp': c_wss.get('lp', 0.0) or float(strike_data.get('callLtp', 0) or 0), 'iv': 0
                })
                rows.append({
                    'timestamp': timestamp, 'underlying': underlying, 'symbol': p_sym,
                    'expiry': datetime.strptime(default_expiry, "%Y-%m-%d").date() if isinstance(default_expiry, str) and "-" in default_expiry else None,
                    'strike': strike, 'option_type': 'put', 'oi': int(strike_data.get('putOi', 0)), 'oi_change': int(strike_data.get('putOiChange', 0)),
                    'volume': p_wss.get('volume', 0) or int(strike_data.get('putVol', 0) or 0),
                    'ltp': p_wss.get('lp', 0.0) or float(strike_data.get('putLtp', 0) or 0), 'iv': 0
                })
            if rows:
                db.insert_options_snapshot(rows)
                await self._calculate_pcr(underlying, timestamp, rows, spot_price=spot_price)
                logger.info(f"Saved merged {oi_source}+WSS snapshot for {underlying} with {len(rows)} rows")
        except Exception as e:
            logger.error(f"Error in taking snapshot for {underlying}: {e}")
            await self._take_snapshot_tv(underlying)

    async def _take_snapshot_tv(self, underlying: str):
        data = await fetch_option_chain(underlying)
        if not data or 'symbols' not in data: return
        timestamp = datetime.now(pytz.utc)
        rows = []
        symbols = []
        if underlying not in self.symbol_map_cache: self.symbol_map_cache[underlying] = {}
        for item in data['symbols']:
            f = item['f']
            try:
                symbol = f[0]; strike = float(f[3]) if f[3] is not None else 0; opt_type = str(f[2]).lower()
                symbols.append(symbol); self.symbol_map_cache[underlying][f"{strike}_{opt_type}"] = symbol
                rows.append({
                    'timestamp': timestamp, 'underlying': underlying, 'symbol': symbol, 'expiry': None,
                    'strike': strike, 'option_type': opt_type, 'oi': 0, 'oi_change': 0,
                    'volume': int(f[4]) if f[4] is not None else 0, 'ltp': float(f[5]) if f[5] is not None else 0, 'iv': 0
                })
            except: continue
        if rows:
            db.insert_options_snapshot(rows)
            await self._calculate_pcr(underlying, timestamp, rows)
            logger.info(f"Saved TV snapshot for {underlying} with {len(rows)} rows")
            if underlying in self.wss_clients:
                atm_strike = sum(r['strike'] for r in rows) / len(rows) if rows else 0
                filtered_symbols = [r['symbol'] for r in rows if r['symbol'] and (atm_strike == 0 or abs(r['strike'] - atm_strike) / atm_strike < 0.05)]
                self.wss_clients[underlying].add_symbols(filtered_symbols[:400])

    async def _refresh_wss_symbols(self, underlying: str):
        data = await fetch_option_chain(underlying)
        if data and 'symbols' in data:
            if underlying not in self.symbol_map_cache: self.symbol_map_cache[underlying] = {}
            all_symbols = []
            for item in data['symbols']:
                symbol = item['f'][0]; strike = float(item['f'][3]) if item['f'][3] is not None else 0; opt_type = str(item['f'][2]).lower()
                all_symbols.append(symbol); self.symbol_map_cache[underlying][f"{strike}_{opt_type}"] = symbol
            if underlying in self.wss_clients:
                self.wss_clients[underlying].add_symbols(all_symbols[:300])

    async def _calculate_pcr(self, underlying, timestamp, rows, spot_price=0):
        calls = [r for r in rows if r['option_type'] == 'call']
        puts = [r for r in rows if r['option_type'] == 'put']
        total_call_oi = sum(r['oi'] for r in calls)
        total_put_oi = sum(r['oi'] for r in puts)
        total_call_vol = sum(r['volume'] for r in calls)
        total_put_vol = sum(r['volume'] for r in puts)
        pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0
        strikes = sorted(list(set(r['strike'] for r in rows)))
        min_pain = float('inf'); max_pain = strikes[0] if strikes else 0
        for s in strikes:
            pain = 0
            for r in calls:
                if s > r['strike']: pain += (s - r['strike']) * r['oi']
            for r in puts:
                if r['strike'] > s: pain += (r['strike'] - s) * r['oi']
            if pain < min_pain: min_pain = pain; max_pain = s
        underlying_price = spot_price
        try:
            ts_ms = int(timestamp.timestamp() * 1000) if hasattr(timestamp, 'timestamp') else timestamp
            res = db.query("SELECT price FROM ticks WHERE instrumentKey = ? and ts_ms >= ? ORDER BY ts_ms ASC LIMIT 1", (underlying, ts_ms))
            if res: underlying_price = res[0]['price']
            elif underlying_price == 0:
                res_latest = db.query("SELECT price FROM ticks WHERE instrumentKey = ? ORDER BY ts_ms DESC LIMIT 1", (underlying,))
                if res_latest: underlying_price = res_latest[0]['price']
                else:
                    hist = await asyncio.to_thread(tv_api.get_hist_candles, underlying, '1', 1)
                    if hist: underlying_price = hist[0][4]
        except Exception as e: logger.error(f"Error fetching spot for PCR: {e}")
        db.insert_pcr_history({
            'timestamp': timestamp, 'underlying': underlying, 'pcr_oi': pcr_oi, 'pcr_vol': pcr_vol,
            'underlying_price': underlying_price or spot_price, 'max_pain': max_pain, 'spot_price': spot_price
        })

options_manager = OptionsManager()
