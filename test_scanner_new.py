import httpx
import asyncio
import json

async def test_scanner(underlying):
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-symbol-search"

    payload = {
        "columns": ["option-type", "strike"],
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"},
            {"left": "root", "operation": "equal", "right": underlying}
        ],
        "ignore_unknown_fields": False,
        "sort": {"sortBy": "name", "sortOrder": "asc"},
        "index_filters": [
            {"name": "underlying_symbol", "values": [f"NSE:{underlying}"]}
        ]
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Total Count: {data.get('totalCount')}")
            symbols = data.get('symbols', [])
            print(f"Got {len(symbols)} symbols")
            if symbols:
                print(f"First symbol: {symbols[0]}")
        else:
            print(f"Error: {response.text}")

if __name__ == "__main__":
    asyncio.run(test_scanner("NIFTY"))
