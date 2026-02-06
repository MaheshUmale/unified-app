from tradingview_scraper.symbols.stream import Streamer
import time

def test():
    try:
        streamer = Streamer()
        stream_gen = streamer.stream(
            exchange='NSE',
            symbol='NIFTY',
            timeframe='1m',
            numb_price_candles=10
        )
        for update in stream_gen:
            if 'ohlc' in update:
                print(f"Success: Got {len(update['ohlc'])} candles")
                break
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
