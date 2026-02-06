import httpx
import asyncio

async def test_scanner_dict_filter():
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-symbol-search"
    headers = {"Content-Type": "application/json"}

    payload = {
        "filter": [
            {"left": "underlying_symbol", "operation": "equal", "right": "NSE:NIFTY"}
        ],
        "columns": ["name", "description", "exchange"]
    }
    # Wait, I'll try with more common fields

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        print(f"Response: {response.text[:500]}")

if __name__ == "__main__":
    asyncio.run(test_scanner_dict_filter())
