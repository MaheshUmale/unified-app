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
            'FINNIFTY': {'symbol': 'CNXFINANCE', 'exchange': 'NSE'},
            'INDIA VIX': {'symbol': 'INDIAVIX', 'exchange': 'NSE'}
        }

    def get_hist_candles(self, symbol_or_hrn, interval_min='1', n_bars=1000):
        """
        Fetch historical candles from TradingView.
        interval_min: '1', '5', '15'
        """
        try:
            tv_symbol = symbol_or_hrn
            tv_exchange = 'NSE'

            # 1. Handle explicit mapping
            if symbol_or_hrn in self.symbol_map:
                meta = self.symbol_map[symbol_or_hrn]
                tv_symbol = meta['symbol']
                tv_exchange = meta['exchange']

            # 2. Handle HRNs for options: "NIFTY 03 FEB 2026 CALL 25300"
            # TradingView wants: "NIFTY 50 03 FEB 2026 CALL 25300"
            elif any(x in symbol_or_hrn.upper() for x in ['CALL', 'PUT']):
                if 'NIFTY' in symbol_or_hrn.upper() and '50' not in symbol_or_hrn:
                    tv_symbol = symbol_or_hrn.upper().replace('NIFTY', 'NIFTY 50')

                else:
                    tv_symbol = symbol_or_hrn.upper()

            # 3. Handle mixed cases like "NIFTY 50" (Index)
            elif 'NIFTY' in symbol_or_hrn.upper():
                tv_symbol = 'NIFTY' # TradingView uses 'NIFTY' for the main index
            elif 'BANK' in symbol_or_hrn.upper():
                tv_symbol = 'BANKNIFTY'

            tv_interval = Interval.in_1_minute
            if interval_min == '5':
                tv_interval = Interval.in_5_minute
            elif interval_min == '15':
                tv_interval = Interval.in_15_minute
            print()
            df = self.tv.get_hist(
                symbol=tv_symbol,
                exchange=tv_exchange,
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
            logger.error(f"Error fetching TradingView data for {symbol_or_hrn}: {e}")
            return None

tv_api = TradingViewAPI()
