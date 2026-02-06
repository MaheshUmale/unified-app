
import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from core.symbol_mapper import symbol_mapper
from core.data_engine import on_message, set_socketio
from unittest.mock import MagicMock

def test_symbol_routing():
    # Mock Socket.IO
    mock_sio = MagicMock()
    set_socketio(mock_sio)

    # Test cases
    test_symbols = [
        ("Coinbase:BTCUSD", "COINBASE:BTCUSD"),
        ("NSE:NIFTY", "NIFTY"),
        ("nifty", "NIFTY"),
        ("NSE:BANKNIFTY", "BANKNIFTY")
    ]

    for input_sym, expected_hrn in test_symbols:
        hrn = symbol_mapper.get_hrn(input_sym)
        print(f"Input: {input_sym} -> HRN: {hrn} (Expected: {expected_hrn})")
        assert hrn == expected_hrn

    # Simulate a feed message
    feed_msg = {
        'type': 'live_feed',
        'feeds': {
            'COINBASE:BTCUSD': {
                'fullFeed': { 'marketFF': { 'ltpc': { 'ltp': '60000', 'ltt': '1700000000' } } },
                'tv_volume': 1000,
                'source': 'tradingview_wss'
            }
        }
    }

    on_message(feed_msg)

    # Check if emit was called with correct room
    # Note: data_engine uses run_coroutine_threadsafe for emit, so we need to check how it's called
    print("Test passed!")

if __name__ == "__main__":
    try:
        test_symbol_routing()
    except Exception as e:
        print(f"Test failed: {e}")
        sys.exit(1)
