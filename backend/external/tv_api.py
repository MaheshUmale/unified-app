import logging
from tvDatafeed import TvDatafeed, Interval
from tradingview_scraper.symbols.stream import Streamer
import logging
import os
import contextlib
import io

from datetime import datetime
import re

def convert_hrn_to_symbol(symbol_or_hrn):
    # Match pattern: "NIFTY 03 FEB 2026 CALL 25300"
    pattern = r"(NIFTY|BANKNIFTY|FINNIFTY)\s+(\d{1,2})\s+([A-Z]{3})\s+(\d{4})\s+(CALL|PUT)\s+(\d+)"
    match = re.search(pattern, symbol_or_hrn.upper())
    
    if match:
        base, day, month_str, year, opt_type, strike = match.groups()
        
        # Convert month name (FEB) to number (02)
        # %d %b %Y matches '03 FEB 2026'
        dt = datetime.strptime(f"{day} {month_str} {year}", "%d %b %Y")
        
        # Format parts: YY (26), MM (02), DD (03)
        yy = dt.strftime("%y")
        mm = dt.strftime("%m")
        dd = dt.strftime("%d")
        
        # Map CALL -> C and PUT -> P
        cp = "C" if opt_type == "CALL" else "P"
        
        return f"{base}{yy}{mm}{dd}{cp}{strike}"
    
    return symbol_or_hrn




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
            logger.info(f"1) Fetching {symbol_or_hrn}")
            if not symbol_or_hrn: return None

            tv_symbol = symbol_or_hrn
            tv_exchange = 'NSE'

            if ':' in symbol_or_hrn:
                parts = symbol_or_hrn.split(':')
                tv_exchange = parts[0]
                tv_symbol = parts[1]
                symbol_or_hrn = tv_symbol # for later checks

            # 1. Handle explicit mapping
            if symbol_or_hrn in self.symbol_map:
                meta = self.symbol_map[symbol_or_hrn]
                tv_symbol = meta['symbol']
                tv_exchange = meta['exchange']
            # 2. Handle HRNs for options: "NIFTY 03 FEB 2026 CALL 25300"
            #convert it to "NIFTY<YYMMDD><C/P><Strike>"
            # Usage in your loop
            elif any(x in symbol_or_hrn.upper() for x in ['CALL', 'PUT']):
                tv_symbol = convert_hrn_to_symbol(symbol_or_hrn)

                # if 'NIFTY' in symbol_or_hrn.upper() and '50' not in symbol_or_hrn:
                #     tv_symbol = symbol_or_hrn.upper().replace('NIFTY', 'NIFTY 50')
                # else:
                #     tv_symbol = symbol_or_hrn.upper()
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
                import traceback
                traceback.print_exc()
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
