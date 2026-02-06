import httpx
import asyncio

async def test_scanner_final_guess():
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-symbol-search"
    headers = {"Content-Type": "application/json"}

    payloads = [
        {"underlying_symbol": ["NSE:NIFTY"]},
        {"underlying_symbol": "NSE:NIFTY"},
        {"symbols": {"tickers": ["NSE:NIFTY"]}},
        {"filter": [{"left": "underlying_symbol", "operation": "in_range", "right": ["NSE:NIFTY"]}]}
    ]

    async with httpx.AsyncClient() as client:
        for p in payloads:
            print(f"Testing {p}...")
            response = await client.post(url, json=p, headers=headers)
            print(f"Response: {response.text[:200]}")

if __name__ == "__main__":
    asyncio.run(test_scanner_final_guess())
