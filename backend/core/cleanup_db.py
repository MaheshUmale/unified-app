import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from db.local_db import db
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def cleanup_oi_data(symbol=None, target_date=None):
    """
    Cleans up potentially incorrect PCR/OI data.
    Targets data for 'today' by default.
    """
    if target_date is None:
        target_date = datetime.now().strftime("%Y-%m-%d")

    sql = f"DELETE FROM oi_data WHERE date = '{target_date}'"
    if symbol:
        sql += f" AND symbol = '{symbol}'"

    # We specifically target data from 'live_engine' or points with anomalous PCR (> 3)
    sql += " AND (source = 'live_engine' OR (put_oi / NULLIF(call_oi, 0)) > 3.0)"

    logger.info(f"Cleaning up OI data for {target_date}...")
    try:
        db.conn.execute(sql)
        logger.info(f"Cleaned up OI data using SQL: {sql}")
    except Exception as e:
        logger.error(f"Failed to cleanup OI data: {e}")

if __name__ == "__main__":
    cleanup_oi_data()
