import httpx
import asyncio

async def test_scanner_index():
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-symbol-search"
    headers = {"Content-Type": "application/json"}

    payload = {
        "index": "NSE:NIFTY",
        "columns": ["name", "description", "exchange", "expiry", "strike", "option_type"],
        "markets": ["india"]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        print(f"Response: {response.text[:500]}")

if __name__ == "__main__":
    asyncio.run(test_scanner_index())
