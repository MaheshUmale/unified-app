#!/usr/bin/env python3
"""Check all available instruments in MongoDB"""
from pymongo import MongoClient
from datetime import datetime
#upstox_strategy_db

# tick_data
client = MongoClient('mongodb://localhost:27017/')
db = client['upstox_strategy_db']
tick_collection = db['tick_data']

print("\n=== Available Instruments in MongoDB ===\n")

# Get unique instrument keys
instruments = tick_collection.distinct('instrumentKey')

if not instruments:
    print("No data found in MongoDB!")
    print("\nPossible reasons:")
    print("1. MongoDB is not running")
    print("2. No data has been collected yet")
    print("3. The collection name is different")
else:
    print(f"Found {len(instruments)} instrument(s) with data:\n")

    for inst in instruments:
        count = tick_collection.count_documents({'instrumentKey': inst})

        # Get date range
        first_doc = tick_collection.find({'instrumentKey': inst}).sort('_id', 1).limit(1)[0]
        last_doc = tick_collection.find({'instrumentKey': inst}).sort('_id', -1).limit(1)[0]

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

        print(f"📊 {inst}")
        print(f"   Documents: {count}")
        if first_ts and last_ts:
            print(f"   Range: {datetime.fromtimestamp(first_ts).strftime('%Y-%m-%d %H:%M')} to {datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M')}")
        print()

print("="*50 + "\n")
