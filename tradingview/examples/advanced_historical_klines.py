import os
import sys
import asyncio
import time
import json
from datetime import datetime
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from tradingview.client import TradingViewClient

# Configuration
config = {
    'symbol': 'BINANCE:BTCUSDT',  # Symbol
    'timeframe': '60',           # Timeframe ('1', '5', '15', '60', 'D', etc.)
    'range': 300,                # Number of K-lines
    'format': 'json',            # Output format: 'json' or 'csv'
    'output': 'btc_data.json',   # Output file
    'indicators': True,          # Whether to add indicators
    'debug': True                # Whether to enable debug output
}

def debug_print(msg):
    if config['debug']:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

async def main():
    """Main function"""
    load_dotenv()

    # Credentials
    session = os.getenv('TV_SESSION')
    signature = os.getenv('TV_SIGNATURE')

    if not session or not signature:
        print("Error: TradingView credentials required.")
        print("Please set environment variables TV_SESSION and TV_SIGNATURE.")
        return

    debug_print(f"Using Token: {session[:10]}...")
    debug_print(f"Using Signature: {signature[:10]}...")

    try:
        # Create client
        debug_print("Creating TradingView client...")
        client = TradingViewClient()

        # Connect
        debug_print("Connecting to TradingView server...")
        await client.connect(session=session, signature=signature)
        debug_print("Connection successful!")

        # Create Chart session
        debug_print("Creating Chart session...")
        chart = client.new_chart()

        # Indicator data storage
        indicators_data = {}

        # Event for data loaded
        data_loaded = asyncio.Event()

        # Handle errors
        @chart.on_error
        async def on_error(*err):
            print('Error:', *err)
            data_loaded.set()

        # Timeout task
        async def timeout_task():
            await asyncio.sleep(90)
            if not data_loaded.is_set():
                print("Operation timed out, maybe symbol doesn't exist or network issue")
                data_loaded.set()

        asyncio.create_task(timeout_task())

        # Ensure WebSocket connection is established
        debug_print("Waiting for WebSocket connection to stabilize...")
        await asyncio.sleep(1)

        # Set market
        debug_print(f"Setting market: {config['symbol']}")
        chart.set_market(config['symbol'], timeframe=config['timeframe'], range=config['range'])

        # When symbol is loaded
        @chart.on_symbol_loaded
        async def on_symbol_loaded():
            debug_print("Symbol loaded successfully!")
            print(f"Symbol \"{chart.infos.description}\" loading data...")

            # Add indicators if needed
            if config['indicators']:
                await add_indicators(chart, indicators_data)

        # When data updates
        @chart.on_update
        async def on_update():
            # Check data validity
            if not chart.periods:
                debug_print("Waiting for data...")
                return

            print(f"Fetched {len(chart.periods)} K-line records")

            if len(chart.periods) >= config['range']:
                try:
                    # Process data
                    kline_data = []
                    for p in chart.periods:
                        try:
                            item = {
                                'time': p['time'],
                                'datetime': datetime.fromtimestamp(p['time']).strftime('%Y-%m-%d %H:%M:%S'),
                                'open': p['open'],
                                'high': p['high'],
                                'low': p['low'],
                                'close': p['close'],
                                'volume': p['volume']
                            }
                            kline_data.append(item)
                        except Exception as e:
                            print(f"Error processing K-line data: {e}")

                    if not kline_data:
                        print("No valid data fetched, continuing wait...")
                        return

                    # Sort by time
                    kline_data.sort(key=lambda x: x['time'])

                    # Display range
                    print(f"Data time range: {kline_data[0]['datetime']} to {kline_data[-1]['datetime']}")

                    # Export data
                    await export_data(kline_data, indicators_data)

                    # Mark as loaded
                    data_loaded.set()

                except Exception as e:
                    print(f"Error in on_update: {e}")

        # Wait for data or timeout
        await data_loaded.wait()

        # Close connection
        print('Data fetch complete, closing connection...')
        await client.close()
        print("Connection closed")

    except Exception as e:
        print(f"Program exception: {str(e)}")
    except KeyboardInterrupt:
        print('\nProgram interrupted')

async def add_indicators(chart, indicators_data):
    """Add technical indicators"""
    print('Adding technical indicators...')
    try:
        # Example: Add EMA
        results = await chart.client.search_indicator('EMA')
        if results:
            indic = results[0]
            indicator_name = 'EMA'

            # Create study
            study = chart.new_study(indic)
            study.set_option('Length', 14)

            @study.on_update
            async def on_study_update(s=study):
                if s.periods:
                    indicators_data[indicator_name] = s.periods
                    print(f"{indicator_name} data updated, total {len(indicators_data[indicator_name])} records")

    except Exception as e:
        print('Failed to add indicator:', e)

async def export_data(kline_data, indicators_data):
    """Export data to file"""
    file_path = config['output']
    try:
        if config['format'] == 'json':
            # Combine indicators if needed (simplified for this example)
            output_data = {
                'klines': kline_data,
                'indicators': indicators_data
            }
            with open(file_path, 'w') as f:
                json.dump(output_data, f, indent=4)
        elif config['format'] == 'csv':
            # Create CSV content
            import csv
            with open(file_path, 'w', newline='') as f:
                if kline_data:
                    writer = csv.DictWriter(f, fieldnames=kline_data[0].keys())
                    writer.writeheader()
                    writer.writerows(kline_data)
        else:
            raise ValueError(f"Unsupported output format: {config['format']}")

        print(f"Data saved to: {file_path}")
    except Exception as e:
        print('Error saving data:', e)

if __name__ == '__main__':
    asyncio.run(main())
