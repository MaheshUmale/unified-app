import os
import sys
import asyncio
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from tradingview.client import TradingViewClient

async def main():
    load_dotenv()

    # Credentials
    session = os.getenv('TV_SESSION')
    signature = os.getenv('TV_SIGNATURE')

    if not session or not signature:
        print('Please set TV_SESSION and TV_SIGNATURE environment variables')
        return

    # Create client
    client = TradingViewClient()

    # Connect
    await client.connect(session=session, signature=signature)

    # Create chart
    chart = client.new_chart()

    # Set market
    print('Setting market to BINANCE:BTCUSDT...')
    chart.set_market('BINANCE:BTCUSDT', timeframe='60')

    # Define callbacks
    @chart.on_update
    async def on_update():
        if chart.periods:
            print(f'Last candle: {chart.periods[-1]}')

    # Wait for 5 seconds and change market
    await asyncio.sleep(5)
    print('Setting market to OANDA:XAUUSD...')
    chart.set_market('OANDA:XAUUSD', timeframe='D')

    # Wait for 5 seconds and close chart
    await asyncio.sleep(5)
    print('\nClosing chart in 5 seconds...')
    await asyncio.sleep(5)
    print('Closing chart...')
    # Assuming delete method exists
    if hasattr(chart, 'delete'):
        await chart.delete()

    # Wait for 5 seconds and close client
    print('\nClosing client in 5 seconds...')
    await asyncio.sleep(5)
    print('Closing client...')
    await client.close()

if __name__ == '__main__':
    asyncio.run(main())
