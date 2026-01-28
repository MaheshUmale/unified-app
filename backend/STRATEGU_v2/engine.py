import upstox_client
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta

class UpstoxIntegratedEngine:
    def __init__(self, api_client, symbol="NIFTY"):
        self.api_client = api_client
        self.symbol = symbol
        self.history_api = upstox_client.HistoryV3Api(api_client)
        self.quote_api = upstox_client.MarketQuoteV3Api(api_client)

        # State Variables
        self.day_type = "SIDEWAYS" # Default
        self.prev_day_range = {"high": 0, "low": 0}
        self.total_score = 0

    # --- 1. DAY TYPE CLASSIFICATION (9:15 AM) ---
    def classify_market_context(self, instrument_key):
        """Classifies Day Type based on Open vs Previous Day levels."""
        # Fetch Prev Day Last 60m
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        hist = self.history_api.get_historical_candle_data1(instrument_key, "minute", "1", yesterday, yesterday)
        last_hour = hist.data.candles[-60:]
        self.prev_day_range['high'] = max(c[2] for c in last_hour)
        self.prev_day_range['low'] = min(c[3] for c in last_hour)

        # Fetch Today's Open
        today_live = self.history_api.get_intra_day_candle_data(instrument_key, "1minute")
        today_open = today_live.data.candles[0][1] # Open of first candle

        # Classification Logic
        if today_open > self.prev_day_range['high']:
            self.day_type = "TRENDING_BULLISH"
        elif today_open < self.prev_day_range['low']:
            self.day_type = "TRENDING_BEARISH"
        else:
            self.day_type = "SIDEWAYS_MEAN_REVERSION"

        print(f"Market Context Set: {self.day_type}")

    # --- 2. TACTICAL TEMPLATES ---
    def execute_tactics(self, df_1m, df_5m):
        """Switches logic based on Day Type and Microstructure Score."""
        score = self.calculate_total_score(df_1m, df_5m)
        ltp = df_1m['close'].iloc[-1]

        # A. HUNTER TRADE (Trap Detection)
        if self.day_type == "SIDEWAYS_MEAN_REVERSION":
            if ltp > self.prev_day_range['high'] and score < -5:
                return "TAKE_SHORT", "Hunter Trap - Failed Breakout High"
            if ltp < self.prev_day_range['low'] and score > 5:
                return "TAKE_LONG", "Hunter Trap - Failed Breakout Low"

        # B. POINT-TO-POINT TREND (P2P)
        if "TRENDING" in self.day_type:
            if abs(score) >= 7: # High confluence
                direction = "LONG" if score > 0 else "SHORT"
                return f"RIDE_TREND_{direction}", "Momentum with Volume Force"

        # C. MEAN REVERSION (Range Bound)
        if self.day_type == "SIDEWAYS_MEAN_REVERSION" and abs(score) < 3:
            # Scalp near EVWMA anchors
            return "SCALP_MEAN_REVERSION", "Price returning to Volume Value"

        return "WAIT", "Neutral Score"

    # --- 3. MICROSTRUCTURE SCORING (PINE_SCRIPT.txt Logic) ---
    def calculate_total_score(self, df_1m, df_5m):
        """Unified Score: dyn5 + dyn1 + evm1 + evm5."""
        def get_dir(df): return 1 if df['close'].iloc[-1] > df['evwma'].iloc[-1] else -1

        dyn5 = 5 * get_dir(df_5m)
        dyn1 = 1 * get_dir(df_1m)
        evm5 = 5 if df_5m['evwma'].iloc[-1] > df_5m['evwma'].iloc[-2] else -5
        evm1 = 1 if df_1m['evwma'].iloc[-1] > df_1m['evwma'].iloc[-2] else -1

        return dyn5 + dyn1 + evm5 + evm1

    # --- 4. PRODUCTION LOOP ---
    def run(self, instrument_key):
        self.classify_market_context(instrument_key)

        while True:
            # Fetch latest data using V3
            raw_1m = self.history_api.get_intra_day_candle_data(instrument_key, "1minute")
            df_1m = pd.DataFrame(raw_1m.data.candles, columns=['ts','o','h','l','close','volume','oi'])
            # (Calculate EVWMA here using your volume-force logic)

            action, reason = self.execute_tactics(df_1m, df_1m) # Simplified for example
            print(f"[{datetime.now()}] Action: {action} | Reason: {reason}")
            time.sleep(10)

# --- Execution ---
# engine = UpstoxIntegratedEngine(api_client)
# engine.run("NSE_INDEX|Nifty 50")