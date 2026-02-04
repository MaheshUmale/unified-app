import logging
import threading
import time
from tvDatafeed import TvDatafeed, Interval
from core.symbol_mapper import symbol_mapper
import os

logger = logging.getLogger(__name__)

class TradingViewFeed:
    def __init__(self, on_message_callback):
        self.on_message = on_message_callback
        username = os.getenv('TV_USERNAME')
        password = os.getenv('TV_PASSWORD')
        if username and password:
            self.tv = TvDatafeed(username, password)
        else:
            self.tv = TvDatafeed()

        self.symbols = ['NIFTY', 'BANKNIFTY', 'CNXFINANCE', 'INDIAVIX']
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info("TradingView Feed started")

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        logger.info("TradingView Feed stopped")

    def _run(self):
        while not self.stop_event.is_set():
            # Check market hours (optional, but good for resources)
            # For now just run
            for symbol in self.symbols:
                try:
                    print(symbol)
                    df = self.tv.get_hist(symbol=symbol, exchange='NSE', interval=Interval.in_1_minute, n_bars=1)
                    if df is not None and not df.empty:
                        last_row = df.iloc[-1]
                        ts = df.index[-1]

                        # Format as a tick/feed update
                        tick = {
                            'symbol': symbol,
                            'last_price': float(last_row['close']),
                            'open': float(last_row['open']),
                            'high': float(last_row['high']),
                            'low': float(last_row['low']),
                            'close': float(last_row['close']),
                            'volume': float(last_row['volume']),
                            'ts_ms': int(ts.timestamp() * 1000),
                            'source': 'tradingview'
                        }

                        # Map to our internal names
                        hrn = symbol
                        if symbol == 'INDIAVIX': hrn = 'INDIA VIX'

                        # Construct a fake Upstox-like message for the data_engine
                        # data_engine.on_message expects a specific structure
                        feed_msg = {
                            'type': 'live_feed',
                            'feeds': {
                                hrn: {
                                    'fullFeed': {
                                        'indexFF': {
                                            'ltpc': {
                                                'ltp': str(tick['last_price']),
                                                'ltt': str(tick['ts_ms']),
                                                'ltq': '0' # TradingView volume is per candle, not per tick
                                            }
                                        }
                                    },
                                    'tv_volume': tick['volume'] # Special field for index volume
                                }
                            }
                        }
                        self.on_message(feed_msg)
                except Exception as e:
                    logger.error(f"Error in TV Feed for {symbol}: {e}")

            time.sleep(1) # Poll every 1 second

tv_feed = None

def start_tv_feed(on_message_callback):
    global tv_feed
    if tv_feed is None:
        tv_feed = TradingViewFeed(on_message_callback)
        tv_feed.start()
    return tv_feed
