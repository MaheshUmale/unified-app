import logging
from tvDatafeed import TvDatafeed, Interval

logger = logging.getLogger(__name__)

import os

class TradingViewAPI:
    def __init__(self):
        username = os.getenv('TV_USERNAME')
        password = os.getenv('TV_PASSWORD')
        if username and password:
            self.tv = TvDatafeed(username, password)
            logger.info("TradingViewAPI initialized with credentials")
        else:
            self.tv = TvDatafeed()
            logger.info("TradingViewAPI initialized with guest access")

        self.symbol_map = {
            'NIFTY': {'symbol': 'NIFTY', 'exchange': 'NSE'},
            'BANKNIFTY': {'symbol': 'BANKNIFTY', 'exchange': 'NSE'},
            'FINNIFTY': {'symbol': 'FINNIFTY', 'exchange': 'NSE'},
            'INDIA VIX': {'symbol': 'INDIAVIX', 'exchange': 'NSE'}
        }

    def get_hist_candles(self, symbol, interval_min='1', n_bars=1000):
        """
        Fetch historical candles from TradingView.
        interval_min: '1', '5', '15'
        """
        try:
            tv_meta = self.symbol_map.get(symbol)
            if not tv_meta:
                # Try to extract base symbol if it's like 'NIFTY 50'
                if 'BANK' in symbol:
                    tv_meta = self.symbol_map['BANKNIFTY']
                elif 'NIFTY' in symbol:
                    tv_meta = self.symbol_map['NIFTY']
                else:
                    return None

            tv_interval = Interval.in_1_minute
            if interval_min == '5':
                tv_interval = Interval.in_5_minute
            elif interval_min == '15':
                tv_interval = Interval.in_15_minute

            df = self.tv.get_hist(
                symbol=tv_meta['symbol'],
                exchange=tv_meta['exchange'],
                interval=tv_interval,
                n_bars=n_bars
            )

            if df is not None and not df.empty:
                candles = []
                # df index is datetime
                # columns: symbol, open, high, low, close, volume
                for ts, row in df.iterrows():
                    candles.append([
                        ts.isoformat(),
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        float(row['volume'])
                    ])
                # Return in newest-first order to match Upstox API
                return candles[::-1]
            return None
        except Exception as e:
            logger.error(f"Error fetching TradingView data for {symbol}: {e}")
            return None

tv_api = TradingViewAPI()
