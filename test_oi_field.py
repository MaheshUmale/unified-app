import requests

def test_field(field):
    url = "https://scanner.tradingview.com/options/scan2?label-product=symbols-options"
    payload = {
        "columns": [field],
        "filter": [
            {"left": "type", "operation": "equal", "right": "option"}
        ]
    }
    headers = {'Content-Type': 'application/json'}
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code == 200:
        print(f"Found valid OI field: {field}")
        return True
    return False

# Try many variants
variants = [
    "oi", "OI", "open_interest", "open_int", "Open.Interest",
    "total_oi", "Total.OI", "openinterest", "OpenInterest",
    "market_cap_basic", "volume", "average_volume_10d_calc",
    "change", "low", "high", "open", "close"
]
for v in variants:
    test_field(v)
