import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from external.tv_api import tv_api
import logging

logging.basicConfig(level=logging.INFO)

def test():
    candles = tv_api.get_hist_candles("NSE:NIFTY", "1", 100)
    if candles:
        print(f"Success: Got {len(candles)} candles")
        print(f"First candle: {candles[0]}")
    else:
        print("Failed to get candles")

if __name__ == "__main__":
    test()
