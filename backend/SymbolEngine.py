from live_indicators import *

class SymbolEngine:
    def __init__(self, symbol, timeframe_sec=60):
        self.symbol = symbol
        self.builder = BarBuilder(timeframe_sec)
        self.state = IndicatorState()

    def on_tick(self, price, volume, ts):
        bar = self.builder.update_tick(price, volume, ts)

        if bar:
            self.state.update(bar)
            signal = self.check_signals(self.state)
            return bar, signal

        return None, None

    def check_signals(self, st: IndicatorState):
        signals = {}

        # --- Example conditions ---
        if st.ema20 and st.ema5 > st.ema20:
            signals['ema_cross'] = True

        if st.bubble_size > 5 and st.norm_vol > 2:
            signals['vol_bubble'] = True

        if st.dyn_pivot and st.prev_close > st.dyn_pivot:
            signals['pivot_break'] = True

        return signals if signals else None

    # -------------------
    # STATE SAVE/LOAD
    # -------------------
    def save_state(self, path):
        data = self.state.__dict__
        with open(path, 'w') as f:
            json.dump(data, f)

    def load_state(self, path):
        if os.path.exists(path):
            with open(path) as f:
                saved = json.load(f)
                for k, v in saved.items():
                    setattr(self.state, k, v)





"""MULTIPLE SYMBOLS on websocket"""
"""

import asyncio
import websockets
import time
from live_indicators import SymbolEngine

symbols = {
    "BTCUSDT": SymbolEngine("BTCUSDT", 60),
    "ETHUSDT": SymbolEngine("ETHUSDT", 60),
    "BNBUSDT": SymbolEngine("BNBUSDT", 60),
}

async def run_wss():
    url = "wss://stream.binance.com:9443/ws/!ticker@arr"

    async with websockets.connect(url) as ws:
        while True:
            msg = await ws.recv()
            data = json.loads(msg)

            ts = int(time.time())  # use exchange timestamp if present

            for tick in data:  # multiple symbols in one payload
                s = tick['s']       # symbol
                p = float(tick['c']) # last price
                v = float(tick['v']) # volume

                if s in symbols:
                    bar, signal = symbols[s].on_tick(p, v, ts)

                    if signal:
                        print(f"[{s}] SIGNAL: {signal}  at {p}")


asyncio.run(run_wss())


State Persistence & Backfill After Paused

Each symbol saves its state:

symbols[s].save_state(f"{s}_state.json")


Reload on restart:

symbols[s].load_state(f"{s}_state.json")



Backfilling 5 minutes of missing data

When reconnecting:

Request historical 1m bars from exchange (e.g., Binance Klines API)

Feed them into the indicator engine using:

for candle in historical_candles:
    symbols[s].state.update(candle)






"""