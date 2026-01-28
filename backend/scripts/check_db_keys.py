from pymongo import MongoClient
import sys

# Connect to the correct database used by data_engine.py
client = MongoClient('mongodb://localhost:27017/')
db = client['upstox_strategy_db']
collection = db['tick_data']

print(f"Checking database: {db.name}")
print(f"Checking collection: {collection.name}")

count = collection.count_documents({})
print(f"Total documents: {count}")

if count == 0:
    print("No documents found.")
    sys.exit(0)

# Get unique instrument keys
keys = collection.distinct('instrumentKey')
print("\nUnique Instrument Keys:")
for key in keys:
    print(f" - {key}")
