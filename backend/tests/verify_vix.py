
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from external import upstox_helper
from config import ACCESS_TOKEN

def test_vix_resolution():
    print(f"Access Token: {ACCESS_TOKEN[:10]}...")
    df = upstox_helper.get_instrument_df()
    vix = df[df['trading_symbol'] == 'INDIA VIX']
    if not vix.empty:
        print("India VIX found:")
        print(vix[['instrument_key', 'trading_symbol', 'name', 'instrument_type']])
    else:
        print("India VIX NOT found in NSE master.")
        # Try finding by name
        vix_by_name = df[df['name'].str.contains('VIX', na=False)]
        print("Search by name 'VIX':")
        print(vix_by_name[['instrument_key', 'trading_symbol', 'name']])

if __name__ == "__main__":
    test_vix_resolution()
