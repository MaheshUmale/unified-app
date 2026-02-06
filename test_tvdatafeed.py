from tvDatafeed import TvDatafeed, Interval
import logging

logging.basicConfig(level=logging.INFO)

def test():
    try:
        tv = TvDatafeed()
        df = tv.get_hist(symbol='NIFTY', exchange='NSE', interval=Interval.in_1_minute, n_bars=100)
        if df is not None and not df.empty:
            print(f"Success: Got {len(df)} candles")
            print(df.head())
        else:
            print("Failed to get candles from TvDatafeed")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test()
