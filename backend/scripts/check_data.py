#!/usr/bin/env python3
"""Quick script to check available data in MongoDB"""
from pymongo import MongoClient
from datetime import datetime

# Connect to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['upstox_strategy_db']
tick_collection = db['tick_data']

# Check for NSE_EQ|INE002A01018
instrument_key = 'NSE_EQ|INE002A01018'

print(f"\n=== Checking data for {instrument_key} ===\n")

# Count total documents
total = tick_collection.count_documents({'instrumentKey': instrument_key})
print(f"Total documents: {total}")

if total > 0:
    # Get first and last documents
    first_doc = tick_collection.find({'instrumentKey': instrument_key}).sort('_id', 1).limit(1)[0]
    last_doc = tick_collection.find({'instrumentKey': instrument_key}).sort('_id', -1).limit(1)[0]

    # Try to extract timestamps
    def get_timestamp(doc):
        try:
            ff = doc.get('fullFeed', {}).get('marketFF', {})
            ohlc_data = ff.get('marketOHLC', {}).get('ohlc', [])
            if ohlc_data:
                ts_ms = int(ohlc_data[0].get('ts', 0))
            else:
                ts_ms = int(ff.get('ltpc', {}).get('ltt', 0))
            return ts_ms / 1000.0
        except:
            return None

    first_ts = get_timestamp(first_doc)
    last_ts = get_timestamp(last_doc)

    if first_ts:
        print(f"First tick: {datetime.fromtimestamp(first_ts)} (timestamp: {first_ts})")
    if last_ts:
        print(f"Last tick:  {datetime.fromtimestamp(last_ts)} (timestamp: {last_ts})")

    print(f"\nTo replay this data, use a start date between:")
    print(f"  {datetime.fromtimestamp(first_ts).strftime('%Y-%m-%dT%H:%M')}")
    print(f"  {datetime.fromtimestamp(last_ts).strftime('%Y-%m-%dT%H:%M')}")
else:
    print("No data found! Please check:")
    print("1. MongoDB is running")
    print("2. The instrument key is correct")
    print("3. Data has been collected for this instrument")

print("\n" + "="*50 + "\n")
