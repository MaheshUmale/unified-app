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

    async def fetch_indicator_data(client, indic_id, symbol="BINANCE:BTCUSDT"):
        """Fetch indicator data"""
        # Create chart
        chart = client.new_chart()
        chart.set_market(symbol, timeframe='60')

        # Search for indicator
        results = await client.search_indicator(indic_id)
        if not results:
            return None

        indic = results[0]
        # Create study
        study = chart.new_study(indic)
        print(f'Fetching "{indic.name}" data...')

        # Wait for data
        data_ready = asyncio.Future()

        @study.on_update
        async def on_update(s=study):
            if s.periods and not data_ready.done():
                print(f'"{s.name}" completed!')
                data_ready.set_result(s.periods)

        # Wait for update
        return await asyncio.wait_for(data_ready, timeout=30)

    # Main logic
    print('Fetching all indicators...')
    indicator_ids = ["RSI", "MACD", "EMA"]

    tasks = []
    for indic_id in indicator_ids:
        tasks.append(fetch_indicator_data(client, indic_id))

    # Run all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Show results
    print('\nIndicator Data Results:')
    for i, data in enumerate(results):
        if isinstance(data, Exception):
            print(f'Indicator {indicator_ids[i]} failed: {data}')
        elif data:
            print(f'Indicator {indicator_ids[i]}: {len(data)} records')
            print(f'Sample record: {data[0]}')
        else:
            print(f'Indicator {indicator_ids[i]}: No data found')

    print('All complete!')
    await client.close()

if __name__ == '__main__':
    asyncio.run(main())
