
import pandas as pd
from datetime import datetime, timedelta
from db.mongodb import get_db, get_tick_data_collection

def get_5day_median_gamma(instrument_key):
    """Calculates the median gamma for an instrument over the last 5 trading days."""
    try:
        db = get_db()
        coll = db['strike_oi_data']

        # Get data from last 7 days to be safe for weekends/holidays
        start_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

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
    # Since ATM strike changes, we should ideally average the volume of
    # whatever strike was ATM. For simplicity, we can use Nifty Futures ADV as a proxy
    # or just average the volume of the current ATM strike over the last 20 days.
    # The requirement says "0.2% of daily ADV" for ATM strikes.
    # I will use a reasonable default if history is sparse, or calculate from futures.
    fut_key = "NSE_FO|NIFTY24JANFUT" # This would need dynamic resolution
    return get_instrument_adv(fut_key) or 5000000

def get_instrument_adv(instrument_key, days=20):
    """Calculates ADV for a specific instrument."""
    try:
        db = get_db()
        # Using tick_data to find daily max(volume)
        coll = get_tick_data_collection()

        start_date = (datetime.now() - timedelta(days=days+10)).strftime("%Y-%m-%d")

        # Aggregate daily max volume
        pipeline = [
            {'$match': {'instrumentKey': instrument_key, '_insertion_time': {'$gte': datetime.now() - timedelta(days=days+10)}}},
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
