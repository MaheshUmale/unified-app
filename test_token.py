import upstox_client
from upstox_client.rest import ApiException
import os

def test_token():
    token = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2OTgwMWRjZDIyMWZlODM4NDM2MTE5M2MiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc3MDAwMzkxNywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzcwMDY5NjAwfQ.EZyJWF1ro2qklDmHizNNPPpNkj_s_da9_1hnqdEsQy4"
    configuration = upstox_client.Configuration()
    configuration.access_token = token
    api_instance = upstox_client.MarketQuoteV3Api(upstox_client.ApiClient(configuration))

    try:
        # Get LTP for Nifty 50
        api_response = api_instance.get_ltp(instrument_key="NSE_INDEX|Nifty 50")
        print("Token is VALID")
        print(api_response)
        return True
    except ApiException as e:
        print(f"Token TEST FAILED: {e}")
        return False

if __name__ == "__main__":
    test_token()
