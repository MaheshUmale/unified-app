import json
import upstox_client
from pymongo import MongoClient
import pandas as pd
from datetime import datetime
import os

# --- Configuration ---
API_VERSION = "v2"
from database import get_oi_collection, get_db

# ... keep access token ...

import config
def get_api_client():
    """Initializes and returns an Upstox API client instance."""

    configuration = upstox_client.Configuration()
    configuration.access_token = config.ACCESS_TOKEN
    api_client = upstox_client.ApiClient(configuration)
    return api_client

def get_option_chain(api_client, instrument_key):
    """
    Fetches the option chain for a given instrument key.

    Args:
        api_client: An instance of the Upstox API client.
        instrument_key: The instrument key for the underlying (e.g., 'NSE_INDEX|Nifty 50').

    Returns:
        A dictionary containing the option chain data, or None if an error occurs.
    """
    try:
        import requests

        url = 'https://api.upstox.com/v2/option/chain'
        params = {
            'instrument_key': 'NSE_INDEX|Nifty 50',
            'expiry_date': '2025-12-09'
        }
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {config.ACCESS_TOKEN}' # Replace with your actual access token
        }

        response = requests.get(url, params=params, headers=headers)

        # print(response.json())
        return response.json()
    except  Exception as e:
        print(f"Error fetching option chain: {e}")
        import traceback

        traceback.print_exc()
        return None

def store_option_chain_data(data):
    """
    Stores the fetched option chain data in a MongoDB collection.

    Args:
        data: The option chain data to be stored.
    """
    try:
        db = get_db()
        # Use the collection name constant or move it to database.py if you prefer
        collection = db['option_chain'] # Hardcoded fallback or use OC_COLLECTION_NAME if valid

        # print(data)
        # Get previous data for OI calculation
        # jsonStr = json.dumps(data)
        # Parse each JSON string into a dictionary
        data = json.loads(json.dumps(data))
        # print(data)

        collection.insert_one(data)


        print("Successfully stored option chain data in MongoDB.")
    except Exception as e:
        print(f"Error storing option chain data in MongoDB: {e}")
        import traceback
        traceback.print_exc()

def calculate_oi_metrics(df, prev_df):
    """
    Calculates various OI-based metrics from the option chain DataFrame.

    Args:
        df: A pandas DataFrame containing the current option chain data.
        prev_df: A pandas DataFrame containing the previous option chain data.

    Returns:
        A dictionary containing the calculated metrics.
    """
    merged_df = pd.merge(df, prev_df, on="strike_price", suffixes=("", "_prev"))

    # Calculate Change in OI
    df['ce_oi_change'] = merged_df['ce_open_interest'] - merged_df['ce_open_interest_prev']
    df['pe_oi_change'] = merged_df['pe_open_interest'] - merged_df['pe_open_interest_prev']

    # Identify Buildups and Unwinding
    df['ce_long_buildup'] = (df['ce_oi_change'] > 0) & (merged_df['ce_ltp'] > merged_df['ce_ltp_prev'])
    df['ce_short_buildup'] = (df['ce_oi_change'] > 0) & (merged_df['ce_ltp'] < merged_df['ce_ltp_prev'])
    df['ce_long_unwinding'] = (df['ce_oi_change'] < 0) & (merged_df['ce_ltp'] < merged_df['ce_ltp_prev'])
    df['ce_short_covering'] = (df['ce_oi_change'] < 0) & (merged_df['ce_ltp'] > merged_df['ce_ltp_prev'])

    df['pe_long_buildup'] = (df['pe_oi_change'] > 0) & (merged_df['pe_ltp'] > merged_df['pe_ltp_prev'])
    df['pe_short_buildup'] = (df['pe_oi_change'] > 0) & (merged_df['pe_ltp'] < merged_df['pe_ltp_prev'])
    df['pe_long_unwinding'] = (df['pe_oi_change'] < 0) & (merged_df['pe_ltp'] < merged_df['pe_ltp_prev'])
    df['pe_short_covering'] = (df['pe_oi_change'] < 0) & (merged_df['pe_ltp'] > merged_df['pe_ltp_prev'])

    return df

def main():
    """
    Main function to fetch, process, and store option chain data.
    """
    api_client = get_api_client()

    # Example for NIFTY
    nifty_key = "NSE_INDEX|Nifty 50"
    option_chain_data = get_option_chain(api_client, nifty_key)

    if option_chain_data:
        store_option_chain_data(option_chain_data)
        # print(option_chain_data.status)
        print("Option chain data processing complete.")
        # print(f"Instrument Key: {option_chain_data }")
        # # Convert to pandas DataFrame for analysis/printing
        # df = pd.DataFrame(option_chain_data['options_chain'])

        # # Check if metrics exist (columns might be missing if no prev data)
        # cols = ['strike_price', 'ce_long_buildup', 'ce_short_buildup', 'pe_long_buildup', 'pe_short_buildup']
        # existing_cols = [c for c in cols if c in df.columns]

        # print("\nOption Chain Metrics:")
        # print(df[existing_cols].head())

if __name__ == "__main__":
    main()
