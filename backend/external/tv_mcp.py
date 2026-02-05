"""
TradingView Integration Layer (MCP-derived)
Provides access to TradingView's Option Scanner and other advanced data utilities.
"""
import requests
import logging
from typing import List, Dict, Optional, Any, Tuple
from http.cookies import SimpleCookie
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# Settings from environment
TV_COOKIE = os.getenv('TV_COOKIE', '')

def fetch_option_chain_data(
    symbol: str,
    exchange: str,
    expiry_date: Optional[int] = None
) -> Dict[str, Any]:
    """
    Fetches raw option chain data from TradingView scanner.
    """
    cookies = {}
    if TV_COOKIE:
        try:
            cookie = SimpleCookie()
            cookie.load(TV_COOKIE)
            cookies = {key: morsel.value for key, morsel in cookie.items()}
        except Exception as e:
            logger.warning(f"Failed to parse TV_COOKIE: {e}")

    try:
        print("Fetching option chain data from TradingView...")
        url = "https://scanner.tradingview.com/options/scan2?label-product=symbols-options"

        # Build filter
        filter_conditions = [
            {"left": "type", "operation": "equal", "right": "option"},
            {"left": "root", "operation": "equal", "right": symbol}
        ]

        if expiry_date is not None:
            filter_conditions.append(
                {"left": "expiration", "operation": "equal", "right": expiry_date}
            )

        payload = {
            "columns": [
                "ask", "bid", "currency", "delta", "expiration", "gamma",
                "iv", "option-type", "pricescale", "rho", "root", "strike",
                "theoPrice", "theta", "vega", "bid_iv", "ask_iv", "close", "volume"
            ],
            "filter": filter_conditions,
            "ignore_unknown_fields": False,
            "index_filters": [
                {"name": "underlying_symbol", "values": [f"{exchange}:{symbol}"]}
            ]
        }

        headers = {
            'Content-Type': 'text/plain;charset=UTF-8',
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:145.0) Gecko/20100101 Firefox/145.0',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://in.tradingview.com/',
            'Origin': 'https://in.tradingview.com',
            'Connection': 'keep-alive'
        }

        response = requests.post(url, json=payload, headers=headers, cookies=cookies, timeout=30)
        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict) or 'symbols' not in data:
            return {'success': False, 'message': 'Invalid response from TradingView', 'data': None}

        return {
            'success': True,
            'data': data,
            'total_count': data.get('totalCount', 0)
        }

    except Exception as e:
        logger.error(f"Failed to fetch option chain: {e}")
        return {'success': False, 'message': str(e), 'data': None}

def get_current_spot_price(symbol: str, exchange: str) -> Dict[str, Any]:
    """
    Get current spot price of underlying symbol.
    """
    try:
        print("Fetching current spot price...")
        url = "https://scanner.tradingview.com/global/scan2?label-product=options-overlay"

        payload = {
            "columns": ["close", "pricescale"],
            "ignore_unknown_fields": False,
            "symbols": {
                "tickers": [f"{exchange}:{symbol}"]
            }
        }

        headers = {
            'Content-Type': 'application/json',
            'User-Agent': 'Mozilla/5.0'
        }

        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, dict) and data.get('symbols') and len(data['symbols']) > 0:
            symbol_data = data['symbols'][0]
            close_price = symbol_data['f'][0]
            pricescale = symbol_data['f'][1]

            return {
                'success': True,
                'spot_price': close_price,
                'pricescale': pricescale
            }

        return {'success': False, 'message': 'No price data found'}

    except Exception as e:
        return {'success': False, 'message': str(e)}

def process_option_chain_with_analysis(
    symbol: str,
    exchange: str,
    expiry_date: Optional[str] = 'nearest',
    no_of_ITM: int = 5,
    no_of_OTM: int = 5
) -> Dict[str, Any]:
    """
    Processes option chain data and returns structured results with basic analysis.
    """
    try:
        # 1. Get spot price
        spot_result = get_current_spot_price(symbol, exchange)
        if not spot_result['success']:
            return spot_result
        spot_price = spot_result['spot_price']

        # 2. Fetch all option chain data
        option_result = fetch_option_chain_data(symbol, exchange)
        if not option_result['success']:
            return option_result

        raw_data = option_result['data']
        fields = raw_data.get('fields', [])
        symbols_data = raw_data.get('symbols', [])

        if not symbols_data:
            return {'success': False, 'message': 'No option data available'}

        # Map fields to results
        flat_options = []
        expiries = set()

        for item in symbols_data:
            symbol_name = item['s']
            values = item['f']
            opt_data = {}
            for i, field in enumerate(fields):
                opt_data[field] = values[i] if i < len(values) else None

            expiration = opt_data.get('expiration')
            if expiration: expiries.add(expiration)

            # Basic mapping to our internal structure
            flat_options.append({
                'symbol': symbol_name,
                'expiration': expiration,
                'strike': opt_data.get('strike'),
                'type': opt_data.get('option-type'),
                'ask': opt_data.get('ask'),
                'bid': opt_data.get('bid'),
                'close': opt_data.get('close'),
                'iv': opt_data.get('iv'),
                'delta': opt_data.get('delta'),
                'gamma': opt_data.get('gamma'),
                'theta': opt_data.get('theta'),
                'vega': opt_data.get('vega'),
                'oi': 0, # OI not available in this scanner
                'volume': opt_data.get('volume', 0)
            })

        available_expiries = sorted(list(expiries))
        current_date_int = int(datetime.now().strftime('%Y%m%d'))

        # Filter by expiry
        target_expiry = None
        if expiry_date == 'nearest':
            for exp in available_expiries:
                if exp >= current_date_int:
                    target_expiry = exp
                    break
            if not target_expiry and available_expiries: target_expiry = available_expiries[0]
        elif expiry_date == 'all':
            pass
        else:
            try:
                target_expiry = int(expiry_date)
            except:
                target_expiry = available_expiries[0] if available_expiries else None

        if target_expiry and expiry_date != 'all':
            flat_options = [opt for opt in flat_options if opt['expiration'] == target_expiry]

        return {
            'success': True,
            'spot_price': spot_price,
            'target_expiry': target_expiry,
            'available_expiries': available_expiries,
            'data': flat_options
        }

    except Exception as e:
        logger.error(f"Error processing option chain: {e}")
        return {'success': False, 'message': str(e)}
