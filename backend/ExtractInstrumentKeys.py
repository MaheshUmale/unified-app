from datetime import datetime
import pandas as pd
import requests
import gzip
import io

def get_upstox_instruments(symbols=["NIFTY", "BANKNIFTY"], spot_prices={"NIFTY": 0, "BANKNIFTY": 0}):
    # 1. Download and Load Instrument Master (NSE_FO for Futures and Options)
    url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
    response = requests.get(url)
    with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
        df = pd.read_json(f)

    full_mapping = {}

    for symbol in symbols:
        spot = spot_prices.get(symbol)

        # --- 1. Current Month Future ---
        fut_df = df[(df['name'] == symbol) & (df['instrument_type'] == 'FUT')].sort_values(by='expiry')
        current_fut_key = fut_df.iloc[0]['instrument_key']

        # --- 2. Nearest Expiry Options ---
        # Filter for Options for the specific index
        opt_df = df[(df['name'] == symbol) & (df['instrument_type'].isin(['CE', 'PE']))].copy()

        # Ensure expiry is in datetime format for accurate sorting
        opt_df['expiry'] = pd.to_datetime(opt_df['expiry'], origin='unix', unit='ms')
        nearest_expiry = opt_df['expiry'].min()
        near_opt_df = opt_df[opt_df['expiry'] == nearest_expiry]

        # --- 3. Identify the 7 Strikes (3 OTM, 1 ATM, 3 ITM) ---
        unique_strikes = sorted(near_opt_df['strike_price'].unique())

        # Find ATM strike
        atm_strike = min(unique_strikes, key=lambda x: abs(x - spot))
        atm_index = unique_strikes.index(atm_strike)

        # Slice range: Index - 3 to Index + 3 (Total 7 strikes)
        start_idx = max(0, atm_index - 3)
        end_idx = min(len(unique_strikes), atm_index + 4)
        selected_strikes = unique_strikes[start_idx : end_idx]

        # --- 4. Build Result ---
        option_keys = []
        for strike in selected_strikes:
            ce_key = near_opt_df[(near_opt_df['strike_price'] == strike) & (near_opt_df['instrument_type'] == 'CE')]['instrument_key'].values[0]
            ce_trading_symbol = near_opt_df[(near_opt_df['strike_price'] == strike) & (near_opt_df['instrument_type'] == 'CE')]['trading_symbol'].values[0]

            pe_key = near_opt_df[(near_opt_df['strike_price'] == strike) & (near_opt_df['instrument_type'] == 'PE')]['instrument_key'].values[0]
            pe_trading_symbol = near_opt_df[(near_opt_df['strike_price'] == strike) & (near_opt_df['instrument_type'] == 'PE')]['trading_symbol'].values[0]
            option_keys.append({
                "strike": strike,
                "ce": ce_key,
                "ce_trading_symbol" :ce_trading_symbol,
                "pe": pe_key,
                "pe_trading_symbol" : pe_trading_symbol
            })

        full_mapping[symbol] = {
            "future": current_fut_key,
            "expiry": nearest_expiry.strftime('%Y-%m-%d'),
            "options": option_keys,
            "all_keys": [current_fut_key] + [opt['ce'] for opt in option_keys] + [opt['pe'] for opt in option_keys]
        }

    return full_mapping

import  json
import config
import upstox_client
from upstox_client.rest import ApiException
# config.ACCESS_TOKEN

def getNiftyAndBNFnOKeys():
    ALL_FNO=[]
    configuration = upstox_client.Configuration()
    configuration.access_token = config.ACCESS_TOKEN
    apiInstance = upstox_client.MarketQuoteV3Api(upstox_client.ApiClient(configuration))
    try:
        # For a single instrument
        response = apiInstance.get_ltp(instrument_key="NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank")
        # print(response.data.get("NSE_INDEX|Nifty 50").get("last_price"))
        # If you want to access a specific index's last price:
        nifty_bank_data = response.data['NSE_INDEX:Nifty Bank']
        nifty_bank_last_price = nifty_bank_data.last_price  # Use dot notation here

        nifty_50_data = response.data['NSE_INDEX:Nifty 50']
        nifty_50_last_price = nifty_50_data.last_price    # Use dot notation here

        print(f"Nifty Bank last price: {nifty_bank_last_price}")
        print(f"Nifty 50 last price: {nifty_50_last_price}")

        # --- Execution ---
        # Replace spot prices with actual live LTP before running
        current_spots = {
            "NIFTY": nifty_50_last_price,
            "BANKNIFTY": nifty_bank_last_price
        }

        data = get_upstox_instruments(["NIFTY", "BANKNIFTY"], current_spots)
        # print(data)
                # 2. Generate a date string (YYYY-MM-DD format for chronological sorting)
        date_str = datetime.now().strftime("%Y-%m-%d")

        # 3. Construct the dynamic filename
        filename = f"records_{date_str}.jsonl"
        # Write the dictionary to a .json file
        with open(filename, 'a', encoding='utf-8')as f:
            json.dump(data, f, indent=4) # Using indent for pretty printing

        # Accessing NIFTY keys
        # print(f"NIFTY Fut: {data['NIFTY']['future']}")
        # print(f"Total NIFTY keys to subscribe: {len(data['NIFTY']['all_keys'])}")

        ALL_FNO = ALL_FNO+data['NIFTY']['all_keys']+data['BANKNIFTY']['all_keys']
        print(ALL_FNO)
        return ALL_FNO
    except ApiException as e:
        print("Exception when calling MarketQuoteV3Api->get_ltp: %s\n" % e)