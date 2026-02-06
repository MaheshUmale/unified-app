import httpx
import asyncio
import json

async def test_scanner_top_level(underlying):
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-symbol-search"

    payload = {
        "underlying_symbol": underlying,
        "columns": ["name", "description", "exchange", "expiry", "strike", "option_type"],
        "markets": ["india"],
        "range": [0, 10],
        "sort": {"column": "expiry", "direction": "asc"}
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        print(f"Testing with {underlying} (top level)...")
        response = await client.post(url, json=payload, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:500]}")

if __name__ == "__main__":
    asyncio.run(test_scanner_top_level("NSE:NIFTY"))
