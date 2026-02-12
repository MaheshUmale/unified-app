import urllib.request
import json

def test_oi_in_builder():
    url = "https://scanner.tradingview.com/options/scan2?label-product=options-builder"

    # Try common OI names in builder product
    variations = ["open_interest", "oi", "open-interest", "Total.Open.Interest"]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/json",
        "Referer": "https://www.tradingview.com/",
        "Origin": "https://www.tradingview.com"
    }

    payload = {
        "columns": ["name"] + variations,
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"}
        ],
        "ignore_unknown_fields": True,
        "index_filters": [
            {"name": "underlying_symbol", "values": ["NSE:NIFTY"]}
        ],
        "limit": 5
    }

    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method='POST')
    try:
        with urllib.request.urlopen(req) as f:
            if f.status == 200:
                res = json.loads(f.read().decode('utf-8'))
                print(f"Fields: {res['fields']}")
                if res['symbols']:
                    for s in res['symbols']:
                        print(f"Data: {s['f']}")
                return True
    except Exception as e:
        print(f"ERROR: {e}")
        if hasattr(e, 'read'):
            print(e.read().decode('utf-8'))
        return False

if __name__ == "__main__":
    test_oi_in_builder()
