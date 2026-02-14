"""
This example is used to fetch historical K-line data.
You can specify the symbol, timeframe, and time range.
"""

import os
import sys
import asyncio
import time
import json
from dotenv import load_dotenv

# Add project root to path - must be before importing tradingview
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# Import and load environment variables
print('Loading config from .env...')
load_dotenv()

# Now import tradingview modules
from tradingview.client import TradingViewClient

async def main():
    """Main function"""
    # Create a new TradingView client
    client = TradingViewClient()

    # Credentials
    session = os.getenv('TV_SESSION')
    signature = os.getenv('TV_SIGNATURE')

    if not session or not signature:
        raise ValueError('Please set TV_SESSION and TV_SIGNATURE environment variables')

    # Connect to TradingView
    await client.connect(session=session, signature=signature)

    # Initialize Chart session
    chart = client.new_chart()

    # Set configuration parameters
    config = {
        'symbol': 'BINANCE:BTCUSDT',  # Symbol
        'timeframe': '60',           # Timeframe (in minutes, or 'D' for daily)
        'range': 500,                # Number of K-lines to fetch
        'to': int(time.time()),      # End timestamp (defaults to current time)
        # 'from': 1672531200,        # Start timestamp (optional, not needed if to and range are set)
        'save_to_file': True,        # Whether to save to file
        'file_name': 'btcusdt_1h_data.json' # Filename to save
    }

    # Data update completion flag
    data_loaded = asyncio.Event()

    # Handle errors
    @chart.on_error
    async def on_error(*err):
        print('Error fetching data:', *err)
        data_loaded.set()

    # When symbol is loaded successfully
    @chart.on_symbol_loaded
    async def on_symbol_loaded():
        print(f"Symbol \"{chart.infos.description}\" loaded successfully!")
        print(f"Exchange: {chart.infos.exchange}")
        print(f"Timeframe: {config['timeframe']}")
        print(f"Requested K-lines: {config['range']}")

    # When price data updates
    @chart.on_update
    async def on_update():
        if len(chart.periods) >= config['range']:
            print(f"Successfully fetched {len(chart.periods)} K-line records")

            # Process and format data
            kline_data = chart.periods
            # Sort by time (asc)
            kline_data.sort(key=lambda x: x['time'])

            # Show first and last record
            print('First record:', kline_data[0])
            print('Last record:', kline_data[-1])

            # Optional: Save to file
            if config['save_to_file']:
                with open(config['file_name'], 'w') as f:
                    json.dump(kline_data, f, indent=4)
                print(f"Data saved to file: {config['file_name']}")

            # Mark data as loaded
            data_loaded.set()

    # Set market and parameters
    chart.set_market(config['symbol'], timeframe=config['timeframe'], range=config['range'])

    # Wait for completion
    try:
        # Set timeout to prevent infinite wait
        await asyncio.wait_for(data_loaded.wait(), timeout=30)
    except asyncio.TimeoutError:
        print("Operation timed out, forcing connection close")
    finally:
        # Close connection
        print('Data fetch complete, closing connection...')
        await client.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nProgram interrupted')
