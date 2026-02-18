
import unittest
import time
import core.data_engine
from core.data_engine import on_message, latest_total_volumes, last_emit_times

class TestDataEngineMerge(unittest.TestCase):
    def test_index_volume_merge(self):
        # Reset state
        latest_total_volumes.clear()
        last_emit_times.clear()
        core.data_engine.last_processed_tick.clear()

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
                    "upstox_volume": 0,
                    "ts_ms": 1700000001000,
                    "source": "upstox_wss"
                }
            }
        }

        # Capture emitted events
        emitted = []
        def mock_emit(event, data, room=None):
            emitted.append((event, data, room))

        core.data_engine.emit_event = mock_emit

        # Reset throttle to ensure both are emitted
        last_emit_times['GLOBAL_TICK'] = 0
        on_message(tv_msg)

        last_emit_times['GLOBAL_TICK'] = 0
        on_message(upstox_msg)

        # Check if Upstox tick was emitted
        raw_ticks = [e for e in emitted if e[0] == 'raw_tick']
        print(f"Emitted Ticks: {len(raw_ticks)}")
        for i, t in enumerate(raw_ticks):
             print(f"Tick {i}: {t[1]}")

        self.assertTrue(len(raw_ticks) >= 2)
        last_tick = raw_ticks[-1][1]["NSE:NIFTY"]
        self.assertEqual(last_tick["last_price"], 22060)

if __name__ == "__main__":
    unittest.main()
