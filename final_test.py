
import requests
import json

BASE_URL = "http://localhost:3000"

def test_endpoints():
    endpoints = [
        "/api/options/chain/NSE:NIFTY/with-greeks",
        "/api/options/oi-analysis/NSE:NIFTY",
        "/api/options/iv-analysis/NSE:NIFTY",
        "/api/options/pcr-trend/NSE:NIFTY",
        "/api/options/support-resistance/NSE:NIFTY",
        "/api/options/oi-buildup/NSE:NIFTY",
        "/api/alerts",
        "/api/db/tables",
        "/api/options/greeks/NSE:NIFTY?strike=21500&option_type=call",
        "/api/strategy/recommendations?market_view=bullish&iv_rank=50"
    ]

    for ep in endpoints:
        print(f"Testing {ep}...")
        try:
            resp = requests.get(f"{BASE_URL}{ep}")
            print(f"  Status: {resp.status_code}")
            if resp.status_code != 200:
                print(f"  Error: {resp.text}")
        except Exception as e:
            print(f"  Connection error: {e}")

if __name__ == "__main__":
    test_endpoints()
