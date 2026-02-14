import os
import sys
import asyncio
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from tradingview.client import TradingViewClient

async def main():
    """Main function"""
    load_dotenv()
    client = TradingViewClient()

    print("========== Market Search ==========")
    markets = await client.search_market("BINANCE:")
    for market in markets[:3]:
        print(f"Market: {market.id} - {market.description}")

    print("\n========== Technical Analysis ==========")
    if markets:
        m = markets[0]
        # Assuming get_ta exists
        if hasattr(client, 'get_ta'):
            ta = await client.get_ta(m.exchange, m.id.split(':')[-1])
            print(ta)

    print("\n========== Indicator Search ==========")
    indicators = await client.search_indicator("RSI")
    for indicator in indicators[:3]:
        print(f"Indicator: {indicator.name} Author: {indicator.author['username']}")

    print("\n========== Indicator Details ==========")
    if indicators:
        indic = indicators[0]
        try:
            # Assuming get_indicator_details exists
            if hasattr(client, 'get_indicator_details'):
                detail = await client.get_indicator_details(indic.id)
                print(f"Pine ID: {detail.pineId}")
                print(f"Version: {detail.pineVersion}")
                print(f"Inputs: {len(detail.inputs)}")
        except Exception as e:
            print(f"Failed to fetch indicator details: {e}")

    await client.close()

if __name__ == '__main__':
    asyncio.run(main())
