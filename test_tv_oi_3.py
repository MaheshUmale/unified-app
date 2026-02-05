import requests

payload = {
    "columns": ["perf_open_interest"],
    "filter": [{"left": "type", "operation": "equal", "right": "option"}]
}
resp = requests.post("https://scanner.tradingview.com/options/scan2?label-product=symbols-options", json=payload)
print(f"perf_open_interest: {resp.status_code}")

payload["columns"] = ["oi_total"]
resp = requests.post("https://scanner.tradingview.com/options/scan2?label-product=symbols-options", json=payload)
print(f"oi_total: {resp.status_code}")
