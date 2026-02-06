import httpx
import asyncio

async def test_scanner_url_param():
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-symbol-search&underlying_symbol=NSE:NIFTY"
    headers = {"Content-Type": "application/json"}

    payload = {
        "columns": ["name", "description", "exchange"],
        "range": [0, 10]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:500]}")

if __name__ == "__main__":
    asyncio.run(test_scanner_url_param())
