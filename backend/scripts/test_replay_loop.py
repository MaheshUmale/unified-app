from data_engine import ReplayManager, db

class MockSocket:
    def emit(self, event, data):
        print(f"[MOCK SOCKET] Emitted {event}: {str(data)[:200]}...")

def test_replay():
    print("Initializing ReplayManager...")
    manager = ReplayManager(db, MockSocket())

    instrument_key = "NSE_EQ|INE002A01018"
    print(f"Starting replay for {instrument_key}")

    # Run synchronously
    manager.start(instrument_key, speed=10, start_ts=None, timeframe=1)

if __name__ == "__main__":
    test_replay()
