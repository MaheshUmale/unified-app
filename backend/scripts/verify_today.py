
import sys
import os
import asyncio
from datetime import datetime

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from db.local_db import db
import pandas as pd

def verify_today_charts():
    print(f"Verifying today's charts data ({datetime.now().strftime('%Y-%m-%d')})...")

    # 1. Check Ticks
    today_str = datetime.now().strftime('%Y-%m-%d')
    ticks = db.query("SELECT instrumentKey, count(*) as count FROM ticks WHERE date = ? GROUP BY instrumentKey", (today_str,))
    print(f"\nTicks collected today:")
    for t in ticks:
        print(f" - {t['instrumentKey']}: {t['count']} ticks")

    # 2. Check OI Data
    oi = db.query("SELECT symbol, count(*) as count FROM oi_data WHERE date = ? GROUP BY symbol", (today_str,))
    print(f"\nOI Data points collected today:")
    for o in oi:
        print(f" - {o['symbol']}: {o['count']} points")

    # 3. Test Indicators on NIFTY if data exists
    nifty_ticks = db.query("SELECT price FROM ticks WHERE instrumentKey = 'NIFTY' AND date = ? ORDER BY ts_ms ASC", (today_str,))
    if nifty_ticks:
        df = pd.DataFrame(nifty_ticks)
        sma = df['price'].rolling(window=20).mean()
        print(f"\nIndicator Test (NIFTY SMA 20):")
        print(f" - Latest Price: {df['price'].iloc[-1]}")
        print(f" - SMA Value: {sma.iloc[-1] if not pd.isna(sma.iloc[-1]) else 'N/A'}")
    else:
        print("\nNo NIFTY ticks found for today yet.")

if __name__ == "__main__":
    verify_today_charts()
