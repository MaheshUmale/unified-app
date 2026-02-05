import requests

def test_label_field(label, field):
    url = f"https://scanner.tradingview.com/options/scan2?label-product={label}"
    payload = {
        "columns": [field],
        "filter": [{"left": "type", "operation": "equal", "right": "option"}]
    }
    resp = requests.post(url, json=payload)
    print(f"Label: {label}, Field: {field} -> Status: {resp.status_code}")

labels = ["symbols-options", "options", "india-options", "nse-options"]
for l in labels:
    test_label_field(l, "open_interest")
    test_label_field(l, "volume")
