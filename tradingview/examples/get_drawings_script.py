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

    # Check args
    if len(sys.argv) < 2:
        print("Error: Please specify a layoutID")
        print("Usage: python get_drawings_script.py <layout_id> [user_id]")
        return

    layout_id = sys.argv[1]
    user_id = sys.argv[2] if len(sys.argv) > 2 else None

    # Credentials
    session = os.getenv('TV_SESSION')
    signature = os.getenv('TV_SIGNATURE')

    client = TradingViewClient()
    try:
        await client.connect(session=session, signature=signature)
        # Assuming get_drawings exists on client
        if hasattr(client, 'get_drawings'):
            drawings = await client.get_drawings(layout_id, user_id)
            print(f"Found {len(drawings)} drawings")
            for d in drawings[:3]:
                print(d)
    except Exception as e:
        print(f"Error: {str(e)}")
    finally:
        await client.close()

if __name__ == '__main__':
    asyncio.run(main())
