import logging
import threading
import time
from datetime import datetime
try:
    from tvDatafeed import TvDatafeed, Interval
except ImportError:
    TvDatafeed = None
    Interval = None
from core.symbol_mapper import symbol_mapper
import os

logger = logging.getLogger(__name__)

from external.tv_mcp import process_option_chain_with_analysis

class TradingViewFeed:
    def __init__(self, on_message_callback):
        self.on_message = on_message_callback
        username = os.getenv('TV_USERNAME')
        password = os.getenv('TV_PASSWORD')
        if TvDatafeed:
            if username and password:
                self.tv = TvDatafeed(username, password)
            else:
                self.tv = TvDatafeed()
        else:
            self.tv = None

        self.indices = ['NIFTY', 'BANKNIFTY', 'CNXFINANCE', 'INDIAVIX']
        self.stop_event = threading.Event()
        self.thread = None
        self.option_scan_thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_indices, daemon=True)
        self.thread.start()

        self.option_scan_thread = threading.Thread(target=self._run_options, daemon=True)
        self.option_scan_thread.start()

        logger.info("TradingView Feed (Indices + Options) started")

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        if self.option_scan_thread:
            self.option_scan_thread.join()
        logger.info("TradingView Feed stopped")

    def _run_indices(self):
        """Polls index prices from TradingView."""
        while not self.stop_event.is_set():
            if not self.tv:
                time.sleep(10)
                continue
            for symbol in self.indices:
                try:
                    df = self.tv.get_hist(symbol=symbol, exchange='NSE', interval=Interval.in_1_minute, n_bars=1)
                    if df is not None and not df.empty:
                        last_row = df.iloc[-1]
                        ts = df.index[-1]

                        price = float(last_row['close'])
                        ts_ms = int(ts.timestamp() * 1000)

                        hrn = symbol
                        if symbol == 'INDIAVIX': hrn = 'INDIA VIX'
                        if symbol == 'NIFTY': hrn = 'NIFTY'
                        if symbol == 'CNXFINANCE': hrn = 'FINNIFTY'

                        feed_msg = {
                            'type': 'live_feed',
                            'feeds': {
                                hrn: {
                                    'fullFeed': {
                                        'indexFF': {
                                            'ltpc': {
                                                'ltp': str(price),
                                                'ltt': str(ts_ms),
                                                'ltq': '0'
                                            }
                                        }
                                    },
                                    'tv_volume': float(last_row['volume']),
                                    'source': 'tradingview'
                                }
                            }
                        }
                        self.on_message(feed_msg)
                except Exception as e:
                    logger.error(f"Error in TV Index Feed for {symbol}: {e}")
            # Poll every 10 seconds as a backup to WSS real-time feed
            time.sleep(10)

    def _run_options(self):
        """Polls option chain from TradingView scanner every 15 seconds."""
        while not self.stop_event.is_set():
            for symbol in ['NIFTY', 'BANKNIFTY', 'CNXFINANCE']:
                try:
                    tv_symbol = symbol
                    internal_symbol = 'FINNIFTY' if symbol == 'CNXFINANCE' else symbol

                    res = process_option_chain_with_analysis(tv_symbol, 'NSE', expiry_date='nearest')
                    if res['success']:
                        feeds = {}
                        ts_ms = int(datetime.now().timestamp() * 1000)

                        for opt in res['data']:
                            # Map to HRN: SYMBOL DD MMM YYYY CALL/PUT STRIKE
                            # TradingView symbol: NSE:NIFTY260205C23500 (example, format varies)
                            # Actually our tv_mcp returns structured data.

                            # We need to construct the HRN correctly.
                            # res['target_expiry'] is YYYYMMDD
                           # NIFTY 10 FEB 2026 CALL 25900  ==>  NSE:NIFTY260210C25900
                            expiry_dt = datetime.strptime(str(res['target_expiry']), '%Y%m%d')
                            expiry_str = expiry_dt.strftime('%d %b %Y').upper()

                            hrn = f"{internal_symbol} {expiry_str} {opt['type'].upper()} {int(opt['strike'])}"

                            feeds[hrn] = {
                                'fullFeed': {
                                    'marketFF': {
                                        'ltpc': {
                                            'ltp': str(opt['close'] or 0),
                                            'ltt': str(ts_ms),
                                            'ltq': str(opt['volume'] or 0)
                                        },
                                        'oi': str(opt['oi'] or 0),
                                        'iv': str(opt['iv'] or 0),
                                        'optionGreeks': {
                                            'delta': str(opt['delta'] or 0),
                                            'gamma': str(opt['gamma'] or 0),
                                            'theta': str(opt['theta'] or 0),
                                            'vega': str(opt['vega'] or 0)
                                        }
                                    }
                                },
                                'source': 'tradingview_scanner'
                            }

                        if feeds:
                            self.on_message({'type': 'live_feed', 'feeds': feeds})

                except Exception as e:
                    logger.error(f"Error in TV Option Feed for {symbol}: {e}")

            # Poll every 15 seconds to avoid hitting rate limits too hard
            time.sleep(15)

tv_feed = None

def start_tv_feed(on_message_callback):
    global tv_feed
    if tv_feed is None:
        tv_feed = TradingViewFeed(on_message_callback)
        tv_feed.start()
    return tv_feed
