"""
This example demonstrates how to handle various errors in the TradingView API client
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

    print("=== Example 1: Invalid Symbol ===")

    # Create chart with invalid symbol
    chart1 = client.new_chart()

    @chart1.on_error
    async def on_error1(*err):
        """Error handling callback"""
        print("Error Example 1:", err)
        print("Successfully caught invalid symbol error")

    @chart1.on_symbol_loaded
    async def on_ready1():
        print("Chart 1 ready (this should not happen for invalid symbol)")

    # Set invalid symbol
    chart1.set_market('INVALID:SYMBOL', timeframe='60')

    # Wait for error to occur
    await asyncio.sleep(5)

    print("\n=== Example 2: Invalid Indicator ===")

    # Create chart with valid symbol
    chart2 = client.new_chart()

    @chart2.on_error
    async def on_error2(*err):
        """Error handling callback"""
        print("Error Example 2:", err)
        print("Successfully caught invalid indicator error")

    @chart2.on_symbol_loaded
    async def on_ready2():
        print("Chart 2 ready")
        # Try to use invalid indicator
        try:
            # Passing invalid indicator ID/info
            await chart2.new_study("InvalidIndicatorID")
        except Exception as e:
            print(f"Exception when adding indicator: {e}")

    chart2.set_market('BINANCE:BTCUSDT', timeframe='60')

    # Wait for indicator error
    await asyncio.sleep(5)

    print("\n=== Example 3: Authentication Error ===")

    # Create client with invalid credentials
    bad_client = TradingViewClient()
    try:
        # Connect with invalid credentials
        await bad_client.connect(session='invalid_session', signature='invalid_signature')
        print("Connection successful (this should not happen with invalid credentials)")
    except Exception as e:
        print(f"Auth error example: {e}")
        print("Successfully caught authentication error")

    # Close all connections
    print("\nClosing connections...")
    await client.close()
    await bad_client.close()

if __name__ == '__main__':
    asyncio.run(main())
