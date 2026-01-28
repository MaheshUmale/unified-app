import gzip
import json
import os
import sys
import requests
nifty_50_tickers ="ADANIENT","ADANIPORTS","APOLLOHOSP","ASIANPAINT","AXISBANK","BAJAJ-AUTO","BAJFINANCE","BAJAJFINSV","BEL","BHARTIARTL","CIPLA","COALINDIA","DRREDDY","EICHERMOT","ETERNAL","GRASIM","HCLTECH","HDFCBANK","HDFCLIFE","HEROMOTOCO","HINDALCO","HINDUNILVR","ICICIBANK","ITC","INDUSINDBK","INFY","JSWSTEEL","JIOFIN","KOTAKBANK","LT","M&M","MARUTI","NTPC","NESTLEIND","ONGC","POWERGRID","RELIANCE","SBILIFE","SHRIRAMFIN","SBIN","SUNPHARMA","TCS","TATACONSUM","TATAMOTORS","TATASTEEL","TECHM","TITAN","TRENT","ULTRACEMCO","WIPRO"


UPSTOX_INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"


def extract_unique_instrument_keys() -> set:
    """
    Reads a gzipped file containing a list of JSON objects (like nse.json),
    extracts the unique values of the 'instrument_key' key, and returns them as a set.

    The 'instrument_key' is the required identifier for WebSocket subscriptions.

    Args:
        gz_filepath (str): The path to the input .gz file.

    Returns:
        set: A set of unique instrument key strings.
    """
    print("--------------- ")
    try:

        # 1. Download, decompress, and parse
        response = requests.get(UPSTOX_INSTRUMENTS_URL)
        response.raise_for_status()
        gzipped_file = gzip.decompress(response.content)
        instruments_data = json.loads(gzipped_file.decode('utf-8'))


        # Use a set to automatically handle uniqueness of the keys
        unique_keys = set()

        data = instruments_data


        # 3. Check if the loaded data is a list (an array of instruments)
        if not isinstance(data, list):
            print("Warning: JSON file does not contain a top-level list/array. Could not process.", file=sys.stderr)
            return set()

        # 4. Iterate through each instrument dictionary
        # 2. Populate mappings
        for row in instruments_data:
            full_instrument_key = row.get('instrument_key')
            tradingSymbol = row.get('trading_symbol')
            # Check if the 'instrument_key' exists and is a non-empty string
            if 'instrument_key' in row and row.get('instrument_key'):
                key_with_prefix = row.get('instrument_key')

                # print(key_with_prefix)
                # Extract the ticker symbol from the instrument key
                # Assuming the format is 'NSE_FO|TICKER'
                # ticker = key_with_prefix.split('|')[-1]

                # Add the key to the set only if the ticker is in the nifty_50_tickers set
                if tradingSymbol in nifty_50_tickers:
                    unique_keys.add(key_with_prefix)
                    # print(key_with_prefix)

    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

        import traceback
        traceback.print_exc()

    return unique_keys

# --- Main execution block ---
if __name__ == "__main__":
    # IMPORTANT: Replace 'nse.json.gz' with the actual path to your gzipped file.
    file_path = 'nse.json.gz'

    print(f"Attempting to extract unique 'instrument_key' values from {file_path}...")

    # For demonstration, we'll create a dummy gzipped file if it doesn't exist
    if not os.path.exists(file_path):
        print(f"Creating dummy file '{file_path}' for demonstration...")
        DUMMY_JSON = [
            # Equity
            {"segment": "NSE_EQ", "name": "JOCIL LIMITED", "instrument_key": "NSE_EQ|INE839G01010"},
            # Index
            {"segment": "BSE_INDEX", "name": "AUTO", "instrument_key": "BSE_INDEX|AUTO"},
            # F&O Currency (Duplicate key to test set uniqueness)
            {"segment": "NCD_FO", "underlying_symbol": "GBPINR", "instrument_key": "NCD_FO|14277"},
            {"segment": "NCD_FO", "underlying_symbol": "GBPINR", "instrument_key": "NCD_FO|14277"},
            # F&O Equity
            {"segment": "NSE_FO", "underlying_symbol": "IDEA", "instrument_key": "NSE_FO|36708"},
            # F&O Index
            {"segment": "NSE_FO", "underlying_symbol": "NIFTY", "instrument_key": "NSE_FO|99999"},
            # Entry with missing key (Should be skipped)
            {"segment": "ERROR", "name": "Missing Key"},
        ]
        try:
            with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                json.dump(DUMMY_JSON, f)
            print("Dummy file created successfully.")
        except Exception as e:
            print(f"Failed to create dummy file: {e}", file=sys.stderr)

    # Perform the extraction
    instrument_keys = extract_unique_instrument_keys()

    if instrument_keys:
        print("\n--- Unique Instrument Keys Extracted ---")
        # Convert set to a sorted list for clean display
        sorted_keys = sorted(list(instrument_keys))
        for key in sorted_keys:
            print(key)
        print(f"\nTotal unique keys found: {len(instrument_keys)}")
    elif os.path.exists(file_path):
        print("\nNo 'instrument_key' keys were found, or the file was empty/malformed.")