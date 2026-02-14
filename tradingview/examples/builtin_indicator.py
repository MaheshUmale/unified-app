"""
This example tests built-in indicators, such as volume-based indicators
"""

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

    # Create Volume Profile indicator
    # Note: Built-in indicator names can be found in TradingView's search
    indicator_name = "Volume Profile Visible Range"

    # Credentials
    session = os.getenv('TV_SESSION')
    signature = os.getenv('TV_SIGNATURE')

    if not session or not signature:
        raise ValueError('Please set your TV_SESSION and TV_SIGNATURE environment variables')

    # Create client
    client = TradingViewClient()

    finished = asyncio.Event()

    # Connect
    await client.connect(session=session, signature=signature)

    # Create chart
    chart = client.new_chart()

    # Set market
    chart.set_market('BINANCE:BTCUSDT', timeframe='60')

    # Search for indicator
    results = await client.search_indicator(indicator_name)
    if not results:
        print(f"Indicator not found: {indicator_name}")
        await client.close()
        return

    indic = results[0]

    # Create study
    study = chart.new_study(indic)

    # Handle updates
    @study.on_update
    async def on_update(indicator=study):
        # Filter and process Volume Profile data
        if indicator.periods:
            print(f"Indicator {indicator.name} updated with {len(indicator.periods)} data points")
            # Show a sample of the data
            print("Sample data:", indicator.periods[0])
            finished.set()

    # Set timeout
    try:
        await asyncio.wait_for(finished.wait(), timeout=45)
    except asyncio.TimeoutError:
        print("Operation timed out, forcing connection close")
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
