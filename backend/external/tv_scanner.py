import httpx
import logging

logger = logging.getLogger(__name__)

async def search_options(underlying: str):
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-symbol-search"

    payload = {
        "columns": ["name", "description", "exchange", "expiry", "strike", "option_type", "underlying_symbol", "root"],
        "filter": [
            {"left": "underlying_symbol", "operation": "equal", "right": underlying.upper()},
            {"left": "type", "operation": "in_range", "right": ["option"]}
        ],
        "ignore_unknown_fields": True,
        "markets": ["india"],
        "options": {"lang": "en"},
        "range": [0, 100],
        "sort": {"column": "expiry", "direction": "asc"},
        "symbols": {"query": {"types": []}, "tickers": []}
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, headers=headers, timeout=15.0)
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Options scanner failed: {response.status_code} {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error calling options scanner: {e}")
        return None
