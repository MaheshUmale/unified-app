import logging
from tvDatafeed import TvDatafeed, Interval
from tradingview_scraper.symbols.stream import Streamer
import logging
import os
import contextlib
import io

logger = logging.getLogger(__name__)

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

        self.streamer = Streamer()
        self.symbol_map = {
            'NIFTY': {'symbol': 'NIFTY', 'exchange': 'NSE'},
            'BANKNIFTY': {'symbol': 'BANKNIFTY', 'exchange': 'NSE'},
            'FINNIFTY': {'symbol': 'CNXFINANCE', 'exchange': 'NSE'},
            'INDIA VIX': {'symbol': 'INDIAVIX', 'exchange': 'NSE'}
        }

    def get_hist_candles(self, symbol_or_hrn, interval_min='1', n_bars=1000):
        """
        Fetch historical candles from TradingView using tvDatafeed or Streamer.
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
            elif any(x in symbol_or_hrn.upper() for x in ['CALL', 'PUT']):
                if 'NIFTY' in symbol_or_hrn.upper() and '50' not in symbol_or_hrn:
                    tv_symbol = symbol_or_hrn.upper().replace('NIFTY', 'NIFTY 50')
                else:
                    tv_symbol = symbol_or_hrn.upper()
            elif 'NIFTY' in symbol_or_hrn.upper():
                tv_symbol = 'NIFTY'
            elif 'BANK' in symbol_or_hrn.upper():
                tv_symbol = 'BANKNIFTY'

            # Try Streamer first (sometimes more reliable for recent data)
            try:
                # Capture stdout to avoid clutter
                with contextlib.redirect_stdout(io.StringIO()):
                    data = self.streamer.stream(
                        exchange=tv_exchange,
                        symbol=tv_symbol,
                        timeframe=f"{interval_min}m",
                        numb_price_candles=n_bars
                    )
                if data and 'ohlc' in data:
                    candles = []
                    for row in data['ohlc']:
                        candles.append([
                            row['datetime'],
                            float(row['open']),
                            float(row['high']),
                            float(row['low']),
                            float(row['close']),
                            float(row['volume'])
                        ])
                    return candles[::-1] # Newest first
            except Exception as e:
                logger.warning(f"Streamer failed for {tv_symbol}, falling back to tvDatafeed: {e}")

            # Fallback to tvDatafeed
            tv_interval = Interval.in_1_minute
            if interval_min == '5': tv_interval = Interval.in_5_minute
            elif interval_min == '15': tv_interval = Interval.in_15_minute

            df = self.tv.get_hist(
                symbol=tv_symbol,
                exchange=tv_exchange,
                interval=tv_interval,
                n_bars=n_bars
            )

            if df is not None and not df.empty:
                candles = []
                for ts, row in df.iterrows():
                    candles.append([
                        ts.isoformat(),
                        float(row['open']),
                        float(row['high']),
                        float(row['low']),
                        float(row['close']),
                        float(row['volume'])
                    ])
                return candles[::-1]
            return None
        except Exception as e:
            logger.error(f"Error fetching TradingView data for {symbol_or_hrn}: {e}")
            return None

tv_api = TradingViewAPI()
