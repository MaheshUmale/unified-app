import os
import sys
import asyncio
import json
from datetime import datetime
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
    await client.connect(session=session, signature=signature)

    # Create chart
    chart = client.new_chart()

    # Event for completion
    finished = asyncio.Event()

    # Define callbacks
    @chart.on_error
    async def on_error(*err):
        print("Error:", err)
        finished.set()

    @chart.on_symbol_loaded
    async def on_ready():
        print("Chart ready!")
        print("Enabling replay mode...")
        # Enable replay mode - Set to Jan 1, 2021
        ts = int(datetime(2021, 1, 1).timestamp())
        # Assuming set_replay method exists
        if hasattr(chart, 'set_replay'):
            await chart.set_replay(ts)

    @chart.on_update
    async def on_update():
        # Get candles
        candles = chart.periods

        # Get replay status if available
        if hasattr(chart, 'replay_instance'):
            status = chart.replay_instance.get('status')
            print(f"\nReplay status: {status}")

        # Show latest candle
        if candles:
            latest = candles[-1]
            dt = datetime.fromtimestamp(latest['time'])
            print(f"Fetched {len(candles)} candle records")
            print(f"Time: {dt.strftime('%Y-%m-%d')}")
            print(f"Open: {latest.get('open')}, Close: {latest.get('close')}")

        # Replay action example
        if hasattr(chart, 'replay_step'):
            print("\nStepping forward...")
            await chart.replay_step(1)
            await asyncio.sleep(3)
        else:
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
