import logging
try:
    from tvDatafeed import TvDatafeed, Interval
except ImportError:
    TvDatafeed = None
    Interval = None
from tradingview_scraper.symbols.stream import Streamer
import logging
import os
import contextlib
import io
import time
from datetime import datetime
import re

logger = logging.getLogger(__name__)

class TradingViewAPI:
    def __init__(self):
        username = os.getenv('TV_USERNAME')
        password = os.getenv('TV_PASSWORD')
        if TvDatafeed:
            self.tv = TvDatafeed(username, password) if username and password else TvDatafeed()
            logger.info("TradingViewAPI initialized with tvDatafeed")
        else:
            self.tv = None
            logger.warning("tvDatafeed not installed, falling back to Streamer only")

        self.streamer = Streamer(export_result=False)
        self.symbol_map = {
            'NIFTY': {'symbol': 'NIFTY', 'exchange': 'NSE'},
            'BANKNIFTY': {'symbol': 'BANKNIFTY', 'exchange': 'NSE'},
            'FINNIFTY': {'symbol': 'CNXFINANCE', 'exchange': 'NSE'},
            'INDIA VIX': {'symbol': 'INDIAVIX', 'exchange': 'NSE'}
        }

    def get_hist_candles(self, symbol_or_hrn, interval_min='1', n_bars=1000):
        try:
            logger.info(f"Fetching historical candles for {symbol_or_hrn}")
            if not symbol_or_hrn: return None

            tv_symbol = symbol_or_hrn
            tv_exchange = 'NSE'

            if ':' in symbol_or_hrn:
                parts = symbol_or_hrn.split(':')
                tv_exchange = parts[0].upper()
                tv_symbol = parts[1].upper()
                symbol_or_hrn = tv_symbol

            if symbol_or_hrn in self.symbol_map:
                meta = self.symbol_map[symbol_or_hrn]
                tv_symbol = meta['symbol']
                tv_exchange = meta['exchange']
            elif symbol_or_hrn.upper() == 'NIFTY':
                tv_symbol = 'NIFTY'
            elif symbol_or_hrn.upper() == 'BANKNIFTY':
                tv_symbol = 'BANKNIFTY'
            elif symbol_or_hrn.upper() == 'FINNIFTY':
                tv_symbol = 'CNXFINANCE'

            # Try Streamer first
            try:
                tf = f"{interval_min}m"
                if interval_min == 'D': tf = '1d'
                elif interval_min == 'W': tf = '1w'
                if interval_min == '60': tf = '1h'

                logger.info(f"Using timeframe {tf} for Streamer (interval_min={interval_min})")

                with contextlib.redirect_stdout(io.StringIO()):
                    stream = self.streamer.stream(
                        exchange=tv_exchange,
                        symbol=tv_symbol,
                        timeframe=tf,
                        numb_price_candles=n_bars
                    )

                data = None
                for item in stream:
                    if 'ohlc' in item:
                        data = item
                        break

                if data and 'ohlc' in data:
                    candles = []
                    for row in data['ohlc']:
                        ts = row.get('timestamp') or row.get('datetime')
                        if not isinstance(ts, (int, float)):
                            try:
                                ts = int(datetime.fromisoformat(ts.replace('Z', '+00:00')).timestamp())
                            except:
                                pass

                        candles.append([
                            ts,
                            float(row['open']), float(row['high']), float(row['low']), float(row['close']),
                            float(row['volume'])
                        ])
                    logger.info(f"Retrieved {len(candles)} candles via Streamer")
                    return candles[::-1] # Newest first
            except Exception as e:
                logger.warning(f"Streamer failed for {tv_symbol}: {e}")

            # Fallback to tvDatafeed
            if self.tv:
                tv_interval = Interval.in_1_minute
                if interval_min == '5': tv_interval = Interval.in_5_minute
                elif interval_min == '15': tv_interval = Interval.in_15_minute
                elif interval_min == '30': tv_interval = Interval.in_30_minute
                elif interval_min == '60': tv_interval = Interval.in_1_hour
                elif interval_min == 'D' or interval_min == '1d': tv_interval = Interval.in_daily
                elif interval_min == 'W' or interval_min == '1w': tv_interval = Interval.in_weekly

                df = self.tv.get_hist(symbol=tv_symbol, exchange=tv_exchange, interval=tv_interval, n_bars=n_bars)
                if df is not None and not df.empty:
                    candles = []
                    import pytz
                    ist = pytz.timezone('Asia/Kolkata')
                    for ts, row in df.iterrows():
                        try:
                            ts_ist = ist.localize(ts) if ts.tzinfo is None else ts.astimezone(ist)
                            unix_ts = int(ts_ist.timestamp())
                        except:
                            unix_ts = int(ts.timestamp())

                        candles.append([
                            unix_ts,
                            float(row['open']), float(row['high']), float(row['low']), float(row['close']),
                            float(row['volume'])
                        ])
                    logger.info(f"Retrieved {len(candles)} candles via tvDatafeed")
                    return candles[::-1]

            # Final Fallback to Local DB (for Replay support)
            try:
                from db.local_db import db
                logger.info(f"Falling back to local DB for {tv_symbol}")
                # Build candles from ticks
                interval_map = {'1': 60, '5': 300, '15': 900, '30': 1800, '60': 3600, 'D': 86400}
                duration = interval_map.get(interval_min, 60)

                # Fetch last 1000 bars worth of ticks using arg_min/max for accurate OHLC
                res = db.query(f"""
                    SELECT
                        (ts_ms / 1000 / {duration}) * {duration} as bucket,
                        arg_min(price, ts_ms) as o,
                        MAX(price) as h,
                        MIN(price) as l,
                        arg_max(price, ts_ms) as c,
                        SUM(qty) as v
                    FROM ticks
                    WHERE instrumentKey = ?
                    GROUP BY bucket
                    ORDER BY bucket DESC
                    LIMIT ?
                """, (symbol_or_hrn, n_bars))

                if res:
                    candles = [[int(r['bucket']), float(r['o']), float(r['h']), float(r['l']), float(r['c']), float(r['v'])] for r in res]
                    logger.info(f"Retrieved {len(candles)} candles via local DB")
                    return candles # Already newest first from query
            except Exception as db_e:
                logger.warning(f"Local DB fallback failed: {db_e}")

            return None
        except Exception as e:
            logger.error(f"Error fetching TradingView data: {e}")
            return None

tv_api = TradingViewAPI()
