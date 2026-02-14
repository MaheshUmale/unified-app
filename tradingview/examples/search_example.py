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

    # Create client
    client = TradingViewClient()

    print("===== Testing Search Functionality =====")

    try:
        # Search for markets
        print("\nSearching market: BINANCE:")
        markets = await client.search_market("BINANCE:")
        if markets:
            print(f"Found {len(markets)} markets:")
            for i, market in enumerate(markets[:5], 1):
                print(f"{i}. {market.id} - {market.description} ({market.exchange})")

            if len(markets) > 5:
                print(f"... and {len(markets) - 5} more markets")

            # Search for a specific pair
            market_name = "BINANCE:BTCUSDT"
            try:
                print(f"\nSearching specific pair: {market_name}")
                specific_markets = await client.search_market(market_name)
                if specific_markets:
                    market = specific_markets[0]
                    print(f"Found pair: {market.id}")
                    print(f"Description: {market.description}")
                    print(f"Exchange: {market.exchange}")
                    print(f"Type: {market.type}")

                    # Fetch technical analysis data
                    print("\nFetching technical analysis data...")
                    try:
                        # Assuming get_ta method exists
                        if hasattr(client, 'get_ta'):
                            ta_data = await client.get_ta(market.exchange, market.id.split(':')[-1])
                            if ta_data:
                                print("Technical Analysis results:")
                                print(ta_data)
                            else:
                                print("Unable to fetch TA data")
                    except Exception as e:
                        print(f"Error fetching TA data: {str(e)}")
                else:
                    print(f"No matching pair found: {market_name}")
            except Exception as e:
                print(f"Error searching specific pair: {str(e)}")
        else:
            print("No markets found")

        # Search for indicators
        print("\nSearching indicator: RSI")
        indicators = await client.search_indicator("RSI")
        if indicators:
            print(f"Found {len(indicators)} indicators:")
            for i, indicator in enumerate(indicators[:5], 1):
                print(f"{i}. {indicator.name} - Author: {indicator.author['username']} - Type: {indicator.type}")

            if len(indicators) > 5:
                print(f"... and {len(indicators) - 5} more indicators")

        # Search for other types of indicators
        print("\nSearching indicator: MACD")
        macd_indicators = await client.search_indicator("MACD")
        if macd_indicators:
            print(f"Found {len(macd_indicators)} MACD related indicators")

            # Built-in vs Custom
            builtin_count = sum(1 for x in macd_indicators if x.type == 'builtin')
            custom_count = sum(1 for x in macd_indicators if x.type != 'builtin')

            print("\nIndicator categories:")
            print(f"Built-in indicators: {builtin_count}")
            print(f"Custom indicators: {custom_count}")

    except Exception as e:
        print(f"Search error: {str(e)}")
        print(f"Error type: {type(e)}")

    finally:
        await client.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\nProgram interrupted')
    except Exception as e:
        print(f"Program execution error: {str(e)}")
