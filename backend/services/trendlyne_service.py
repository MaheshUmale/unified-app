"""
Service for interacting with Trendlyne SmartOptions API to fetch historical OI data.
"""
import requests
import time
import logging
from datetime import datetime, timedelta, date
from database import get_oi_collection, get_stocks_collection

logger = logging.getLogger(__name__)

# Cache for stock IDs
STOCK_ID_CACHE = {}

def get_stock_id_for_symbol(symbol: str):
    """Automatically lookup Trendlyne stock ID for a given symbol"""
    if symbol in STOCK_ID_CACHE:
        return STOCK_ID_CACHE[symbol]

    search_url = "https://smartoptions.trendlyne.com/phoenix/api/search-contract-stock/"
    params = {'query': symbol.lower()}

    try:
        logger.info(f"Looking up Trendlyne stock ID for {symbol}...")
        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and 'body' in data and 'data' in data['body'] and len(data['body']['data']) > 0:
            stock_id = data['body']['data'][0]['stock_id']
            if stock_id:
                STOCK_ID_CACHE[symbol] = stock_id
                logger.info(f"Found Trendlyne stock ID {stock_id} for {symbol}")
                return stock_id

        logger.warning(f"Could not find Trendlyne stock ID for {symbol}")
        return None

    except Exception as e:
        logger.error(f"Error looking up {symbol} on Trendlyne: {e}")
        return None

def fetch_and_save_oi_snapshot(symbol: str, stock_id: int, expiry_date_str: str, timestamp_snapshot: str):
    """Fetch and save historical OI data snapshot from Trendlyne"""
    url = "https://smartoptions.trendlyne.com/phoenix/api/live-oi-data/"
    params = {
        'stockId': stock_id,
        'expDateList': expiry_date_str,
        'minTime': "09:15",
        'maxTime': timestamp_snapshot
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data['head']['status'] != '0':
            logger.error(f"Trendlyne API error: {data['head'].get('statusDescription', 'Unknown error')}")
            return False

        body = data['body']
        oi_data = body.get('oiData', {})
        input_data = body.get('inputData', {})

        oi_collection = get_oi_collection()
        stocks_collection = get_stocks_collection()

        # Ensure stock exists in MongoDB
        stock = stocks_collection.find_one({'symbol': symbol})
        if not stock:
            start_stock = {'symbol': symbol, 'trendlyne_stock_id': stock_id}
            stocks_collection.insert_one(start_stock)
            stock_db_id = start_stock['_id']
        else:
             stock_db_id = stock['_id']

        current_date_str = input_data.get('tradingDate', date.today().strftime("%Y-%m-%d"))
        expiry_str = input_data.get('expDateList', [expiry_date_str])[0]

        total_call_oi = 0
        total_put_oi = 0
        total_call_change = 0
        total_put_change = 0

        for strike_data in oi_data.values():
            total_call_oi += int(strike_data.get('callOi', 0))
            total_put_oi += int(strike_data.get('putOi', 0))
            total_call_change += int(strike_data.get('callOiChange', 0))
            total_put_change += int(strike_data.get('putOiChange', 0))

        doc = {
            'stock_id': stock_db_id,
            'symbol': symbol,
            'date': current_date_str,
            'timestamp': timestamp_snapshot,
            'expiry_date': expiry_str,
            'call_oi': total_call_oi,
            'put_oi': total_put_oi,
            'change_in_call_oi': total_call_change,
            'change_in_put_oi': total_put_change,
            'source': 'trendlyne_backfill',
            'updated_at': datetime.now()
        }

        query = {'symbol': symbol, 'date': current_date_str, 'timestamp': timestamp_snapshot}
        oi_collection.update_one(query, {'$set': doc}, upsert=True)
        return True

    except Exception as e:
        logger.error(f"Error fetching Trendlyne snapshot for {symbol} at {timestamp_snapshot}: {e}")
        return False

def generate_time_intervals(start_time="09:15", end_time="15:30", interval_minutes=15):
    """Generate time strings in HH:MM format"""
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")
    current = start
    times = []
    while current <= end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=interval_minutes)
    return times

def perform_backfill(symbol: str):
    """Triggers a full backfill for the current day for a given symbol"""
    stock_id = get_stock_id_for_symbol(symbol)
    if not stock_id:
        return {"status": "error", "message": f"Stock ID not found for {symbol}"}

    try:
        # Get Nearest Expiry
        expiry_url = f"https://smartoptions.trendlyne.com/phoenix/api/fno/get-expiry-dates/?mtype=options&stock_id={stock_id}"
        resp = requests.get(expiry_url, timeout=10)
        expiry_data = resp.json()
        if 'body' in expiry_data and 'expiryDates' in expiry_data['body']:
            default_expiry = expiry_data['body']['expiryDates'][0]
        else:
            return {"status": "error", "message": f"Could not get expiry for {symbol}"}

        # Generate time slots
        now = datetime.now()
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        end_time_str = "15:30" if now > market_close else now.strftime("%H:%M")

        time_slots = generate_time_intervals(end_time=end_time_str)
        logger.info(f"Backfilling {symbol} for {len(time_slots)} slots...")

        success_count = 0
        for ts in time_slots:
            if fetch_and_save_oi_snapshot(symbol, stock_id, default_expiry, ts):
                success_count += 1
            time.sleep(0.1) # Brief pause to be nice to API

        return {
            "status": "success",
            "symbol": symbol,
            "slots_processed": success_count,
            "total_slots": len(time_slots)
        }
    except Exception as e:
        logger.error(f"Backfill failed for {symbol}: {e}")
        return {"status": "error", "message": str(e)}
