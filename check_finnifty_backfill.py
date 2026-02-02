from db.mongodb import get_db
db = get_db()
count = db['strike_oi_data'].count_documents({'instrument_key': {'': 'FINNIFTY'}, 'source': 'backfill_upstox'})
print(f"FINNIFTY backfilled points: {count}")
