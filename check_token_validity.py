import requests
import os

token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2OTgwMWRjZDIyMWZlODM4NDM2MTE5M2MiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc3MDAwMzkxNywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzcwMDY5NjAwfQ.EZyJWF1ro2qklDmHizNNPPpNkj_s_da9_1hnqdEsQy4"
url = "https://api.upstox.com/v2/market-quote/ltp?instrument_key=NSE_INDEX|Nifty 50"
headers = {
    'Accept': 'application/json',
    'Authorization': f'Bearer {token}'
}

response = requests.get(url, headers=headers)
print(f"Status Code: {response.status_code}")
print(f"Response: {response.json()}")
