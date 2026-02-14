"""
This example demonstrates how to use custom timeframes
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

    # Create chart with custom timeframe
    chart = client.new_chart()

    @chart.on_error
    async def on_error(*err):
        """Error handling callback"""
        print("Error:", err)

    @chart.on_symbol_loaded
    async def on_ready():
        """Ready callback"""
        print("Chart ready!")

        # Display available custom timeframes (informative)
        print("\nAvailable custom timeframes (examples):")
        print("- Seconds: S5 (5s), S10 (10s), S15 (15s), etc.")
        print("- Minutes: 1 (1m), 3, 5, 10, 15, 30, 45, etc.")
        print("- Hours: 60 (1h), 120 (2h), 180 (3h), 240 (4h), etc.")
        print("- Days: 1D (1d), 2D, 3D, etc.")
        print("- Weeks: 1W (1w), 2W, etc.")
        print("- Months: 1M (1m), etc.")
        print("- Years: 12M (1y), etc.")

    @chart.on_update
    async def on_update():
        """Data update callback"""
        candles = chart.periods
        if candles:
            # Display last 3 candles
            print(f"Fetched {len(candles)} candle records (10m timeframe)")
            print("Last 3 records:")
            for c in candles[-3:]:
                print(c)
            # Demo complete, close connection
            await client.close()

    # Set market with custom timeframe: 10 minutes
    chart.set_market('BINANCE:BTCUSDT', timeframe='10')

    # Timeout handling
    try:
        await asyncio.sleep(30)
    except asyncio.CancelledError:
        pass
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
