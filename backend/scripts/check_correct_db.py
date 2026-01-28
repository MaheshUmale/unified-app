#!/usr/bin/env python3
"""Check tick_data in upstox_strategy_db"""
from pymongo import MongoClient
from datetime import datetime

client = MongoClient('mongodb://localhost:27017/')
db = client['upstox_strategy_db']
collection = db['tick_data']

print("\n=== Checking 'upstox_strategy_db.tick_data' ===\n")

count = collection.count_documents({})
print(f"Total documents: {count}\n")

if count > 0:
    # Get unique instruments
    instruments = collection.distinct('instrumentKey')
    print(f"Instruments with data: {len(instruments)}\n")

    for inst in instruments[:10]:  # Show first 10
        inst_count = collection.count_documents({'instrumentKey': inst})

        # Get date range
        first_doc = collection.find({'instrumentKey': inst}).sort('_id', 1).limit(1)[0]
        last_doc = collection.find({'instrumentKey': inst}).sort('_id', -1).limit(1)[0]

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
        print(f"   Documents: {inst_count}")
        if first_ts and last_ts:
            print(f"   From: {datetime.fromtimestamp(first_ts).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   To:   {datetime.fromtimestamp(last_ts).strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"   📅 Use this in UI: {datetime.fromtimestamp(first_ts).strftime('%Y-%m-%dT%H:%M')}")
            print(f"   🔢 Or timestamp: {int(first_ts)}\n")
else:
    print("❌ No data in tick_data collection")

print("="*60)
