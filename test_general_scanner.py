import httpx
import asyncio

async def test_general_scanner():
    url = "https://scanner.tradingview.com/india/scan"
    headers = {"Content-Type": "application/json"}

    payload = {
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"},
            {"left": "name", "operation": "match", "right": "NIFTY"}
        ],
        "columns": ["name", "description", "exchange"],
        "range": [0, 10]
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:500]}")

if __name__ == "__main__":
    asyncio.run(test_general_scanner())
