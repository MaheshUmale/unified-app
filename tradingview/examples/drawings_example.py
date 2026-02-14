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

    try:
        # Create chart
        chart = client.new_chart()
        chart.set_market('BINANCE:BTCUSDT', timeframe='60')

        # Wait for chart ready
        await asyncio.sleep(5)

        # Get drawings
        print("Fetching drawings...")
        # Assuming get_drawings method exists
        if hasattr(chart, 'get_drawings'):
            drawings = await chart.get_drawings()
            print(f"Found {len(drawings)} drawings")

            if drawings:
                first_drawing = drawings[0]
                print("\nFirst drawing details example:")
                print(f"Type: {first_drawing.get('type', 'unknown')}")

                # Show points if available
                if 'points' in first_drawing:
                    print("\nPoints:")
                    for i, point in enumerate(first_drawing['points']):
                        print(f"Point {i+1}: {point}")
    except Exception as e:
        print(f"Failed to fetch drawings: {e}")
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
