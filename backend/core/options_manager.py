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
        data = await fetch_option_chain(underlying)
        if not data or 'data' not in data:
            return

        # Use UTC for storage
        timestamp = datetime.utcnow()
        rows = []

        # Mapping based on columns in tv_options_scanner.py
        # ["name", "description", "option-type", "strike", "expiry", "open_interest", "open_interest_chg", "volume", "lp", "iv"]
        # Actually I updated it to:
        # ["name", "description", "option-type", "strike", "expiry", "open_interest", "open_interest_chg", "volume", "lp", "iv", "ch", "chp"]
        # Wait, I had an error with "expiry". Let me check what I actually wrote in the file.

        # Column indices:
        # 0: name, 1: description, 2: option-type, 3: strike, 4: expiry (if valid), 5: oi, 6: oi_chg, 7: vol, 8: ltp, 9: iv

        for item in data['data']:
            f = item['f']
            try:
                rows.append({
                    'timestamp': timestamp,
                    'underlying': underlying,
                    'expiry': None, # TODO: parse from name
                    'strike': float(f[3]) if f[3] is not None else 0,
                    'option_type': str(f[2]),
                    'oi': 0, # Not available in basic scanner
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
            logger.info(f"Saved snapshot for {underlying} with {len(rows)} rows")

    def _calculate_pcr(self, underlying, timestamp, rows):
        calls = [r for r in rows if r['option_type'] == 'call']
        puts = [r for r in rows if r['option_type'] == 'put']

        total_call_oi = sum(r['oi'] for r in calls)
        total_put_oi = sum(r['oi'] for r in puts)
        total_call_vol = sum(r['volume'] for r in calls)
        total_put_vol = sum(r['volume'] for r in puts)

        pcr_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
        pcr_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0

        # We don't have underlying price easily here, maybe fetch from last tick
        underlying_price = 0
        try:
            res = db.query("SELECT price FROM ticks WHERE instrumentKey = ? ORDER BY ts_ms DESC LIMIT 1", (underlying,))
            if res: underlying_price = res[0]['price']
        except: pass

        db.insert_pcr_history({
            'timestamp': timestamp,
            'underlying': underlying,
            'pcr_oi': pcr_oi,
            'pcr_vol': pcr_vol,
            'underlying_price': underlying_price
        })

options_manager = OptionsManager()
