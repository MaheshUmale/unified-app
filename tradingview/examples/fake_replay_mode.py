"""
This example demonstrates how to use a simulated replay mode by filtering data for custom backtesting.
Unlike real replay mode, simulated replay doesn't use TradingView's replay feature,
but instead filters received data to only process data before a specific date, simulating a replay effect.
This allows you to use your own data for backtesting without relying solely on TradingView's replay.
"""

import os
import sys
import asyncio
from datetime import datetime, timezone
import time
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from tradingview.client import TradingViewClient

# Replay filter date - Jan 1, 2022
FILTER_DATE = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

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

    # Event for completion
    finished = asyncio.Event()

    # Define callbacks
    @client.on_error
    async def on_error(*err):
        """Error handling callback"""
        print("Error:", err)
        finished.set()

    # Connect
    await client.connect(session=session, signature=signature)

    # Create chart
    chart = client.new_chart()

    @chart.on_symbol_loaded
    async def on_ready():
        """Ready callback"""
        print("Chart ready!")
        print(f"Using simulated replay mode, filter date: {datetime.fromtimestamp(FILTER_DATE/1000, tz=timezone.utc).strftime('%Y-%m-%d')}")

    @chart.on_update
    async def on_update():
        """Data update callback"""
        # Get candle data
        candles = chart.periods

        # Filter data - only keep data before filter date
        filtered_candles = [c for c in candles if c['time'] * 1000 <= FILTER_DATE]

        if not filtered_candles:
            print("No data found before filter date")
            return

        print(f"Original data: {len(candles)} candles, Filtered: {len(filtered_candles)} candles")

        # Show latest filtered data
        latest = filtered_candles[-1]
        dt = datetime.fromtimestamp(latest['time'], tz=timezone.utc)
        print(f"\nSimulated Replay latest data ({dt.strftime('%Y-%m-%d')}):")
        print(f"Open: {latest.get('open')}")
        print(f"High: {latest.get('high')}")
        print(f"Low: {latest.get('low')}")
        print(f"Close: {latest.get('close')}")
        print(f"Volume: {latest.get('volume')}")

        # Simulated strategy signals example
        if len(filtered_candles) > 20:
            # Simple MA crossover example
            closes = [c['close'] for c in filtered_candles]
            short_ma = sum(closes[-10:]) / 10
            long_ma = sum(closes[-20:]) / 20

            print(f"10-period MA: {short_ma:.2f}")
            print(f"20-period MA: {long_ma:.2f}")

            # Signal logic
            if short_ma > long_ma:
                print("Simulated Signal: BUY")
            else:
                print("Simulated Signal: SELL")

        # Demo complete, close connection
        finished.set()

    # Set market
    chart.set_market('BINANCE:BTCUSDT', timeframe='D')

    # Timeout handling
    try:
        await asyncio.wait_for(finished.wait(), timeout=30)
    except asyncio.TimeoutError:
        print("Operation timed out")
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
