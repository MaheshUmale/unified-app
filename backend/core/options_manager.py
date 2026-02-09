import asyncio
import logging
import json
import pytz
from datetime import datetime, timedelta
from typing import Dict, Any, List
import pandas as pd
from external.tv_options_scanner import fetch_option_chain
from external.tv_options_wss import OptionsWSS
from external.trendlyne_api import trendlyne_api
from db.local_db import db

logger = logging.getLogger(__name__)

class OptionsManager:
    def __init__(self):
        self.active_underlyings = ["NSE:NIFTY", "NSE:BANKNIFTY", "NSE:FINNIFTY"]
        self.running = False
        self._task = None
        self.wss_clients: Dict[str, OptionsWSS] = {}
        self.latest_chains: Dict[str, Any] = {}

    async def start(self):
        if self.running: return
        self.running = True

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

        symbol_map = {
            "NSE:NIFTY": "NIFTY",
            "NSE:BANKNIFTY": "BANKNIFTY",
            "NSE:FINNIFTY": "FINNIFTY"
        }

        for underlying, tl_symbol in symbol_map.items():
            try:
                # Check if already backfilled today
                existing = db.query("SELECT COUNT(*) as count FROM pcr_history WHERE underlying = ? AND CAST(timestamp AS DATE) = CURRENT_DATE", (underlying,))
                if existing and existing[0]['count'] > (len(time_slots) * 0.8):
                    logger.info(f"Sufficient data already exists for {underlying} today, skipping backfill.")
                    continue

                stock_id = await trendlyne_api.get_stock_id(tl_symbol)
                if not stock_id: continue

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

                    snapshot_time = now.replace(hour=int(ts_str.split(':')[0]), minute=int(ts_str.split(':')[1]), second=0, microsecond=0).astimezone(pytz.utc).replace(tzinfo=None)

                    rows = []
                    for strike_str, strike_data in oi_data.items():
                        strike = float(strike_str)
                        # Call
                        rows.append({
                            'timestamp': snapshot_time,
                            'underlying': underlying,
                            'expiry': datetime.strptime(default_expiry, "%Y-%m-%d").date(),
                            'strike': strike,
                            'option_type': 'call',
                            'oi': int(strike_data.get('callOi', 0)),
                            'oi_change': int(strike_data.get('callOiChange', 0)),
                            'volume': int(strike_data.get('callVol', 0)),
                            'ltp': float(strike_data.get('callLtp', 0)),
                            'iv': 0
                        })
                        # Put
                        rows.append({
                            'timestamp': snapshot_time,
                            'underlying': underlying,
                            'expiry': datetime.strptime(default_expiry, "%Y-%m-%d").date(),
                            'strike': strike,
                            'option_type': 'put',
                            'oi': int(strike_data.get('putOi', 0)),
                            'oi_change': int(strike_data.get('putOiChange', 0)),
                            'volume': int(strike_data.get('putVol', 0)),
                            'ltp': float(strike_data.get('putLtp', 0)),
                            'iv': 0
                        })

                    if rows:
                        db.insert_options_snapshot(rows)
                        self._calculate_pcr(underlying, snapshot_time, rows)

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
        # Update latest chain data
        # Data format from options chain WSS needs to be analyzed
        # Usually it sends 'm': 'du' (data update) with field updates
        if isinstance(data, dict) and data.get('m') == 'du':
            # Handle incremental updates
            pass
        elif isinstance(data, dict):
             # Save last message for inspection if needed
             self.latest_chains[underlying] = data

    async def _snapshot_loop(self):
        ist = pytz.timezone('Asia/Kolkata')
        while self.running:
            now = datetime.now(ist)
            # Market hours 9:15 to 15:30 IST
            # We use UTC in sandbox? No, let's just assume local time for now or check pytz
            # For simplicity, we just run it.

            for underlying in self.active_underlyings:
                try:
                    await self.take_snapshot(underlying)
                except Exception as e:
                    logger.error(f"Error taking snapshot for {underlying}: {e}")

            # Wait 5 minutes
            await asyncio.sleep(300)

    async def take_snapshot(self, underlying: str):
        # We prefer Trendlyne for snapshots because it provides accurate OI and Max Pain
        symbol_map = {"NSE:NIFTY": "NIFTY", "NSE:BANKNIFTY": "BANKNIFTY", "NSE:FINNIFTY": "FINNIFTY"}
        tl_symbol = symbol_map.get(underlying)
        if not tl_symbol: return

        try:
            stock_id = await trendlyne_api.get_stock_id(tl_symbol)
            if not stock_id: return

            expiries = await trendlyne_api.get_expiry_dates(stock_id)
            if not expiries: return
            default_expiry = expiries[0]

            ist = pytz.timezone('Asia/Kolkata')
            now_ist = datetime.now(ist)
            ts_str = now_ist.strftime("%H:%M")

            data = await trendlyne_api.get_oi_data(stock_id, default_expiry, ts_str)
            if not data or data.get('head', {}).get('status') != '0':
                # Fallback to TV Scanner for LTP/Volume if Trendlyne fails
                logger.warning(f"Trendlyne snapshot failed for {underlying}, trying TV Scanner")
                return await self._take_snapshot_tv(underlying)

            body = data.get('body', {})
            oi_data = body.get('oiData', {})

            timestamp = datetime.utcnow()
            rows = []
            for strike_str, strike_data in oi_data.items():
                strike = float(strike_str)
                # Call
                rows.append({
                    'timestamp': timestamp,
                    'underlying': underlying,
                    'expiry': datetime.strptime(default_expiry, "%Y-%m-%d").date(),
                    'strike': strike,
                    'option_type': 'call',
                    'oi': int(strike_data.get('callOi', 0)),
                    'oi_change': int(strike_data.get('callOiChange', 0)),
                    'volume': int(strike_data.get('callVol', 0)),
                    'ltp': float(strike_data.get('callLtp', 0)),
                    'iv': 0
                })
                # Put
                rows.append({
                    'timestamp': timestamp,
                    'underlying': underlying,
                    'expiry': datetime.strptime(default_expiry, "%Y-%m-%d").date(),
                    'strike': strike,
                    'option_type': 'put',
                    'oi': int(strike_data.get('putOi', 0)),
                    'oi_change': int(strike_data.get('putOiChange', 0)),
                    'volume': int(strike_data.get('putVol', 0)),
                    'ltp': float(strike_data.get('putLtp', 0)),
                    'iv': 0
                })

            if rows:
                db.insert_options_snapshot(rows)
                self._calculate_pcr(underlying, timestamp, rows)
                logger.info(f"Saved Trendlyne snapshot for {underlying} with {len(rows)} rows")
        except Exception as e:
            logger.error(f"Error in Trendlyne snapshot for {underlying}: {e}")

    async def _take_snapshot_tv(self, underlying: str):
        data = await fetch_option_chain(underlying)
        if not data or 'data' not in data:
            return

        timestamp = datetime.utcnow()
        rows = []
        for item in data['data']:
            f = item['f']
            try:
                rows.append({
                    'timestamp': timestamp,
                    'underlying': underlying,
                    'expiry': None,
                    'strike': float(f[3]) if f[3] is not None else 0,
                    'option_type': str(f[2]),
                    'oi': 0,
                    'oi_change': 0,
                    'volume': int(f[4]) if f[4] is not None else 0,
                    'ltp': float(f[5]) if f[5] is not None else 0,
                    'iv': 0
                })
            except (IndexError, ValueError, TypeError):
                continue

        if rows:
            db.insert_options_snapshot(rows)
            self._calculate_pcr(underlying, timestamp, rows)
            logger.info(f"Saved TV snapshot for {underlying} with {len(rows)} rows")

    def _calculate_pcr(self, underlying, timestamp, rows):
        calls = [r for r in rows if r['option_type'] == 'call']
        puts = [r for r in rows if r['option_type'] == 'put']

        total_call_oi = sum(r['oi'] for r in calls)
        total_put_oi = sum(r['oi'] for r in puts)
        total_call_vol = sum(r['volume'] for r in calls)
        total_put_vol = sum(r['volume'] for r in puts)

        pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0

        # Calculate Max Pain
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

        # Get spot price
        spot_price = 0
        try:
            # First try Trendlyne mapped symbol if available in ticks
            symbol_map = {"NSE:NIFTY": "NIFTY", "NSE:BANKNIFTY": "BANKNIFTY", "NSE:FINNIFTY": "FINNIFTY"}
            tl_symbol = symbol_map.get(underlying, underlying)

            res = db.query("SELECT price FROM ticks WHERE instrumentKey IN (?, ?) ORDER BY ts_ms DESC LIMIT 1", (underlying, tl_symbol))
            if res: spot_price = res[0]['price']
        except Exception as e:
            logger.error(f"Error fetching spot for PCR: {e}")

        db.insert_pcr_history({
            'timestamp': timestamp,
            'underlying': underlying,
            'pcr_oi': pcr_oi,
            'pcr_vol': pcr_vol,
            'underlying_price': spot_price,
            'max_pain': max_pain,
            'spot_price': spot_price
        })

options_manager = OptionsManager()
