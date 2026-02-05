import requests

def test_columns(columns):
    url = "https://scanner.tradingview.com/options/scan2?label-product=symbols-options"
    payload = {
        "columns": columns,
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"},
            {"left": "root", "operation": "equal", "right": "NIFTY"}
        ],
        "index_filters": [
            {"name": "underlying_symbol", "values": ["NSE:NIFTY"]}
        ]
    }
    headers = {'Content-Type': 'application/json'}
    resp = requests.post(url, json=payload, headers=headers)
    print(f"Columns: {columns} -> Status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Response: {resp.text}")
    return resp.status_code == 200

all_cols = ["ask", "bid", "currency", "delta", "expiration", "gamma",
            "iv", "option-type", "pricescale", "rho", "root", "strike",
            "theoPrice", "theta", "vega", "bid_iv", "ask_iv", "close", "volume"]

# Test one by one to find the bad one
for col in all_cols + ["open_interest"]:
    test_columns([col])
