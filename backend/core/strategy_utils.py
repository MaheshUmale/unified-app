
import pandas as pd
import logging
from datetime import datetime, timedelta
from db.mongodb import get_db, get_tick_data_collection
from core import data_engine

logger = logging.getLogger(__name__)

def get_5day_median_gamma(instrument_key):
    """Calculates the median gamma for an instrument over the last 5 trading days."""
    try:
        db = get_db()
        coll = db['strike_oi_data']
        now = data_engine.get_now()

        # Get data from last 7 days to be safe for weekends/holidays
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        cursor = coll.find({
            'instrument_key': instrument_key,
            'date': {'$gte': start_date},
            'gamma': {'$gt': 0}
        }).sort('date', -1)

        df = pd.DataFrame(list(cursor))
        if df.empty:
            return 0.0

        return float(df['gamma'].median())
    except Exception as e:
        print(f"Error calculating median gamma: {e}")
        return 0.0

def get_nifty_adv():
    """Calculates Average Daily Volume (ADV) for Nifty 50 ATM strikes."""
    from external import upstox_helper
    try:
        fut_key = upstox_helper.resolve_instrument_key("NIFTY", "FUT")
        if not fut_key:
            return 5000000
        adv = get_instrument_adv(fut_key)
        if adv <= 1000000: # If DB is sparse, try Upstox API
            adv = fetch_adv_from_upstox(fut_key)
        return adv or 5000000
    except Exception:
        return 5000000

def fetch_adv_from_upstox(instrument_key, days=5):
    """Fetches historical ADV from Upstox API as fallback."""
    from external.upstox_api import UpstoxAPI
    import config
    try:
        api = UpstoxAPI(config.ACCESS_TOKEN)
        # Fetch daily candles for the last few days
        to_date = data_engine.get_now().strftime("%Y-%m-%d")
        from_date = (data_engine.get_now() - timedelta(days=days+5)).strftime("%Y-%m-%d")

        data = api.get_historical_candles(instrument_key, "day", to_date, from_date)
        if data and data.get('status') == 'success':
            candles = data.get('data', {}).get('candles', [])
            if not candles: return None

            # Upstox returns [timestamp, open, high, low, close, volume, oi]
            vols = [c[5] for c in candles[:days]]
            return sum(vols) / len(vols)
    except Exception as e:
        logger.error(f"Error fetching ADV from Upstox: {e}")
    return None

def get_instrument_adv(instrument_key, days=20):
    """Calculates ADV for a specific instrument."""
    try:
        db = get_db()
        coll = get_tick_data_collection()
        now = data_engine.get_now()

        start_date = now - timedelta(days=days+10)

        # Aggregate daily max volume
        pipeline = [
            {'$match': {'instrumentKey': instrument_key, '_insertion_time': {'$gte': start_date}}},
            {'$project': {
                'date': {'$dateToString': {'format': '%Y-%m-%d', 'date': '$_insertion_time'}},
                'vol': {'$ifNull': ['$fullFeed.marketFF.vtt', 0]}
            }},
            {'$group': {'_id': '$date', 'daily_vol': {'$max': '$vol'}}},
            {'$match': {'daily_vol': {'$gt': 0}}},
            {'$sort': {'_id': -1}},
            {'$limit': days}
        ]

        results = list(coll.aggregate(pipeline))
        if not results:
            return 1000000 # Default fallback

        vols = [r['daily_vol'] for r in results]
        return sum(vols) / len(vols)
    except Exception:
        return 1000000
