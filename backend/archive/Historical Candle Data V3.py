import upstox_client
from upstox_client.rest import ApiException

# Configure the API client with your access token
configuration = upstox_client.Configuration()
configuration.access_token = '{your_access_token}' # Replace with your actual access token

# Create an instance of the HistoryV3Api
api_instance = upstox_client.HistoryV3Api(upstox_client.ApiClient(configuration))

# Define the required parameters
instrument_key = 'NSE_EQ|INE848E01016' # Example instrument key (e.g., for Bajaj Auto)
unit = 'minutes'                       # Time unit: minutes, hours, days, weeks, or months
interval = '1'                         # Interval value (e.g., '1' minute, '3' hours)
to_date = '2025-01-02'                 # End date for the data (inclusive)
from_date = '2025-01-01'               # Start date for the data (inclusive)

try:
    # Call the get_historical_candle_data1 method
    api_response = api_instance.get_historical_candle_data1(instrument_key, unit, interval, to_date, from_date)
    print("API called successfully. Returned data:")
    print(api_response)
except ApiException as e:
    print("Exception when calling HistoryV3Api->get_historical_candle_data1: %s\n" % e)
