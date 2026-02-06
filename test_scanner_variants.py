import httpx
import asyncio
import json

async def test_scanner_variants():
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-symbol-search"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }

    variants = [
        # Variant 1: underlying_symbol in filter
        {
            "filter": [{"left": "underlying_symbol", "operation": "equal", "right": "NSE:NIFTY"}],
            "markets": ["india"]
        },
        # Variant 2: underlying_symbol_id in filter
        {
            "filter": [{"left": "underlying_symbol_id", "operation": "equal", "right": "NSE:NIFTY"}],
            "markets": ["india"]
        },
        # Variant 3: simple search
        {
            "filter": [{"left": "name", "operation": "match", "right": "NIFTY"}],
            "markets": ["india"]
        }
    ]

    async with httpx.AsyncClient() as client:
        for i, payload in enumerate(variants):
            print(f"Testing Variant {i+1}...")
            response = await client.post(url, json=payload, headers=headers)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text[:200]}")

if __name__ == "__main__":
    asyncio.run(test_scanner_variants())
