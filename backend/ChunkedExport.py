import os
import gzip
import json
from pymongo import MongoClient
from bson import json_util

# Configuration
import os
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "upstox_strategy_db_new"
COLLECTION_NAME = "raw_tick_data"
OUTPUT_DIR = "../data"
TARGET_SIZE_MB = 20
TARGET_SIZE_BYTES = TARGET_SIZE_MB * 1024 * 1024




if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def export_mongo_to_gzipped_json():
    client = MongoClient(MONGO_URI)
    col = client[DB_NAME][COLLECTION_NAME]

    filter={}
    project={
        '_id': 0
    }
    sort=list({
        '_id': 1
    }.items())


    cursor = col.find(
    filter=filter,
    projection=project,
    sort=sort
    ).batch_size(1000)

    file_count = 1
    current_file_path = os.path.join(OUTPUT_DIR, f"file{file_count}.json.gz")

    # Open the first gzipped file
    f_out = gzip.open(current_file_path, 'wt', encoding='utf-8')

    print(f"Starting export to {OUTPUT_DIR}...")

    try:
        for doc in cursor:
            # Convert BSON to JSON string (keeps marketFF/indexFF and {} exactly as is)
            json_str = json_util.dumps(doc)
            f_out.write(json_str + '\n')

            # Check file size periodically
            if os.path.getsize(current_file_path) >= TARGET_SIZE_BYTES:
                f_out.close()
                print(f"Finished {current_file_path} ({os.path.getsize(current_file_path)/1024/1024:.2f} MB)")

                file_count += 1
                current_file_path = os.path.join(OUTPUT_DIR, f"file{file_count}.json.gz")
                f_out = gzip.open(current_file_path, 'wt', encoding='utf-8')

        f_out.close()
        print("Export complete.")

    except Exception as e:
        print(f"Error: {e}")
        f_out.close()

if __name__ == "__main__":
    export_mongo_to_gzipped_json()
