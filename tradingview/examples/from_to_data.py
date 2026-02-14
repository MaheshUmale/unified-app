import os
import sys
import asyncio
from datetime import datetime, timezone
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

    # Define time range - Jan 1, 2022 to Jan 31, 2022
    from_date = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
    to_date = int(datetime(2022, 1, 31, tzinfo=timezone.utc).timestamp())

    print(f"Fetching data range: ")
    print(f"  From: {datetime.fromtimestamp(from_date, tz=timezone.utc).strftime('%Y-%m-%d')}")
    print(f"  To:   {datetime.fromtimestamp(to_date, tz=timezone.utc).strftime('%Y-%m-%d')}")

    # Create chart
    chart = client.new_chart()

    # Completion flag
    finished = asyncio.Event()

    # Define callbacks
    @chart.on_error
    async def on_error(*err):
        print("Error:", *err)
        finished.set()

    @chart.on_symbol_loaded
    async def on_ready():
        print("Chart ready!")
        print(f"Symbol: {chart.infos.description}")

    @chart.on_update
    async def on_update():
        candles = chart.periods
        print(f"Fetched {len(candles)} candle records")

        # Check time range
        if candles:
            first_time = datetime.fromtimestamp(candles[0]['time'], tz=timezone.utc)
            last_time = datetime.fromtimestamp(candles[-1]['time'], tz=timezone.utc)
            print(f"\nData time range:")
            print(f"  First candle: {first_time.strftime('%Y-%m-%d')}")
            print(f"  Last candle:  {last_time.strftime('%Y-%m-%d')}")

            # Simple data analysis example
            prices = [c['close'] for c in candles]
            max_price = max(prices)
            min_price = min(prices)
            print(f"\nPeriod High: {max_price}")
            print(f"Period Low:  {min_price}")
            print(f"Volatility Range: {max_price - min_price}")
            print(f"Volatility %: {((max_price - min_price) / min_price * 100):.2f}%")

        finished.set()

    # Set market with range parameters
    chart.set_market('BINANCE:BTCUSDT', timeframe='D', from_ts=from_date, to_ts=to_date)

    # Timeout handling
    try:
        await asyncio.wait_for(finished.wait(), timeout=30)
    except asyncio.TimeoutError:
        print("Operation timed out")
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
