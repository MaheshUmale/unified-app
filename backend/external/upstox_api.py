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
        from core.symbol_mapper import symbol_mapper
        api_instance = upstox_client.OptionsApi(self.api_client)
        try:
            # SDK call as per user instructions
            response = api_instance.get_put_call_option_chain(instrument_key, expiry_date)

            chain_data = []
            for item in response.data:
                entry = {
                    'strike_price': item.strike_price,
                    'call_options': None,
                    'put_options': None
                }

                if item.call_options:
                    # Map to HRN
                    hrn = symbol_mapper.get_hrn(item.call_options.instrument_key, {
                        'symbol': symbol_mapper.get_symbol(instrument_key),
                        'type': 'CE',
                        'strike': item.strike_price,
                        'expiry': expiry_date
                    })
                    entry['call_options'] = {
                        'instrument_key': hrn,
                        'market_data': {
                            'oi': item.call_options.market_data.oi,
                            'ltp': item.call_options.market_data.ltp
                        }
                    }

                if item.put_options:
                    # Map to HRN
                    hrn = symbol_mapper.get_hrn(item.put_options.instrument_key, {
                        'symbol': symbol_mapper.get_symbol(instrument_key),
                        'type': 'PE',
                        'strike': item.strike_price,
                        'expiry': expiry_date
                    })
                    entry['put_options'] = {
                        'instrument_key': hrn,
                        'market_data': {
                            'oi': item.put_options.market_data.oi,
                            'ltp': item.put_options.market_data.ltp
                        }
                    }
                chain_data.append(entry)

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
            # Using plural "minutes" as per latest SDK requirement for intraday
            count = int(interval)
            response = api_instance.get_intra_day_candle_data(instrument_key, "minutes", count)
            # Map SDK response to expected dict format
            candles = response.data.candles if hasattr(response.data, 'candles') else []
            return {"status": "success", "data": {"candles": candles}}
        except Exception as e:
            logger.error(f"Exception when calling HistoryV3Api->get_intra_day_candle_data: {e}")
            return None

    def get_historical_candles(self, instrument_key: str, interval: str, to_date: str, from_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Fetches historical candle data using Upstox History SDK."""
        api_instance = upstox_client.HistoryV3Api(self.api_client)
        try:
 
            # Map interval to SDK units
            unit = "minutes"

            count = 1
            if interval == "1":
                unit = "minutes"
                count = 1
            elif interval == "30":
                unit = "minutes"
                count = 30
            elif interval == "1D":
                unit = "days"
                count = 1

            if from_date:
                response = api_instance.get_historical_candle_data1(instrument_key, unit, count, to_date, from_date)
            else:
                response = api_instance.get_historical_candle_data(instrument_key, unit, count, to_date)

            candles = response.data.candles if hasattr(response.data, 'candles') else []
            return {"status": "success", "data": {"candles": candles}}
        except Exception as e:
            logger.error(f"Exception when calling HistoryV3Api->get_historical_candle: {e}")
            return None
