"""
Upstox REST API Client (External API Access)
Provides methods for fetching historical data, quotes, and option chains.
"""
import requests
import logging
from typing import Dict, Any, Optional, List
import upstox_client
from upstox_client.rest import ApiException

logger = logging.getLogger(__name__)

class UpstoxAPI:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.configuration = upstox_client.Configuration()
        self.configuration.access_token = access_token
        self.api_client = upstox_client.ApiClient(self.configuration)

    def get_last_price(self, instrument_keys: List[str]) -> Dict[str, Any]:
        """Fetches the last traded price for given instruments."""
        api_instance = upstox_client.MarketQuoteV3Api(self.api_client)
        try:
            keys_str = ",".join(instrument_keys)
            response = api_instance.get_ltp(instrument_key=keys_str)
            return response.data
        except ApiException as e:
            logger.error(f"Exception when calling MarketQuoteV3Api->get_ltp: {e}")
            return {}

    def get_option_chain(self, instrument_key: str, expiry_date: str) -> Optional[Dict[str, Any]]:
        """Fetches the option chain for a given underlying and expiry."""
        url = 'https://api.upstox.com/v2/option/chain'
        params = {
            'instrument_key': instrument_key,
            'expiry_date': expiry_date
        }
        headers = {
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }
        try:
            response = requests.get(url, params=params, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching option chain: {e}")
            return None
