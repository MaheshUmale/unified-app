import upstox_client
import os

token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2OTgwMWRjZDIyMWZlODM4NDM2MTE5M2MiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc3MDAwMzkxNywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzcwMDY5NjAwfQ.EZyJWF1ro2qklDmHizNNPPpNkj_s_da9_1hnqdEsQy4"
configuration = upstox_client.Configuration()
configuration.access_token = token
api_instance = upstox_client.HistoryV3Api(upstox_client.ApiClient(configuration))

try:
    # Testing with 1minute
    print("Testing with 1minute...")
    response = api_instance.get_intra_day_candle_data("NSE_INDEX|Nifty 50", "1minute")
    print("Success with 1minute")
except Exception as e:
    print(f"Failed with 1minute: {e}")

try:
    # Testing with minutes, 1
    print("\nTesting with minutes, 1...")
    response = api_instance.get_intra_day_candle_data("NSE_INDEX|Nifty 50", "minutes", 1)
    print("Success with minutes, 1")
except Exception as e:
    print(f"Failed with minutes, 1: {e}")
