from pymongo import MongoClient
import sys

client = MongoClient('mongodb://localhost:27017/')
db = client['upstox_strategy_db_new']
collection = db['tick_data']

# regex query to find NIFTY options
# We look for documents where the 'instrumentKey' starts with 'NSE_FO'
# and we try to find a human readable name in the document structure.
# Based on previous files, structure might be in 'fullFeed' -> 'marketFF' -> 'ltpc' or 'marketOHLC'
# OR 'fullFeed' -> 'marketFF' -> 'marketLevel' -> 'bidAskQuote' etc.
# Actually usually the 'trading_symbol' or 'name' comes from the initial instrument list,
# but inside tick_data it might just be the key.
# However, the user said "instrument key and data with volume for CE option".

# Let's grep a few NSE_FO documents and see if they contain a symbol name.

cursor = collection.find({'instrumentKey': {'$regex': '^NSE_FO'}}).limit(5)

print("Scanning NSE_FO documents for symbol names...\n")

for doc in cursor:
    key = doc.get('instrumentKey')
    # Try to find symbol name in common Upstox paths
    # Usually it's NOT in the tick data itself, only the instrument key.
    # But let's check if 'fullFeed' has anything.
    print(f"Key: {key}")
    # print(doc) # simplified

    # Check if we can deduce anything or if we should just try one that has high volume.
    ff = doc.get('fullFeed', {}).get('marketFF', {})
    ltpc = ff.get('ltpc', {})
    ltp = ltpc.get('ltp')
    vol = ff.get('marketOHLC', {}).get('ohlc', [{}])[0].get('vol')

    print(f"  LTP: {ltp}, Vol: {vol}")

print("\nSince tick data might not have names, we'll look for a key with HIGH VOLUME (indicating activity) to test with.")

# Find an instrument with significant accumulated volume
cursor = collection.aggregate([
    {'$match': {'instrumentKey': {'$regex': '^NSE_FO'}}},
    {'$group': {'_id': '$instrumentKey', 'count': {'$sum': 1}}},
    {'$sort': {'count': -1}},
    {'$limit': 5}
])

print("\nTop 5 Active NSE_FO Instruments by Tick Count:")
most_active_key = None
for item in cursor:
    print(f"Key: {item['_id']} - Ticks: {item['count']}")
    if not most_active_key:
        most_active_key = item['_id']

print(f"\nRecommended Key to Test: {most_active_key}")
