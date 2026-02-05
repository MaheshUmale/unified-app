import logging
import threading
import time
from datetime import datetime
try:
    from tvDatafeed import TvDatafeed, Interval
except ImportError:
    TvDatafeed = None
    Interval = None
import os

logger = logging.getLogger(__name__)

class TradingViewFeed:
    def __init__(self, on_message_callback):
        self.on_message = on_message_callback
        username = os.getenv('TV_USERNAME')
        password = os.getenv('TV_PASSWORD')
        if TvDatafeed:
            self.tv = TvDatafeed(username, password) if username and password else TvDatafeed()
        else:
            self.tv = None
        self.stop_event = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive(): return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run_indices, daemon=True)
        self.thread.start()
        logger.info("TradingView Polling Feed started")

    def stop(self):
        self.stop_event.set()
        if self.thread: self.thread.join()
        logger.info("TradingView Polling Feed stopped")

    def _run_indices(self):
        while not self.stop_event.is_set():
            if not self.tv:
                time.sleep(10); continue
            for symbol in ['NIFTY', 'BANKNIFTY', 'CNXFINANCE']:
                try:
                    df = self.tv.get_hist(symbol=symbol, exchange='NSE', interval=Interval.in_1_minute, n_bars=1)
                    if df is not None and not df.empty:
                        last_row = df.iloc[-1]
                        price = float(last_row['close'])
                        ts_ms = int(df.index[-1].timestamp() * 1000)
                        hrn = {'CNXFINANCE': 'FINNIFTY'}.get(symbol, symbol)
                        self.on_message({
                            'type': 'live_feed',
                            'feeds': {
                                hrn: {
                                    'fullFeed': {'indexFF': {'ltpc': {'ltp': str(price), 'ltt': str(ts_ms), 'ltq': '0'}}},
                                    'tv_volume': float(last_row['volume']),
                                    'source': 'tradingview'
                                }
                            }
                        })
                except:
                    pass
            time.sleep(10)

def start_tv_feed(on_message_callback):
    global tv_feed
    tv_feed = TradingViewFeed(on_message_callback)
    tv_feed.start()
    return tv_feed
