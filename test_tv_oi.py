import requests

def test_oi(field):
    url = "https://scanner.tradingview.com/options/scan2?label-product=symbols-options"
    payload = {
        "columns": [field],
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"},
            {"left": "root", "operation": "equal", "right": "NIFTY"}
        ],
        "index_filters": [
            {"name": "underlying_symbol", "values": ["NSE:NIFTY"]}
        ]
    }
    resp = requests.post(url, json=payload)
    print(f"Field: {field} -> Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"Success! {field} is valid.")

fields = ["open_interest", "oi", "open_int", "Open.Interest", "volume"]
for f in fields:
    test_oi(f)
