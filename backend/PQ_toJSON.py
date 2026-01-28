import os
import pyarrow.parquet as pq
from bson import json_util

# Configuration
DATA_DIR = "../data"

def convert_back_to_json():
    # Filter for parquet files in the data directory
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.parquet')]

    if not files:
        print(f"No parquet files found in {DATA_DIR}")
        return

    for filename in files:
        parquet_path = os.path.join(DATA_DIR, filename)
        json_path = os.path.join(DATA_DIR, filename.replace('.parquet', '.json'))

        # Read Parquet
        table = pq.read_table(parquet_path)
        data = table.to_pylist()

        # Write JSON (Preserving nested marketFF/indexFF)
        with open(json_path, 'w', encoding='utf-8') as f:
            # Use json_util for MongoDB compatibility
            f.write(json_util.dumps(data, indent=2))

        print(f"Converted: {filename} -> {os.path.basename(json_path)}")

if __name__ == "__main__":
    convert_back_to_json()
