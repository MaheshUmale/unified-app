import upstox_client
from upstox_client.rest import ApiException

# Configure the API client (assuming configuration.access_token is already set)
# configuration = upstox_client.Configuration()
# configuration.access_token = '{your_access_token}'
# api_instance = upstox_client.HistoryV3Api(upstox_client.ApiClient(configuration))

# Use the same instance as above or create a new one
api_instance = upstox_client.HistoryV3Api()

# Define parameters for intraday data
instrument_key = 'NSE_EQ|INE848E01016'
unit = 'minutes'
interval = '1'

try:
    # Call the get_intra_day_candle_data method
    api_response = api_instance.get_intra_day_candle_data(instrument_key, unit, interval)
    print("API called successfully. Returned data:")
    print(api_response)
except ApiException as e:
    print("Exception when calling HistoryV3Api->get_intra_day_candle_data: %s\n" % e)
