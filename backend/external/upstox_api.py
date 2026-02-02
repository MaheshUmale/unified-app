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
        """Fetches the option chain for a given underlying and expiry using official SDK."""
        api_instance = upstox_client.OptionsApi(self.api_client)
        try:
            # SDK call as per user instructions
            response = api_instance.get_put_call_option_chain(instrument_key, expiry_date)

            # Convert SDK response to dictionary format expected by the app
            # SDK objects usually have a to_dict() method
            if hasattr(response, 'to_dict'):
                return response.to_dict()

            # Fallback manual mapping if to_dict is not as expected
            chain_data = []
            for item in response.data:
                chain_data.append({
                    'strike_price': item.strike_price,
                    'call_options': {
                        'instrument_key': item.call_options.instrument_key,
                        'market_data': {
                            'oi': item.call_options.market_data.oi,
                            'ltp': item.call_options.market_data.ltp
                        }
                    } if item.call_options else None,
                    'put_options': {
                        'instrument_key': item.put_options.instrument_key,
                        'market_data': {
                            'oi': item.put_options.market_data.oi,
                            'ltp': item.put_options.market_data.ltp
                        }
                    } if item.put_options else None
                })
            return {"status": "success", "data": chain_data}

        except ApiException as e:
            logger.error(f"Exception when calling OptionsApi->get_put_call_option_chain: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching option chain via SDK: {e}")
            return None

    def get_intraday_candles(self, instrument_key: str, interval: str = '1') -> Optional[Dict[str, Any]]:
        """Fetches intraday candle data using Upstox History SDK."""
        api_instance = upstox_client.HistoryV3Api(self.api_client)
        try:
            count = int(interval)
            response = api_instance.get_intra_day_candle_data(instrument_key, "minutes", count)
            # Map SDK response to expected dict format
            return {"status": "success", "data": {"candles": response.data.candles if hasattr(response.data, 'candles') else []}}
        except Exception as e:
            logger.error(f"Exception when calling HistoryV3Api->get_intra_day_candle_data: {e}")
            return None

    def get_historical_candles(self, instrument_key: str, interval: str, to_date: str, from_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetches historical candle data using Upstox History SDK."""
        api_instance = upstox_client.HistoryV3Api(self.api_client)
        try:
            iv_name = "minutes"
            iv_val = "1"
        #    if interval == "15":
        #         iv_name = "minutes"
        #         iv_val = "15"
        #     elif interval == "60":
        #         iv_name = "hour"
        #         iv_val = "1"
        #     elif interval == "1D":
        #         iv_name = "day"
        #         iv_val = "1"
        #     elif interval == "1W":
        #         iv_name = "week"
        #         iv_val = "1"
        #     elif interval == "1M":
        #         iv_name = "month"
        #         iv_val = "1"

            if from_date:
                print
                response = api_instance.get_historical_candle_data1(instrument_key, iv_name, iv_val, to_date, from_date)
            else:
                response = api_instance.get_historical_candle_data(instrument_key, unit, count, to_date)

            return {"status": "success", "data": {"candles": response.data.candles if hasattr(response.data, 'candles') else []}}
        except Exception as e:
            logger.error(f"Exception when calling HistoryV3Api->get_historical_candle: {e}")
            return None
