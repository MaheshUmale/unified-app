"""
This example demonstrates how to use custom chart types
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

    # Check credentials
    session = os.getenv('TV_SESSION')
    signature = os.getenv('TV_SIGNATURE')

    if not session or not signature:
        raise ValueError('Please set TV_SESSION and TV_SIGNATURE environment variables')

    # Create client
    client = TradingViewClient()

    # Connect
    await client.connect(session=session, signature=signature)

    # Create chart with custom type - Heikin Ashi
    chart = client.new_chart()

    # Define callbacks
    @chart.on_error
    async def on_error(*err):
        """Error handling callback"""
        print("Error:", err)

    @chart.on_symbol_loaded
    async def on_ready():
        """Ready callback"""
        print("Chart ready!")

    @chart.on_update
    async def on_update():
        """Data update callback"""
        # Get candle data
        candles = chart.periods
        if candles:
            # Display last 3 candles
            print(f"Fetched {len(candles)} candle records")
            print("Last 3 records:")
            for c in candles[-3:]:
                print(c)
            # Demo complete, close connection
            await client.close()

    # Set market with custom type
    # Type 3 is often Heikin Ashi in some implementations, but here we specify it via parameter if supported
    chart.set_market('BINANCE:BTCUSDT', timeframe='60', style=3)

    # Timeout handling
    try:
        await asyncio.sleep(30)
    except asyncio.CancelledError:
        pass
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
