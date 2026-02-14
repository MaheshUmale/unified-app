import os
import sys
import asyncio
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from tradingview.client import TradingViewClient

# Load environment variables
load_dotenv()

async def main():
    # Credentials
    session = os.getenv('TV_SESSION')
    signature = os.getenv('TV_SIGNATURE')

    if not session or not signature:
        print('Please set TV_SESSION and TV_SIGNATURE environment variables')
        return

    # Create client
    client = TradingViewClient()

    # List of private indicators to test
    # Note: These should be indicators that the user has access to
    indicator_names = [
        "Indicator Name 1",
        "Indicator Name 2"
    ]

    try:
        # Connect
        await client.connect(session=session, signature=signature)

        # Create chart
        chart = client.new_chart()
        chart.set_market('BINANCE:BTCUSDT', timeframe='60')

        indicators_ready = asyncio.Event()
        loaded_count = 0

        # Handle each indicator
        for name in indicator_names:
            try:
                # Search for indicator
                results = await client.search_indicator(name)
                if not results:
                    print(f'Indicator not found: {name}')
                    continue

                # Get full indicator info
                indic = results[0]
                print(f'Loading indicator: {indic.name}...')

                # Create indicator study
                study = chart.new_study(indic)

                # When indicator is ready
                @study.on_ready
                async def on_study_ready(indicator=study):
                    nonlocal loaded_count
                    print(f'Indicator {indicator.name} loaded!')
                    loaded_count += 1
                    if loaded_count == len(indicator_names):
                        indicators_ready.set()

                # When indicator data updates
                @study.on_update
                async def on_study_update(indicator=study):
                    # Check if there's data
                    if indicator.periods:
                        print(f'Indicator {indicator.name} plot values:', indicator.periods[0])
                        # Show strategy report if available
                        if indicator.strategy_report:
                            print(f'Indicator {indicator.name} strategy report:', indicator.strategy_report)

            except Exception as e:
                print(f'Error loading indicator {name}: {e}')

        # Exit if no indicators or loading failed
        if not indicator_names:
            await client.close()
            return

        # Wait for up to 60 seconds
        try:
            await asyncio.wait_for(indicators_ready.wait(), timeout=60)
            print('All indicators loaded, closing...')
        except asyncio.TimeoutError:
            print('Wait timeout, exiting...')

    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
