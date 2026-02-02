import upstox_client
import os

token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2OTgwMWRjZDIyMWZlODM4NDM2MTE5M2MiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc3MDAwMzkxNywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzcwMDY5NjAwfQ.EZyJWF1ro2qklDmHizNNPPpNkj_s_da9_1hnqdEsQy4"
configuration = upstox_client.Configuration()
configuration.access_token = token
api_instance = upstox_client.HistoryV3Api(upstox_client.ApiClient(configuration))

response = api_instance.get_intra_day_candle_data("NSE_INDEX|Nifty 50", "minutes", 1)
print(f"Type of response.data: {type(response.data)}")
print(f"Attributes of response.data: {dir(response.data)}")
if hasattr(response.data, 'candles'):
    print(f"First candle: {response.data.candles[0]}")
