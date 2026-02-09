import httpx
import logging
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

class TrendlyneAPI:
    def __init__(self):
        self.base_url = "https://smartoptions.trendlyne.com/phoenix/api"
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        self.stock_id_cache = {}

    async def get_stock_id(self, symbol: str) -> Optional[int]:
        if symbol in self.stock_id_cache:
            return self.stock_id_cache[symbol]

        url = f"{self.base_url}/search-contract-stock/"
        params = {'query': symbol.lower()}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if data and 'body' in data and 'data' in data['body'] and len(data['body']['data']) > 0:
                        stock_id = data['body']['data'][0]['stock_id']
                        if stock_id:
                            self.stock_id_cache[symbol] = stock_id
                            return stock_id
        except Exception as e:
            logger.error(f"Error looking up stock ID for {symbol}: {e}")
        return None

    async def get_expiry_dates(self, stock_id: int) -> List[str]:
        url = f"{self.base_url}/fno/get-expiry-dates/"
        params = {'mtype': 'options', 'stock_id': stock_id}

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=self.headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if 'body' in data and 'expiryDates' in data['body']:
                        return data['body']['expiryDates']
        except Exception as e:
            logger.error(f"Error getting expiry dates for stock_id {stock_id}: {e}")
        return []

    async def get_oi_data(self, stock_id: int, expiry: str, max_time: str) -> Optional[Dict[str, Any]]:
        """
        Fetch OI data snapshot.
        max_time: HH:MM
        """
        url = f"{self.base_url}/live-oi-data/"
        params = {
            'stockId': stock_id,
            'expDateList': expiry,
            'minTime': "09:15",
            'maxTime': max_time
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, params=params, headers=self.headers, timeout=15)
                if response.status_code == 200:
                    return response.json()
        except Exception as e:
            logger.error(f"Error fetching OI data from Trendlyne: {e}")
        return None

trendlyne_api = TrendlyneAPI()
