import requests
import json
import sys

BASE_URL = "http://localhost:5051"

def test_endpoint(method, path, params=None, json_data=None):
    url = f"{BASE_URL}{path}"
    print(f"Testing {method} {url}...", end=" ")
    try:
        if method == "GET":
            resp = requests.get(url, params=params, timeout=10)
        elif method == "POST":
            resp = requests.post(url, json=json_data, timeout=10)

        if resp.status_code == 200:
            print("SUCCESS")
            # Try to parse JSON to ensure it's valid
            try:
                data = resp.json()
                # print(f"  Response: {str(data)[:100]}...")
            except:
                print("  Warning: Valid status but NOT JSON")
            return True
        else:
            print(f"FAILED (Status: {resp.status_code})")
            print(f"  Detail: {resp.text}")
            return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False

def run_all_tests():
    success = True

    endpoints = [
        ("GET", "/health"),
        ("GET", "/api/instruments"),
        ("GET", "/api/replay/dates"),
        ("GET", "/api/live_pnl"),
        ("GET", "/api/trendlyne/expiry/NIFTY"),
        ("GET", "/api/analytics/pcr/NIFTY"),
        # These might fail if no data exists, but we check if the route exists
        ("GET", "/api/upstox/intraday/NSE_INDEX%7CNifty%2050"),
        ("GET", "/api/upstox/option_chain/NSE_INDEX%7CNifty%2050/2026-02-03"),
        ("GET", "/api/oi_data/NSE_INDEX%7CNifty%2050"),
        ("GET", "/api/trendlyne/buildup/futures/NIFTY/3-feb-2026-near"),
        ("GET", "/api/trendlyne/buildup/options/NIFTY/3-feb-2026-near/24300/call"),
    ]

    for method, path in endpoints:
        if not test_endpoint(method, path):
            # We don't necessarily stop on failure if it's just missing data
            pass

    # Test Trade Signals (needs unquoted key)
    test_endpoint("GET", "/api/trade_signals/NSE_INDEX%7CNifty%2050")

    # POST backfill is destructive/slow, maybe skip or test with invalid symbol?
    # test_endpoint("POST", "/api/backfill/trendlyne", params={"symbol": "INVALID"})

if __name__ == "__main__":
    run_all_tests()
