
import pandas as pd
import logging
from datetime import datetime, timedelta
from db.local_db import db
from core import data_engine

logger = logging.getLogger(__name__)

def get_5day_median_gamma(instrument_key):
    """Calculates the median gamma for an instrument over the last 5 trading days."""
    try:
        now = data_engine.get_now()
        start_date = (now - timedelta(days=7)).strftime("%Y-%m-%d")

        sql = """
            SELECT gamma FROM strike_oi_data
            WHERE instrument_key = ?
            AND date >= ?
            AND gamma > 0
            ORDER BY date DESC
        """
        rows = db.query(sql, (instrument_key, start_date))
        if not rows:
            return 0.0

        import numpy as np
        return float(np.median([r['gamma'] for r in rows]))
    except Exception as e:
        logger.error(f"Error calculating median gamma: {e}")
        return 0.0

def get_nifty_adv():
    """Calculates Average Daily Volume (ADV) for Nifty 50 ATM strikes."""
    try:
        # Try to find Nifty Future key
        rows = db.query("SELECT hrn FROM metadata WHERE hrn LIKE 'NIFTY % FUT' ORDER BY updated_at DESC LIMIT 1")
        if not rows:
            return 5000000

        fut_key = rows[0]['hrn']
        adv = get_instrument_adv(fut_key)
        return adv or 5000000
    except Exception:
        return 5000000

def get_instrument_adv(instrument_key, days=20):
    """Calculates ADV for a specific instrument."""
    try:
        sql = """
            SELECT date, MAX(qty) as daily_vol
            FROM ticks
            WHERE instrumentKey = ?
            GROUP BY date
            HAVING daily_vol > 0
            ORDER BY date DESC
            LIMIT ?
        """
        rows = db.query(sql, (instrument_key, days))
        if not rows:
            return 1000000 # Default fallback

        vols = [r['daily_vol'] for r in rows]
        return sum(vols) / len(vols)
    except Exception as e:
        logger.error(f"Error calculating ADV: {e}")
        return 1000000
