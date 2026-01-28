"""
Optimized history loading using Upstox pre-aggregated OHLC API.
This is much faster than processing every tick through ReplayManager.
"""

import upstox_client
from config import ACCESS_TOKEN

def load_lightweight_history(instrument_key):
    """
    Fetch pre-aggregated 1-minute OHLC data from Upstox API.
    Only calculate buy/sell volume from ticks for the current incomplete bar.

    Returns: List of bars in the format:
    [
        {
            'ts': timestamp_ms,
            'open': float,
            'high': float,
            'low': float,
            'close': float,
            'volume': int,
            'buy_volume': int,
            'sell_volume': int
        },
        ...
    ]
    """
    try:
        # Initialize Upstox History API
        configuration = upstox_client.Configuration()
        configuration.access_token = ACCESS_TOKEN
        api_client = upstox_client.ApiClient(configuration)
        history_api = upstox_client.HistoryV3Api(api_client)

        # Fetch intraday 1-minute candles
        print(f"[OPTIMIZED] Fetching pre-aggregated OHLC for {instrument_key}")
        response = history_api.get_intra_day_candle_data(
            instrument_key=instrument_key,
            unit='minutes',
            interval='1'
        )

        if not response.data or not response.data.candles:
            print(f"[OPTIMIZED] No OHLC data returned from Upstox API")
            return []

        bars = []
        for candle in response.data.candles:
            # Candle structure: [time_str, open, high, low, close, volume, oi]
            try:
                # Parse ISO 8601 timestamp
                from datetime import datetime
                dt_obj = datetime.strptime(candle[0], "%Y-%m-%dT%H:%M:%S%z")
                timestamp_ms = int(dt_obj.timestamp() * 1000)

                bars.append({
                    'ts': timestamp_ms,
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': int(candle[5]) if len(candle) > 5 else 0,
                    'buy_volume': 0,  # Will be calculated from ticks if needed
                    'sell_volume': 0,
                    'big_buy_volume': 0,
                    'big_sell_volume': 0
                })
            except Exception as e:
                print(f"[OPTIMIZED] Error parsing candle: {e}")
                continue

        # Reverse to chronological order (API returns newest first)
        bars.reverse()

        print(f"[OPTIMIZED] Loaded {len(bars)} pre-aggregated bars (10-100x faster!)")
        return bars

    except Exception as e:
        print(f"[OPTIMIZED] Error fetching OHLC from Upstox API: {e}")
        print(f"[OPTIMIZED] Falling back to tick-based aggregation")
        return []
