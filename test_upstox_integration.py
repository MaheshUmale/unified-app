
import asyncio
import os
import sys

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from external.upstox_api import UpstoxAPIClient
from core.symbol_mapper import symbol_mapper

async def test_upstox_options():
    token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if not token:
        print("UPSTOX_ACCESS_TOKEN not set")
        return

    print(f"Testing Upstox Options API with token: {token[:10]}...")
    client = UpstoxAPIClient(token)

    # Test NIFTY option chain
    print("Fetching NIFTY option chain...")
    chain = await client.get_option_chain("NSE:NIFTY")
    if chain and "chain" in chain:
        print(f"Success! Found {len(chain['chain'])} strikes in chain.")
        # Check if OI is present
        top_strike = chain['chain'][0]
        print(f"Sample Strike: {top_strike.get('strike')} {top_strike.get('option_type')} OI: {top_strike.get('oi')}")
    else:
        # Check for the structure returned by my UpstoxAPIClient
        # My implementation: standard_data["symbols"].append({"f": [po.instrument_key, str(strike), "put", ...]})
        # Wait, I should check my implementation of get_option_chain in upstox_api.py
        if chain and "symbols" in chain:
             print(f"Success! Found {len(chain['symbols'])} symbols in chain.")
        else:
             print("Failed to fetch option chain or empty data.")

if __name__ == "__main__":
    asyncio.run(test_upstox_options())
