from pymongo import MongoClient
import sys

client = MongoClient('mongodb://localhost:27017/')
db = client['upstox_strategy_db']
collection = db['tick_data']

key = "NSE_EQ|INE002A01018"
print(f"Checking data for: {key}")

count = collection.count_documents({'instrumentKey': key})
print(f"Total documents: {count}")

if count > 0:
    first_doc = collection.find_one({'instrumentKey': key}, sort=[('_id', 1)])
    last_doc = collection.find_one({'instrumentKey': key}, sort=[('_id', -1)])
    print("Has data. Range check:")
    # Helper to get TS
    def get_ts(doc):
        try:
             ff = doc.get('fullFeed', {}).get('marketFF', {})
             ohlc = ff.get('marketOHLC', {}).get('ohlc', [])
             if ohlc: return int(ohlc[0].get('ts'))
             return int(ff.get('ltpc', {}).get('ltt'))
        except: return None

    print(f"Start TS: {get_ts(first_doc)}")
    print(f"End TS: {get_ts(last_doc)}")
else:
    print("NO DATA FOUND for Reliance.")
