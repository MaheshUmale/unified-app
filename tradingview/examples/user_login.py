import os
import sys
from getpass import getpass
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from tradingview.client import TradingViewClient

async def main():
    """User login example"""
    print("TradingView User Login Example")
    load_dotenv()

    # Create client
    client = TradingViewClient()

    # Get credentials from environment or input
    username = os.environ.get('TV_USERNAME') or input("Enter username or email: ")
    password = os.environ.get('TV_PASSWORD') or getpass("Enter password: ")

    try:
        # Attempt login
        print("\nLogging in...")
        # Assuming login method exists
        if hasattr(client, 'login'):
            user = await client.login(username, password)
            print(f"\nLogin successful!")
            print(f"Username: {user.username}")
            print(f"User ID: {user.id}")
            print(f"Join Date: {user.join_date}")
            print(f"Followers: {user.followers}")

            # Fetch private indicators
            print("\nFetching private indicators...")
            if hasattr(client, 'get_private_indicators'):
                indicators = await client.get_private_indicators()
                if indicators:
                    print(f"\nFound {len(indicators)} private indicators:")
                    for i, indic in enumerate(indicators[:5], 1):
                        print(f"{i}. {indic.name}")
                else:
                    print("\nNo private indicators found")

            # Session info
            print("\nSession info:")
            print("To use this session elsewhere, you can save:")
            print(f"Session ID: {user.session}")
            print(f"Session Signature: {user.signature}")
    except Exception as e:
        print(f"\nLogin failed: {e}")
    finally:
        await client.close()

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
