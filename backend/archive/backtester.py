import os
import pandas as pd
from pymongo import MongoClient
from datetime import datetime, timedelta
import sys
import time
from collections import deque

from streamlit import json


import upstox_client

configuration = upstox_client.Configuration()
ACCESS_TOKEN =  configuration.access_token
api_client = upstox_client.ApiClient(configuration)
history_api_instance = upstox_client.HistoryV3Api(api_client)

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


# Assuming ORDER_FLOW_s9 contains the necessary classes and functions
# We will need to refactor it to be importable
from CandleCrossStrategy import CandleCrossStrategy
from ORDER_FLOW_s9 import StrategyEngine, PaperTradeManager, DataPersistor
# --- Configuration ---
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "upstox_strategy_db"
TICK_COLLECTION = "tick_data"
BACKTEST_SIGNAL_COLLECTION = "backtest_signals"
client = MongoClient(MONGO_URI)
db = client[MONGO_DB_NAME]
tick_collection = db[TICK_COLLECTION]

def runNewTest():



        initial_instruments =["NSE_EQ|INE585B01010","NSE_EQ|INE139A01034","NSE_EQ|INE1NPP01017","NSE_EQ|INE917I01010","NSE_EQ|INE267A01025","NSE_EQ|INE466L01038","NSE_EQ|INE070A01015","NSE_EQ|INE749A01030","NSE_EQ|INE171Z01026","NSE_EQ|INE591G01025","NSE_EQ|INE160A01022","NSE_EQ|INE814H01029","NSE_EQ|INE102D01028","NSE_EQ|INE134E01011","NSE_EQ|INE009A01021","NSE_EQ|INE376G01013","NSE_EQ|INE619A01035","NSE_EQ|INE465A01025","NSE_EQ|INE540L01014","NSE_EQ|INE237A01028","NSE_EQ|INE361B01024","NSE_EQ|INE811K01011","NSE_EQ|INE01EA01019","NSE_EQ|INE030A01027","NSE_EQ|INE476A01022","NSE_EQ|INE721A01047","NSE_EQ|INE028A01039"]#,"NSE_EQ|INE670K01029","NSE_EQ|INE158A01026","NSE_EQ|INE123W01016","NSE_EQ|INE192A01025","NSE_EQ|INE118A01012","NSE_EQ|INE674K01013","NSE_EQ|INE094A01015","NSE_EQ|INE528G01035","NSE_EQ|INE093I01010","NSE_EQ|INE073K01018","NSE_EQ|INE006I01046","NSE_EQ|INE142M01025","NSE_EQ|INE169A01031","NSE_EQ|INE849A01020","NSE_EQ|INE669C01036","NSE_EQ|INE216A01030","NSE_EQ|INE111A01025","NSE_EQ|INE062A01020","NSE_EQ|INE081A01020","NSE_EQ|INE883A01011","NSE_EQ|INE075A01022","NSE_EQ|INE498L01015","NSE_EQ|INE377N01017","NSE_EQ|INE484J01027","NSE_EQ|INE205A01025","NSE_EQ|INE027H01010","NSE_EQ|INE121A01024","NSE_EQ|INE974X01010","NSE_EQ|INE854D01024","NSE_EQ|INE742F01042","NSE_EQ|INE226A01021","NSE_EQ|INE047A01021","NSE_EQ|INE326A01037","NSE_EQ|INE584A01023","NSE_EQ|INE414G01012","NSE_EQ|INE669E01016","NSE_EQ|INE211B01039","NSE_EQ|INE813H01021","NSE_EQ|INE213A01029","NSE_EQ|INE335Y01020","NSE_EQ|INE931S01010","NSE_EQ|INE704P01025","NSE_EQ|INE053F01010","NSE_EQ|INE127D01025","NSE_EQ|INE021A01026","NSE_EQ|INE356A01018","NSE_EQ|INE733E01010","NSE_EQ|INE115A01026","NSE_EQ|INE702C01027","NSE_EQ|INE388Y01029","NSE_EQ|INE117A01022","NSE_EQ|INE239A01024","NSE_EQ|INE437A01024","NSE_EQ|INE245A01021","NSE_EQ|INE053A01029","NSE_EQ|INE196A01026","NSE_EQ|INE121J01017","NSE_EQ|INE399L01023","NSE_EQ|INE121E01018","NSE_EQ|INE019A01038","NSE_EQ|INE151A01013","NSE_EQ|INE522F01014","NSE_EQ|INE296A01032","NSE_EQ|INE066F01020","NSE_EQ|INE002A01018","NSE_EQ|INE203G01027","NSE_EQ|INE467B01029","NSE_EQ|INE0ONG01011","NSE_EQ|INE079A01024","NSE_EQ|INE0J1Y01017","NSE_EQ|INE260B01028","NSE_EQ|INE040A01034"]

        # NiftyFO = ["NSE_FO|41910","NSE_FO|41913","NSE_FO|41914","NSE_FO|41915","NSE_FO|41916","NSE_FO|41917","NSE_FO|41918","NSE_FO|41921","NSE_FO|41922","NSE_FO|41923","NSE_FO|41924","NSE_FO|41925","NSE_FO|41926","NSE_FO|41927","NSE_FO|41928","NSE_FO|41935","NSE_FO|41936","NSE_FO|41939","NSE_FO|41940","NSE_FO|41943","NSE_FO|41944","NSE_FO|41945","NSE_FO|41946"]
        BN_FO =["NSE_FO|51414","NSE_FO|51415","NSE_FO|51416","NSE_FO|51417","NSE_FO|51420","NSE_FO|51421","NSE_FO|51439","NSE_FO|51440","NSE_FO|51460","NSE_FO|51461","NSE_FO|51475","NSE_FO|51476","NSE_FO|51493","NSE_FO|51498","NSE_FO|51499","NSE_FO|51500","NSE_FO|51501","NSE_FO|51502","NSE_FO|51507","NSE_FO|51510","NSE_FO|60166","NSE_FO|60167"]


        # # append all 3 arrays into one
        all_instruments =  initial_instruments
        # all_instruments =["NSE_EQ|INE585B01010"]
        if CandleCrossStrategy:
            # class DummyWriter:
            #     def write(self, s): pass

            # dummy_writer = DummyWriter()
            persistor_instance = DataPersistor() # Create a single persistor instance
            for key in all_instruments:
                print(f"Initializing CandleCrossStrategy Strategy for {key}...")
                # 2. Connect to the database
                # 3. Initialize the Strategy, passing the persistor
                strategy = CandleCrossStrategy(
                    instrument_key="" + key ,
                    csv_writer=None, # Mock CSV writer
                    persistor=persistor_instance, # <-- Inject the persistor
                    is_backtesting=True
                )
                strategy.backtest_mode = True
                #historical_candles: List[Dict[str, Any]]
                #[{'open': ..., 'high': ..., 'low': ..., 'close': ..., 'volume': ..., 'time': 'YYYY-MM-DD HH:MM:SS', 'ts_epoch': ...}, ...]
                #Convert the API response into a list of dictionaries that match the required format for the backtest_data_feed
                historical_candles_json = getIntradayCandleFromUpstox(key)
                strategy.backtest_data_feed( historical_candles= historical_candles_json )



def getIntradayCandleFromUpstox(instrument_key ):
    """
    Fetches historical candle data for a given instrument key from Upstox API.
    """
    # Placeholder function: Implement actual API call to Upstox to fetch candle data
    # Return format should be a list of dictionaries with keys: 'open', 'high', 'low', 'close', 'volume', 'time', 'ts_epoch'
    response = history_api_instance.get_intra_day_candle_data(instrument_key , "minutes", "1")

    # print(response)

    if not response.data or not response.data.candles:
        print(f"No candle data found for {instrument_key}.")
        print( response)
        return json.dumps([])

    ohlc_data = []
    for candle in response.data.candles:

        ohlc_data.append(candle )

    # The data is usually returned in reverse chronological order (newest first)
    # We must reverse it to be chronological (oldest first) for Lightweight Charts
    ohlc_data.reverse()

    if not ohlc_data:
        print(f"No OHLC data returned from Upstox API for {instrument_key}.")
        return json.dumps([])


    return ohlc_data

# def _convert_upstox_candle(self, upstox_candle: List[Any]) -> Dict[str, Any]:
#         """
#         Converts the Upstox API candle format (list) to the strategy's dictionary format.
#         Format: ['2025-12-10T09:24:00+05:30', Open, High, Low, Close, Volume, 0]
#         """
#         timestamp_str = upstox_candle[0]
#         dt_obj = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))

#         # Ensure we have a uniform time format (epoch in seconds)
#         ts_epoch = dt_obj.timestamp()

#         return {
#             'time_str': dt_obj.strftime('%Y-%m-%d %H:%M:%S'),
#             'ts_epoch': ts_epoch,
#             'open': upstox_candle[1],
#             'high': upstox_candle[2],
#             'low': upstox_candle[3],
#             'close': upstox_candle[4],
#             'volume': upstox_candle[5]
#         }



def run_backtest(start_time, end_time):
    """
    Runs a backtest of the trading strategy on historical tick data.
    """


    # Use a separate collection for backtest signals
    persistor = DataPersistor()
    persistor.db = db
    persistor.SIGNAL_COLLECTION = BACKTEST_SIGNAL_COLLECTION

    trade_manager = PaperTradeManager(persistor=persistor)
    strategy_engine = StrategyEngine(persistor=persistor, trade_manager=trade_manager)



    from pymongo import MongoClient

    # Requires the PyMongo package.
    # https://api.mongodb.com/python/current

    # client = MongoClient('mongodb://localhost:27017/')
    filter={}
    project={
        'instrumentKey': 1
    }

    sort=({
        'fullFeed.marketFF.ltpc.ltt': 1
    })

    result = tick_collection.find(
    filter=filter,
    # sort=sort,
    projection=project
    )

    for instrumentKey in result:
        instrument = instrumentKey.get("instrumentKey")
        print(" BACKTESTING FOR "+instrument)
        # print(instrumentKey.get("instrumentKey"))
        # Fetch historical data
        ticks = tick_collection.find({
            "_insertion_time": {
                "$gte": start_time,
                "$lte": end_time
            },
            "instrumentKey" : instrument,
        },
        sort=sort)#.sort("_insertion_time", 1)

        for tick in ticks:
            ltpc_data = tick.get('fullFeed', {}).get('marketFF', {}).get('ltpc', {})
            ltq = ltpc_data.get('ltq', 0)

            try:
                ltq = int(ltq)
            except (ValueError, TypeError):
                ltq = 0

            strategy_engine.process_tick(tick, ltq)

    print("Backtest complete.")
    # In a real scenario, you'd generate a more detailed report here
    generate_backtest_report(db, BACKTEST_SIGNAL_COLLECTION)

def generate_backtest_report(db, collection_name):
    """
    Generates a performance report from the backtest signals.
    """
    signals = pd.DataFrame(list(db[collection_name].find()))
    if signals.empty:
        print("No signals were generated during the backtest.")
        return

    # PnL Analysis
    pnl = signals[signals['signal'] == 'SQUARE_OFF']['pnl'].sum()
    print(f"Total PnL: {pnl}")

    # Further analysis can be added here (e.g., win/loss ratio, Sharpe ratio, etc.)

if __name__ == "__main__":
    # Example: Run backtest for the last day
    end_time = datetime.now()
    start_time = end_time - timedelta(days=1)

    print(f"Running backtest from {start_time} to {end_time}...")
    # run_backtest(start_time, end_time)
    runNewTest()
