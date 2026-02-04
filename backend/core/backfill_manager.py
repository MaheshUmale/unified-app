
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any
from db.local_db import db
from external.tv_api import tv_api
from external import trendlyne_api
from external.tv_mcp import process_option_chain_with_analysis
from core.symbol_mapper import symbol_mapper
import asyncio
import json

logger = logging.getLogger(__name__)

class BackfillManager:
    def __init__(self, access_token: str = None):
        pass

    async def backfill_today_session(self):
        """
        Orchestrates a full backfill for today's data:
        1. Index Candles
        2. Option Chain Snapshots (Price + OI)
        3. Trendlyne PCR History
        """
        logger.info("Starting session backfill for today...")

        try:
            # 1. Backfill Indices
            indices = ["NIFTY", "BANKNIFTY", "FINNIFTY", "INDIA VIX"]
            tasks = [self.backfill_instrument(idx) for idx in indices]
            await asyncio.gather(*tasks)

            # 2. Backfill ATM options using scanner
            for symbol in ['NIFTY', 'BANKNIFTY', 'FINNIFTY']:
                logger.info(f"Backfilling options for {symbol} via TradingView scanner...")
                res = process_option_chain_with_analysis(symbol, 'NSE', expiry_date='nearest')
                if res['success']:
                    ts_ms = int(datetime.now().timestamp() * 1000)
                    expiry_dt = datetime.strptime(str(res['target_expiry']), '%Y%m%d')
                    expiry_str = expiry_dt.strftime('%d %b %Y').upper()

                    for opt in res['data']:
                        hrn = f"{symbol} {expiry_str} {opt['type'].upper()} {int(opt['strike'])}"
                        doc = {
                            'instrument_key': hrn,
                            'date': datetime.now().strftime("%Y-%m-%d"),
                            'timestamp': datetime.now().strftime("%H:%M:%S"),
                            'oi': float(opt['oi'] or 0),
                            'price': float(opt['close'] or 0),
                            'iv': float(opt['iv'] or 0),
                            'gamma': float(opt['gamma'] or 0),
                            'theta': float(opt['theta'] or 0),
                            'delta': float(opt['delta'] or 0),
                            'spread': 0,
                            'updated_at': datetime.now(),
                            'source': 'backfill_tradingview'
                        }
                        db.insert_strike_metric(doc)

            # 3. Trigger Trendlyne PCR backfill
            logger.info("Triggering Trendlyne PCR backfill...")
            trendlyne_api.perform_backfill("NIFTY")
            trendlyne_api.perform_backfill("BANKNIFTY")

            return {
                "status": "success",
                "message": "Backfill completed using TradingView and Trendlyne"
            }

        except Exception as e:
            logger.error(f"Error during session backfill: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def backfill_instrument(self, instrument_key: str):
        """Fetches intraday candles and persists them. instrument_key is HRN or Symbol."""
        import pytz
        ist = pytz.timezone('Asia/Kolkata')
        today_ist = datetime.now(ist).date()

        try:
            # Fetch candles from TV API
            candles = await asyncio.to_thread(tv_api.get_hist_candles, instrument_key, n_bars=500)
            if not candles:
                return {"key": instrument_key, "count": 0}

            count = 0
            # TV returns: [iso_ts, open, high, low, close, volume]
            for c in candles:
                dt = datetime.fromisoformat(c[0])
                if dt.astimezone(ist).date() != today_ist:
                    continue

                # Index data goes to tick_data
                tick_doc = {
                    'instrumentKey': instrument_key,
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
                    'source': 'backfill_tradingview',
                    '_insertion_time': datetime.now()
                }
                db.insert_ticks([tick_doc])
                count += 1

            return {"key": instrument_key, "count": count}

        except Exception as e:
            logger.error(f"Failed to backfill {instrument_key}: {e}")
            return {"key": instrument_key, "count": 0}
