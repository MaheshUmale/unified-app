from datetime import datetime
import pandas as pd
import requests
import gzip
import io
import json
import upstox_client
from upstox_client.rest import ApiException
import config

_INSTRUMENT_DF = None
_LAST_FETCH = None

def get_instrument_df():
    global _INSTRUMENT_DF, _LAST_FETCH
    now = datetime.now()
    if _INSTRUMENT_DF is None or _LAST_FETCH is None or (now - _LAST_FETCH).total_seconds() > 86400:
        url = "https://assets.upstox.com/market-quote/instruments/exchange/NSE.json.gz"
        response = requests.get(url)
        with gzip.GzipFile(fileobj=io.BytesIO(response.content)) as f:
            _INSTRUMENT_DF = pd.read_json(f)
        _LAST_FETCH = now
    return _INSTRUMENT_DF

def get_upstox_instruments(symbols=["NIFTY", "BANKNIFTY"], spot_prices={"NIFTY": 0, "BANKNIFTY": 0}):
    # 1. Download and Load Instrument Master (NSE_FO for Futures and Options)
    df = get_instrument_df()

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

def resolve_instrument_key(symbol: str, instrument_type: str = 'FUT', strike: float = None, expiry: str = None):
    df = get_instrument_df()
    mask = (df['name'] == symbol)
    if instrument_type:
        mask &= (df['instrument_type'] == instrument_type)

    if strike is not None:
        mask &= (df['strike_price'] == strike)

    filtered = df[mask].copy()
    if expiry:
        # Assuming expiry is in YYYY-MM-DD
        filtered['expiry_date'] = pd.to_datetime(filtered['expiry'], origin='unix', unit='ms').dt.strftime('%Y-%m-%d')
        filtered = filtered[filtered['expiry_date'] == expiry]

    if not filtered.empty:
        # Sort by expiry to get the nearest one if not specified
        filtered = filtered.sort_values(by='expiry')
        return filtered.iloc[0]['instrument_key']
    return None

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

        # Accessing NIFTY keys
        # print(f"NIFTY Fut: {data['NIFTY']['future']}")
        # print(f"Total NIFTY keys to subscribe: {len(data['NIFTY']['all_keys'])}")

        ALL_FNO = ALL_FNO+data['NIFTY']['all_keys']+data['BANKNIFTY']['all_keys']
        print(ALL_FNO)
        return ALL_FNO
    except ApiException as e:
        print("Exception when calling MarketQuoteV3Api->get_ltp: %s\n" % e)
        return []
