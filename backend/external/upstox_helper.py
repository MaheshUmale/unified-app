from datetime import datetime
from typing import List, Dict, Any, Optional
from core.symbol_mapper import symbol_mapper
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

def is_monthly_expiry(expiry_dt: datetime, all_expiries: List[datetime]) -> bool:
    """Checks if the given expiry date is a monthly expiry (last expiry of its month)."""
    month_expiries = [d for d in all_expiries if d.year == expiry_dt.year and d.month == expiry_dt.month]
    return expiry_dt == max(month_expiries) if month_expiries else False

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

        all_unique_expiries = sorted(opt_df['expiry'].unique())

        # User Requirement: NIFTY is Weekly, BANKNIFTY is Monthly
        if symbol == 'BANKNIFTY':
            # Pick nearest MONTHLY expiry
            monthly_expiries = [d for d in all_unique_expiries if is_monthly_expiry(d, all_unique_expiries)]
            nearest_expiry = monthly_expiries[0] if monthly_expiries else all_unique_expiries[0]
        else:
            # Default to absolute nearest (Weekly)
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
            ce_meta = {'symbol': symbol, 'type': 'CE', 'strike': strike, 'expiry': nearest_expiry.strftime('%Y-%m-%d')}
            pe_meta = {'symbol': symbol, 'type': 'PE', 'strike': strike, 'expiry': nearest_expiry.strftime('%Y-%m-%d')}

            ce_hrn = symbol_mapper.get_hrn(ce_key, ce_meta)
            pe_hrn = symbol_mapper.get_hrn(pe_key, pe_meta)

            option_keys.append({
                "strike": strike,
                "ce": ce_key,
                "ce_hrn": ce_hrn,
                "ce_trading_symbol" :ce_trading_symbol,
                "pe": pe_key,
                "pe_hrn": pe_hrn,
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
    import logging
    logger = logging.getLogger(__name__)

    df = get_instrument_df()
    if df is None or df.empty:
        logger.error("Instrument dataframe is empty or None")
        return None

    # Normalization for symbol
    search_symbol = symbol_mapper.get_symbol(symbol)
    if search_symbol == "UNKNOWN":
        search_symbol = symbol.upper()

    mask = (df['name'].str.upper() == search_symbol)
    if instrument_type:
        mask &= (df['instrument_type'].str.upper() == instrument_type.upper())

    if strike is not None:
        # Using a small epsilon for float comparison to be safe
        mask &= (abs(df['strike_price'] - float(strike)) < 0.1)

    filtered = df[mask].copy()

    if filtered.empty:
        logger.warning(f"No instruments found matching {search_symbol} {instrument_type} {strike}")
        return None

    if expiry:
        # Ensure expiry is in YYYY-MM-DD format for comparison
        # Upstox JSON master expiry is often unix ms in float or int
        try:
            # Handle both float/int and potentially already datetime
            if pd.api.types.is_numeric_dtype(filtered['expiry']):
                 filtered['expiry_date'] = pd.to_datetime(filtered['expiry'], origin='unix', unit='ms').dt.strftime('%Y-%m-%d')
            else:
                 filtered['expiry_date'] = pd.to_datetime(filtered['expiry']).dt.strftime('%Y-%m-%d')

            final_filtered = filtered[filtered['expiry_date'] == expiry]

            if final_filtered.empty:
                # Log available expiries for debugging
                available = filtered['expiry_date'].unique().tolist()

                # SPECIAL HANDLING FOR FUTURES:
                # If we requested a weekly expiry for a FUTURE (common mismatch),
                # fallback to the nearest Monthly future instead of failing.
                if instrument_type.upper() == 'FUT':
                    logger.info(f"FUT expiry mismatch for {search_symbol}: Weekly {expiry} requested, choosing nearest FUT {available[0] if available else 'None'}")
                    filtered = filtered.sort_values(by='expiry')
                else:
                    logger.warning(f"Expiry mismatch for {search_symbol}: Requested {expiry}, Available {available}")
                    # Fallback to nearest if exact match fails
                    filtered = filtered.sort_values(by='expiry')
            else:
                filtered = final_filtered
        except Exception as e:
            logger.error(f"Error processing expiry for {search_symbol}: {e}")

    if not filtered.empty:
        # Sort by expiry to get the nearest one
        filtered = filtered.sort_values(by='expiry')
        key = filtered.iloc[0]['instrument_key']
        return key

    return None

def getNiftyAndBNFnOKeys():
    ALL_FNO=[]
    configuration = upstox_client.Configuration()
    configuration.access_token = config.ACCESS_TOKEN
    apiInstance = upstox_client.MarketQuoteV3Api(upstox_client.ApiClient(configuration))
    try:
        # For a single instrument
        response = apiInstance.get_ltp(instrument_key="NSE_INDEX|Nifty 50,NSE_INDEX|Nifty Bank,NSE_INDEX|Nifty Fin Service")

        nifty_bank_data = response.data.get('NSE_INDEX:Nifty Bank')
        nifty_bank_last_price = nifty_bank_data.last_price if nifty_bank_data else 0

        nifty_50_data = response.data.get('NSE_INDEX:Nifty 50')
        nifty_50_last_price = nifty_50_data.last_price if nifty_50_data else 0

        nifty_fin_data = response.data.get('NSE_INDEX:Nifty Fin Service')
        nifty_fin_last_price = nifty_fin_data.last_price if nifty_fin_data else 0

        # --- Execution ---
        current_spots = {
            "NIFTY": nifty_50_last_price,
            "BANKNIFTY": nifty_bank_last_price,
            "FINNIFTY": nifty_fin_last_price
        }

        data = get_upstox_instruments(["NIFTY", "BANKNIFTY", "FINNIFTY"], current_spots)

        for symbol in data:
            ALL_FNO = ALL_FNO + data[symbol]['all_keys']
        return ALL_FNO
    except ApiException as e:
        print("Exception when calling MarketQuoteV3Api->get_ltp: %s\n" % e)
        return []
