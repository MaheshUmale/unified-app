from pymongo import MongoClient
import pandas as pd

# --- Configuration ---
MONGO_URI = "mongodb://localhost:27017/"
MONGO_DB_NAME = "upstox_strategy_db"
TICK_COLLECTION = "tick_data"
SIGNAL_COLLECTION = "trade_signals"

def connect_db():
    """Connects to MongoDB and returns the database object."""
    try:
        client = MongoClient(MONGO_URI)
        return client[MONGO_DB_NAME]
    except Exception as e:
        print(f"Error connecting to MongoDB: {e}")
        return None

def generate_plot_json(instrument_key):
    """
    Generates a Plotly JSON object for the given instrument.
    """
    db = connect_db()
    if not db:
        return {"error": "Could not connect to the database."}

    # Fetching ticks
    ticks_df = pd.DataFrame(list(db[TICK_COLLECTION].find({"instrumentKey": instrument_key})))
    if ticks_df.empty:
        return {"error": "No tick data found for the instrument."}

    ticks_df['time'] = pd.to_datetime(ticks_df['_insertion_time'])
    ticks_df = ticks_df.set_index('time')
    ohlc = ticks_df['fullFeed.marketFF.ltpc.ltp'].resample('1Min').ohlc()

    # Fetching signals
    signals_df = pd.DataFrame(list(db[SIGNAL_COLLECTION].find({"instrumentKey": instrument_key})))
    if not signals_df.empty:
        signals_df['time'] = pd.to_datetime(signals_df['timestamp'], unit='s')

    # Create figure
    fig = {
        "data": [{
            "x": ohlc.index.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            "open": ohlc['open'].tolist(),
            "high": ohlc['high'].tolist(),
            "low": ohlc['low'].tolist(),
            "close": ohlc['close'].tolist(),
            "type": "candlestick",
            "name": instrument_key
        }],
        "layout": {
            "title": f"1-Min OHLC Chart for {instrument_key}",
            "xaxis": {"title": "Time"},
            "yaxis": {"title": "Price"},
        }
    }

    if not signals_df.empty:
        buy_signals = signals_df[signals_df['signal'] == 'ENTRY']
        sell_signals = signals_df[signals_df['signal'] == 'SQUARE_OFF']

        fig['data'].append({
            "x": buy_signals['time'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            "y": buy_signals['ltp'].tolist(),
            "mode": "markers",
            "type": "scatter",
            "marker": {"color": "green", "symbol": "triangle-up", "size": 10},
            "name": "Buy Signal"
        })
        fig['data'].append({
            "x": sell_signals['time'].dt.strftime('%Y-%m-%d %H:%M:%S').tolist(),
            "y": sell_signals['exit_price'].tolist(),
            "mode": "markers",
            "type": "scatter",
            "marker": {"color": "red", "symbol": "triangle-down", "size": 10},
            "name": "Sell Signal"
        })

    return fig
