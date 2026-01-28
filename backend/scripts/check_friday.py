#!/usr/bin/env python3
"""Check data for Friday Dec 6, 2025"""
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['upstox_strategy_db']
collection = db['tick_data']

instrument = 'NSE_EQ|INE002A01018'

print(f"\n=== Checking data for {instrument} ===\n")

# Get all documents for this instrument
docs = list(collection.find({'instrumentKey': instrument}).sort('_id', 1))
print(f"Total documents: {len(docs)}\n")

if docs:
    # Extract all timestamps
    timestamps = []
    for doc in docs:
        try:
            ff = doc.get('fullFeed', {}).get('marketFF', {})
            ohlc_data = ff.get('marketOHLC', {}).get('ohlc', [])
            if ohlc_data:
                ts_ms = int(ohlc_data[0].get('ts', 0))
            else:
                ts_ms = int(ff.get('ltpc', {}).get('ltt', 0))
            if ts_ms:
                timestamps.append(ts_ms / 1000.0)
        except:
            pass

    if timestamps:
        timestamps.sort()

        print(f"First tick: {datetime.fromtimestamp(timestamps[0])}")
        print(f"Last tick:  {datetime.fromtimestamp(timestamps[-1])}")
        print(f"\nTimestamp range:")
        print(f"  First: {int(timestamps[0])}")
        print(f"  Last:  {int(timestamps[-1])}")

        # Group by date
        from collections import defaultdict
        by_date = defaultdict(int)
        for ts in timestamps:
            date_str = datetime.fromtimestamp(ts).strftime('%Y-%m-%d (%A)')
            by_date[date_str] += 1

        print(f"\nData by date:")
        for date, count in sorted(by_date.items()):
            print(f"  {date}: {count} ticks")

        # Check for Friday specifically
        friday_count = sum(1 for ts in timestamps if datetime.fromtimestamp(ts).weekday() == 4)
        print(f"\nFriday data: {friday_count} ticks")

        if friday_count > 0:
            friday_ts = [ts for ts in timestamps if datetime.fromtimestamp(ts).weekday() == 4]
            print(f"Friday range: {datetime.fromtimestamp(friday_ts[0])} to {datetime.fromtimestamp(friday_ts[-1])}")
            print(f"Use timestamp: {int(friday_ts[0])}")

print("\n" + "="*60)
