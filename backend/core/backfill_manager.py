
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from db.mongodb import get_db, get_tick_data_collection, get_oi_collection
from external.upstox_api import UpstoxAPI
from external import upstox_helper
from external import trendlyne_api
from core.symbol_mapper import symbol_mapper
import config
import asyncio

logger = logging.getLogger(__name__)

class BackfillManager:
    def __init__(self, access_token: str):
        self.api = UpstoxAPI(access_token)
        self.db = get_db()
        self.tick_coll = get_tick_data_collection()
        self.strike_coll = self.db['strike_oi_data']

    async def backfill_today_session(self):
        """
        Orchestrates a full backfill for today's data:
        1. Index Candles
        2. ATM Strike Candles (Price + OI)
        3. Trendlyne PCR History
        """
        logger.info("Starting session backfill for today...")

        # 1. Resolve active instruments
        try:
            # We need live prices to find ATM strikes. If market is closed, this might fail or use yesterday's.
            # get_ltp requires a valid market session.
            # Fallback: get last recorded prices from DB if live fails.
            try:
                instrument_keys = upstox_helper.getNiftyAndBNFnOKeys()
            except Exception as e:
                logger.warning(f"Could not fetch live keys for backfill: {e}. Falling back to cached instruments.")
                instrument_keys = self.db['instruments'].distinct('instrument_key')

            if not instrument_keys:
                logger.error("No instruments found to backfill.")
                return {"status": "error", "message": "No instruments found"}

            # Add indices explicitly
            indices = ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank", "NSE_INDEX|India VIX"]
            all_to_backfill = list(set(instrument_keys + indices))

            logger.info(f"Backfilling {len(all_to_backfill)} instruments: {all_to_backfill}")

            tasks = []
            for key in all_to_backfill:
                tasks.append(self.backfill_instrument(key))

            results = await asyncio.gather(*tasks)

            # 2. Trigger Trendlyne PCR backfill
            logger.info("Triggering Trendlyne PCR backfill...")
            trendlyne_api.perform_backfill("NIFTY")
            trendlyne_api.perform_backfill("BANKNIFTY")

            processed = sum(r.get('count', 0) for r in results if isinstance(r, dict))
            return {
                "status": "success",
                "instruments_processed": len(all_to_backfill),
                "data_points_recovered": processed
            }

        except Exception as e:
            logger.error(f"Error during session backfill: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def backfill_instrument(self, instrument_key: str):
        """Fetches intraday candles and persists them to the appropriate collection. instrument_key is raw."""
        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        today_ist = datetime.now(ist).date()

        try:
            # Resolve HRN
            hrn = symbol_mapper.get_hrn(instrument_key)

            # Fetch 1-minute intraday candles
            # get_intraday_candles returns {"status": "success", "data": {"candles": [...]}}
            data = await asyncio.to_thread(self.api.get_intraday_candles, instrument_key)
            if not data or data.get('status') != 'success':
                return {"key": instrument_key, "count": 0}

            candles = data.get('data', {}).get('candles', [])
            if not candles:
                return {"key": instrument_key, "count": 0}

            count = 0
            # Upstox returns: [timestamp, open, high, low, close, volume, oi]
            # Newer candles first
            for c in candles:
                ts_str = c[0]
                dt = datetime.fromisoformat(ts_str)

                # Check if it's today (IST)
                if dt.astimezone(ist).date() != today_ist:
                    continue

                if "NSE_INDEX" in instrument_key:
                    # Index data goes to tick_data as a synthetic tick for historical charts
                    tick_doc = {
                        'instrumentKey': hrn,
                        'raw_key': instrument_key,
                        'ts_ms': int(dt.timestamp() * 1000),
                        'fullFeed': {
                            'indexFF': {
                                'ltpc': {
                                    'ltp': float(c[4]),
                                    'ltt': str(int(dt.timestamp() * 1000)),
                                    'ltq': 0
                                },
                                'marketOHLC': {
                                    'ohlc': [{
                                        'open': float(c[1]),
                                        'high': float(c[2]),
                                        'low': float(c[3]),
                                        'close': float(c[4]),
                                        'ts': int(dt.timestamp() * 1000)
                                    }]
                                }
                            }
                        },
                        'source': 'backfill_synthetic',
                        '_insertion_time': dt
                    }
                    self.tick_coll.update_one(
                        {'instrumentKey': hrn, 'ts_ms': tick_doc['ts_ms']},
                        {'$set': tick_doc},
                        upsert=True
                    )
                    count += 1
                else:
                    # Option data goes to strike_oi_data
                    doc = {
                        'instrument_key': hrn,
                        'date': dt.strftime("%Y-%m-%d"),
                        'timestamp': dt.strftime("%H:%M:%S"),
                        'oi': float(c[6]) if len(c) > 6 else 0,
                        'price': float(c[4]),
                        'iv': 0, # Cannot recover from candles
                        'gamma': 0,
                        'theta': 0,
                        'delta': 0,
                        'spread': 0,
                        'updated_at': dt,
                        'source': 'backfill_upstox'
                    }
                    # Upsert based on key and time
                    self.strike_coll.update_one(
                        {'instrument_key': hrn, 'updated_at': dt},
                        {'$set': doc},
                        upsert=True
                    )
                    count += 1

            return {"key": instrument_key, "count": count}

        except Exception as e:
            logger.error(f"Failed to backfill {instrument_key}: {e}")
            return {"key": instrument_key, "count": 0}
