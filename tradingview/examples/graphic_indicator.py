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
    await client.connect(session=session, signature=signature)

    # Create chart
    chart = client.new_chart()
    chart.set_market('BINANCE:BTCUSDT', timeframe='60')

    # Search for Zig Zag indicator (often has graphics)
    results = await client.search_indicator('Zig Zag')
    if not results:
        print("Indicator not found")
        await client.close()
        return

    indic = results[0]

    # Create study
    study = chart.new_study(indic)

    # Handle errors
    @study.on_error
    async def on_error(*err):
        print('Indicator error:', *err)

    # When study is ready
    @study.on_ready
    async def on_ready(std=study):
        print(f"Indicator '{std.name}' loaded!")

    # When graphics update
    @study.on_update
    async def on_update(std=study):
        print('Graphics data updated')
        # Display table info if available
        if hasattr(std, 'tables') and std.tables:
            print('Tables found:', std.tables)

    # Set timeout
    try:
        await asyncio.sleep(45)
    except asyncio.CancelledError:
        pass
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
