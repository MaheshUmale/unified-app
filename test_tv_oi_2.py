import requests

def test_oi(field):
    url = "https://scanner.tradingview.com/options/scan2?label-product=symbols-options"
    payload = {
        "columns": [field],
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"}
        ]
    }
    resp = requests.post(url, json=payload)
    if resp.status_code == 200:
        print(f"Valid: {field}")
    return resp.status_code == 200

# Try all common TV scanner suffixes/prefixes
common = ["open_interest", "oi", "open_int"]
suffixes = ["", "_calc", "_basic", "_today"]
for c in common:
    for s in suffixes:
        test_oi(c + s)
