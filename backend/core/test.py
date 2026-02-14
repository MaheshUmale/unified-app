import duckdb

# Path to the source and target database files
source_db = 'pro_trade_BKP.duckdb'
target_db = 'pro_trade.duckdb'
table_name = 'options_snapshots' # Replace with your actual table name

# Connect to the target database
con = duckdb.connect(target_db)

# 1. Attach the source database
con.execute(f"ATTACH '{source_db}' AS source_db (READ_ONLY)")

# 2. Insert records from source to target
# Assuming table exists in target, else use: 
# CREATE TABLE table_name AS SELECT * FROM source_db.table_name
con.execute(f"INSERT INTO {table_name} SELECT * FROM source_db.{table_name}")

# (Optional) Detach the source database
con.execute("DETACH source_db")

print(f"Data transferred from {source_db} to {target_db}.")
con.close()
