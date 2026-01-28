#!/usr/bin/env python3
"""Check MongoDB connection and databases"""
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

try:
    # Try to connect with a short timeout
    client = MongoClient('mongodb://localhost:27017/', serverSelectionTimeoutMS=2000)

    # Force connection
    client.admin.command('ping')

    print("✅ MongoDB is running!\n")

    # List all databases
    dbs = client.list_database_names()
    print(f"Available databases: {dbs}\n")

    # Check upstox_strategy_db specifically
    if 'upstox_strategy_db' in dbs:
        db = client['upstox_strategy_db']
        collections = db.list_collection_names()
        print(f"Collections in 'upstox_strategy_db': {collections}\n")

        # Check tick_data collection
        if 'tick_data' in collections:
            count = db['tick_data'].count_documents({})
            print(f"Documents in 'tick_data': {count}")

            if count > 0:
                # Show sample
                sample = db['tick_data'].find_one()
                print(f"\nSample document keys: {list(sample.keys())}")
                if 'instrumentKey' in sample:
                    print(f"Instrument: {sample['instrumentKey']}")
        else:
            print("⚠️  'tick_data' collection does not exist")
    else:
        print("⚠️  'upstox_strategy_db' database does not exist")
        print("This is normal if you haven't run the app with a valid token yet.")

except ServerSelectionTimeoutError:
    print("❌ MongoDB is NOT running!")
    print("\nTo start MongoDB:")
    print("1. Check if MongoDB service is installed")
    print("2. Start the service: net start MongoDB")
    print("3. Or run: mongod --dbpath <your_data_path>")
except Exception as e:
    print(f"❌ Error connecting to MongoDB: {e}")
