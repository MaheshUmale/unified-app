import httpx
import logging
from config import TV_COOKIE

logger = logging.getLogger(__name__)

async def fetch_option_chain(underlying: str):
    """
    Fetches the full option chain for a given underlying from TradingView Scanner.
    underlying: e.g. 'NSE:NIFTY'
    """
    # Use options-builder product as suggested by user
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-builder"

    # Standardize underlying
    if ":" not in underlying:
        tv_underlying = f"NSE:{underlying}"
    else:
        tv_underlying = underlying

    root = tv_underlying.split(":")[-1]

    payload = {
        "columns": [
            "name", "description", "option-type", "strike", "volume", "close", "expiration",
            "ask", "bid", "delta", "gamma", "iv", "rho", "theta", "vega", "theoPrice"
        ],
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"},
            {"left": "root", "operation": "equal", "right": root}
        ],
        "ignore_unknown_fields": True,
        "sort": {"sortBy": "name", "sortOrder": "asc"},
        "index_filters": [
            {"name": "underlying_symbol", "values": [tv_underlying]}
        ],
        "limit": 1000
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://www.tradingview.com/",
        "Origin": "https://www.tradingview.com"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                json=payload,
                headers=headers,
                timeout=30.0
            )
            if response.status_code == 200:
                data = response.json()
                count = len(data.get('symbols', []))
                logger.info(f"Fetched {count} options for {underlying} using options-builder")
                return data
            else:
                logger.error(f"Options builder failed: {response.status_code} {response.text}")
                return None
    except Exception as e:
        logger.error(f"Error calling options builder: {e}")
        return None
