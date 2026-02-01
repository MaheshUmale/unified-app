
import requests
import json
import time

def check_live_status():
    try:
        # Check backend health
        res = requests.get("http://localhost:5051/health")
        print(f"Health: {res.json()}")

        # Check available instruments via API
        res = requests.get("http://localhost:5051/api/instruments")
        print(f"Instruments discovered: {len(res.json())}")

        # Check latest price for Nifty via live_pnl or similar if possible
        # Actually I'll just check if we can get strategy analysis which needs live data
        # We need atm_strike and expiry.
        # Let's try to find an expiry first
        res = requests.get("http://localhost:5051/api/trendlyne/expiry/NIFTY")
        expiries = res.json()
        print(f"Expiries found: {expiries}")

        if expiries:
            expiry = expiries[0]['date']
            atm = 25350
            index_key = "NSE_INDEX|Nifty 50"
            print(f"Requesting Strategy Analysis for {index_key}, ATM: {atm}, Expiry: {expiry}")
            res = requests.get(f"http://localhost:5051/api/strategy/atm-buying?index_key={index_key}&atm_strike={atm}&expiry={expiry}")
            print(f"Strategy Results: {json.dumps(res.json(), indent=2)}")

    except Exception as e:
        print(f"Error checking status: {e}")

if __name__ == "__main__":
    check_live_status()
