
import sys
import os
import json
import time
from unittest.mock import MagicMock
from datetime import datetime

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

# Mock dependencies
sys.modules['db.local_db'] = MagicMock()
sys.modules['core.provider_registry'] = MagicMock()
sys.modules['core.symbol_mapper'] = MagicMock()

import core.data_engine as data_engine

# Reset global state
data_engine.latest_total_volumes = {}
data_engine.UPSTOX_INDEX_MAP = {"NSE:NIFTY": "NSE_INDEX|Nifty 50"}
data_engine.last_processed_tick = {}
data_engine.last_emit_times = {}
data_engine.room_subscribers = {
    ("NSE:NIFTY", "1"): {"sid1"},
    ("NSE:NIFTY", "5"): {"sid1"}
}

def test_volume_logic():
    inst = "NSE:NIFTY"

    # We need to capture the emitted events
    emitted = []
    def mock_emit(event, data, room=None):
        if event == 'raw_tick':
            emitted.append(data)
    data_engine.emit_event = mock_emit

    print("Starting Multi-Interval Volume Logic Test...")

    # 1. 1m Interval update: Should generate a tick
    msg1 = {
        'type': 'chart_update',
        'instrumentKey': inst,
        'interval': '1',
        'data': {
            'ohlcv': [[1700000000.0, 100.0, 101.0, 99.0, 100.5, 500.0]]
        }
    }
    data_engine.on_message(msg1)
    tick1 = emitted[-1][inst]
    print(f"Tick 1 (1m Candle 500): ltq={tick1['ltq']}, source={tick1['source']}")
    assert tick1['ltq'] == 1, "Expected ltq=1 (first tick index)"

    data_engine.last_emit_times = {}

    # 2. 5m Interval update: Should NOT generate a tick (since 1m is primary)
    prev_emitted_count = len(emitted)
    msg2 = {
        'type': 'chart_update',
        'instrumentKey': inst,
        'interval': '5',
        'data': {
            'ohlcv': [[1700000000.0, 100.0, 101.0, 99.0, 100.5, 2500.0]]
        }
    }
    data_engine.on_message(msg2)
    assert len(emitted) == prev_emitted_count, "Expected NO raw_tick from 5m interval when 1m is active"
    print("Tick 2 (5m Candle): Correctly suppressed.")

    data_engine.last_emit_times = {}

    # 3. 1m Interval update again: Should generate a delta from PREVIOUS 1m volume
    msg3 = {
        'type': 'chart_update',
        'instrumentKey': inst,
        'interval': '1',
        'data': {
            'ohlcv': [[1700000000.0, 100.0, 101.0, 99.0, 100.5, 510.0]]
        }
    }
    data_engine.on_message(msg3)
    tick3 = emitted[-1][inst]
    print(f"Tick 3 (1m Candle 510): ltq={tick3['ltq']}, source={tick3['source']}")
    assert tick3['ltq'] == 10, f"Expected ltq=10, got {tick3['ltq']}"

    # 4. Remove 1m subscriber, now 5m is primary
    del data_engine.room_subscribers[("NSE:NIFTY", "1")]
    data_engine.last_emit_times = {}

    msg4 = {
        'type': 'chart_update',
        'instrumentKey': inst,
        'interval': '5',
        'data': {
            'ohlcv': [[1700000000.0, 100.0, 101.0, 99.0, 100.5, 2550.0]]
        }
    }
    data_engine.on_message(msg4)
    tick4 = emitted[-1][inst]
    print(f"Tick 4 (5m Candle 2550, now primary): ltq={tick4['ltq']}, source={tick4['source']}")
    # It should be 1 because it's the first time the 5m tracker sees volume
    assert tick4['ltq'] == 1, f"Expected ltq=1, got {tick4['ltq']}"

    # 5. Second update for 5m primary
    data_engine.last_emit_times = {}
    msg5 = {
        'type': 'chart_update',
        'instrumentKey': inst,
        'interval': '5',
        'data': {
            'ohlcv': [[1700000000.0, 100.0, 101.0, 99.0, 100.5, 2565.0]]
        }
    }
    data_engine.on_message(msg5)
    tick5 = emitted[-1][inst]
    print(f"Tick 5 (5m Candle 2565): ltq={tick5['ltq']}, source={tick5['source']}")
    assert tick5['ltq'] == 15, f"Expected ltq=15, got {tick5['ltq']}"

    print("\nALL TESTS PASSED!")

if __name__ == "__main__":
    test_volume_logic()
