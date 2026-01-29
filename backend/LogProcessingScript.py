import re
from datetime import datetime
import time
from pymongo import MongoClient
import os
# --- CONFIGURATION ---
import os
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
DB_NAME = "upstox_strategy_db_new"


SIGNAL_COLLECTION = "trade_signals"




# --- MONGODB CONNECTION ---
try:
    client = MongoClient(MONGO_URI)
    db = client[DB_NAME]
    signals_collection = db[SIGNAL_COLLECTION]
    print(f"✅ Connected to MongoDB: {DB_NAME}")
except Exception as e:
    print(f"❌ Error connecting to MongoDB: {e}")
    client = None
    signals_collection = None


# Regex for parsing the log lines
# It captures: 1.Timestamp, 2.Instrument Key, 3.Event Type, 4.Rest of the details
LOG_PATTERN = re.compile(
    r"\[(?P<dt>\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}:\d{2})\]\s"  # 1. Datetime
    r"(?P<instrumentKey>[A-Z_]+\|[\w]+)\s"              # 2. Instrument Key (e.g., NSE_EQ|INE417T01026)
    r"(?P<event>\w+):\s"                                # 3. Event Type (e.g., TRADE_EXIT)
    r"(?P<details>.*)"                                  # 4. Details
)

# --- TRADE ID GENERATION ---
# Creates a unique ID for a trade based on instrument and entry time
def generate_trade_id(instrument_key, timestamp):
    dt_object = datetime.fromtimestamp(timestamp)
    time_str = dt_object.strftime('%Y%m%d%H%M%S')
    # Use only the ISIN part of the key for a cleaner ID
    isin = instrument_key.split('|')[-1]
    return f"{isin}-{time_str}"

# --- PARSING AND TRANSFORMATION LOGIC ---
def process_log_file(file_path):
    if signals_collection is None:
        return

    documents_to_insert = []

    with open(file_path, 'r') as f:
        for line in f:
            match = LOG_PATTERN.match(line)
            if not match:
                continue

            data = match.groupdict()

            # Convert datetime string to datetime object and then to epoch timestamp
            dt_obj = datetime.strptime(data['dt'], '%Y-%m-%d %H:%M:%S')
            timestamp = dt_obj.timestamp()

            # Standard fields for every trade signal
            base_doc = {
                'timestamp': timestamp,
                'instrumentKey': data['instrumentKey'],
            }

            event_type = data['event'].split('_')[1] # e.g., 'TRADE_EXIT' -> 'EXIT'

            if 'TRADE_ENTRY' in data['event']:
                # Example: TRADE_ENTRY: SHORT at 860.55
                m = re.search(r"(?P<position_after>SHORT|LONG|BUY|SELL)\s+at\s+(?P<ltp>\d+\.?\d*)", data['details'])
                if m:
                    doc = base_doc.copy()
                    doc.update({
                        'type': 'ENTRY',
                        'ltp': float(m.group('ltp')),
                        'position_after': m.group('position_after'), # e.g., SHORT
                        'trade_id': generate_trade_id(doc['instrumentKey'], timestamp)
                    })

                    # Extract strategy from preceding FAILED_AUCTION line if present (a guess based on log)
                    if 'FAILED_AUCTION_SELL' in line:
                         # FAILED_AUCTION_SELL: CONFLUENCE (TREND): Price 860.55 reclaimed ASK | VWAP: 860.91 | EMA: 860.79
                        strategy_match = re.search(r":\s*(?P<strategy>.*?):\s*Price", data['details'])
                        doc['strategy'] = strategy_match.group('strategy').strip() if strategy_match else 'UNKNOWN'

                    documents_to_insert.append(doc)

            elif 'TRADE_EXIT' in data['event']:
                # Example: TRADE_EXIT: Closed SHORT at 1913.3 | PnL: -2.10 | Reason: Trailing Stop Hit (Low: 1908.1)
                m = re.search(
                    r"Closed\s+(?P<position_closed>SHORT|LONG)\s+at\s+(?P<exit_price>\d+\.?\d*)\s*\|\s*"
                    r"PnL:\s*(?P<pnl>-?\d+\.?\d*)\s*\|\s*"
                    r"Reason:\s*(?P<reason_code>.*?)\s*(\s+\(.*\))?$", data['details']
                )
                if m:
                    doc = base_doc.copy()
                    doc.update({
                        'type': 'EXIT',
                        'exit_price': float(m.group('exit_price')),
                        'pnl': float(m.group('pnl')),
                        'position_closed': m.group('position_closed'),
                        'reason_code': m.group('reason_code').strip(),
                        # Note: trade_id for EXIT requires a mechanism to match it to the ENTRY,
                        # which is usually done by tracking open trades *during* log processing or
                        # matching by instrument and time/position_closed *after* insertion.
                        # For simplicity here, we'll use a placeholder and rely on your API to match by instrument/side/time if trade_id is missing.
                        # **BEST PRACTICE:** Persist the `trade_id` from the ENTRY signal for the EXIT.
                        'trade_id': 'MATCH_REQUIRED'
                    })
                    documents_to_insert.append(doc)

            # You can add logic here to process WALL_DETECTED/WALL_GONER if needed
            # elif 'WALL' in data['event']:
            #     ...

    # Insert documents into MongoDB
    if documents_to_insert:
        # A simple mechanism to link EXIT to the most recent ENTRY for the same instrument
        # In a production system, this mapping should be handled by the original trade execution logic.
        trades_by_instrument = {}
        for doc in documents_to_insert:
            instrument = doc['instrumentKey']
            if doc['type'] == 'ENTRY':
                trades_by_instrument[instrument] = doc['trade_id']
            elif doc['type'] == 'EXIT' and doc['trade_id'] == 'MATCH_REQUIRED':
                 # Assign the ID of the most recent ENTRY for this instrument
                doc['trade_id'] = trades_by_instrument.get(instrument, 'UNKNOWN_TRADE')

        # Insert into DB
        signals_collection.insert_many(documents_to_insert)
        print(f"\n✅ Successfully inserted {len(documents_to_insert)} trade signals into {SIGNAL_COLLECTION}.")


# --- EXECUTE SCRIPT ---
if __name__ == "__main__":
    if client:
        # Example of how to use it:
        # NOTE: Manually change LOG_FILE_PATH to your file name before running!
        # process_log_file(LOG_FILE_PATH)
        #for all files names backtest_results_*.txt in current folder
        for file in os.listdir("."):
            if file.startswith("backtest_results_") and file.endswith(".txt"):
                LOG_FILE_PATH = file
                process_log_file(LOG_FILE_PATH)