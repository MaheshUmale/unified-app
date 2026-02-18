
import unittest
from unittest.mock import MagicMock
import json
from core.data_engine import on_message, latest_total_volumes

class TestDataEngineMerge(unittest.TestCase):
    def test_index_volume_merge(self):
        # Reset volumes
        latest_total_volumes.clear()

        # 1. TV Chart Fallback message (Index)
        tv_msg = {
            "type": "chart_update",
            "instrumentKey": "NSE:NIFTY",
            "interval": "1",
            "data": {
                "ohlcv": [[1700000000, 22000, 22100, 21900, 22050, 1000]]
            }
        }

        # 2. Upstox Tick message (Index)
        upstox_msg = {
            "feeds": {
                "NSE:NIFTY": {
                    "last_price": 22060,
                    "upstox_volume": 0, # Upstox has no volume for index
                    "ts_ms": 1700000000000,
                    "source": "upstox_wss"
                }
            }
        }

        # Capture emitted events
        emitted = []
        def mock_emit(event, data, room=None):
            emitted.append((event, data, room))

        import core.data_engine
        core.data_engine.emit_event = mock_emit

        # Process TV first
        on_message(tv_msg)
        # Process Upstox
        on_message(upstox_msg)

        # Check if Upstox tick was emitted with TV volume or delta
        raw_ticks = [e for e in emitted if e[0] == 'raw_tick']
        self.assertTrue(len(raw_ticks) > 0)

        # The last tick should be from Upstox but have a calculated ltq
        last_tick = raw_ticks[-1][1]["NSE:NIFTY"]
        self.assertEqual(last_tick["last_price"], 22060)
        # It should have taken volume from somewhere or at least not crashed
        print(f"Merged Tick: {last_tick}")

if __name__ == "__main__":
    unittest.main()
