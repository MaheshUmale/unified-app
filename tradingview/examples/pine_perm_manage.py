import os
import sys
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

    # Get Pine ID from args
    if len(sys.argv) < 2:
        print('Usage: python pine_perm_manage.py <PINE_ID>')
        return

    pine_id = sys.argv[1]

    # Create client
    client = TradingViewClient()
    await client.connect(session=session, signature=signature)

    # Create Pine permission manager
    # Assuming client has a get_pine_manager method or similar
    # For this example, we'll demonstrate the intended API usage
    try:
        # Get authorized users
        users = await client.get_pine_privileges(pine_id)
        print('Authorized users:', users)

        # Add user 'TradingView' as an example
        print("Adding user 'TradingView'...")
        result = await client.add_pine_privilege(pine_id, 'TradingView')
        if result:
            print('Added successfully!')
        else:
            print('User already authorized or unknown error')

        # Get authorized users again
        users = await client.get_pine_privileges(pine_id)
        print('Authorized users:', users)

        # Remove user 'TradingView'
        print("Removing user 'TradingView'...")
        result = await client.remove_pine_privilege(pine_id, 'TradingView')
        if result:
            print('Removed successfully!')
        else:
            print('Unknown error')

        # Final check
        users = await client.get_pine_privileges(pine_id)
        print('Final authorized users:', users)

    finally:
        await client.close()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
