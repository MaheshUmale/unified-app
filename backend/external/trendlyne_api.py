"""
Trendlyne SmartOptions Service
Provides functionality to interact with Trendlyne API for searching stocks, fetching expiry dates, and backfilling historical Open Interest (OI) data.
"""
import requests
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
from db.mongodb import get_oi_collection, get_stocks_collection, get_trendlyne_buildup_collection

logger = logging.getLogger(__name__)

# Cache for stock IDs to reduce redundant API calls
STOCK_ID_CACHE: Dict[str, int] = {}

class TrendlyneSession:
    _session: Optional[requests.Session] = None
    _csrf_token: Optional[str] = None
    _last_init: Optional[datetime] = None

    @classmethod
    def get_session(cls) -> requests.Session:
        if cls._session is None or (cls._last_init and datetime.now() - cls._last_init > timedelta(hours=1)):
            cls._session = requests.Session()
            cls._session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://smartoptions.trendlyne.com/'
            })
            try:
                # Initial request to get cookies/CSRF
                response = cls._session.get('https://smartoptions.trendlyne.com/', timeout=10)
                cls._csrf_token = cls._session.cookies.get('csrftoken')
                if cls._csrf_token:
                    cls._session.headers.update({'X-CSRFToken': cls._csrf_token})
                cls._last_init = datetime.now()
                logger.info("Trendlyne session initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Trendlyne session: {e}")
        return cls._session

def get_stock_id_for_symbol(symbol: str) -> Optional[int]:
    """
    Automatically lookup the Trendlyne stock ID for a given symbol.

    Args:
        symbol (str): The trading symbol (e.g., 'NIFTY').

    Returns:
        Optional[int]: The stock ID if found, otherwise None.
    """
    if symbol in STOCK_ID_CACHE:
        return STOCK_ID_CACHE[symbol]

    session = TrendlyneSession.get_session()
    search_url = "https://smartoptions.trendlyne.com/phoenix/api/search-contract-stock/"
    params = {'query': symbol.lower()}

    try:
        logger.info(f"Looking up Trendlyne stock ID for {symbol}...")
        response = session.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data and 'body' in data and 'data' in data['body'] and len(data['body']['data']) > 0:
            for item in data['body']['data']:
                item_symbol = item.get('stock_code') or item.get('symbol')
                if item_symbol and item_symbol.lower() == symbol.lower():
                    stock_id = item.get('stock_id') or item.get('stockId')
                    break
            else:
                stock_id = None
        else:
            stock_id = None

        if stock_id:
            STOCK_ID_CACHE[symbol] = stock_id
            logger.info(f"Found Trendlyne stock ID {stock_id} for {symbol}")
            return stock_id
        logger.warning(f"Could not find Trendlyne stock ID for {symbol}")
        return None

    except Exception as e:
        logger.error(f"Error looking up {symbol} on Trendlyne: {e}")
        return None

def fetch_and_save_oi_snapshot(symbol: str, stock_id: int, expiry_date_str: str, timestamp_snapshot: str) -> bool:
    """
    Fetches a snapshot of historical OI data from Trendlyne and persists it to MongoDB.

    Args:
        symbol (str): The trading symbol.
        stock_id (int): The Trendlyne stock ID.
        expiry_date_str (str): The expiry date in YYYY-MM-DD format.
        timestamp_snapshot (str): The time of the snapshot (HH:MM).

    Returns:
        bool: True if the operation was successful.
    """
    session = TrendlyneSession.get_session()
    url = "https://smartoptions.trendlyne.com/phoenix/api/live-oi-data/"
    params = {
        'stockId': stock_id,
        'expDateList': expiry_date_str,
        'minTime': "09:15",
        'maxTime': timestamp_snapshot
    }

    try:
        response = session.get(url, params=params, timeout=10)
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

def get_expiry_dates(stock_id: int, mtype: str = 'options'):
    """
    Fetches latest expiry dates for options or futures from Trendlyne.

    Args:
        stock_id (int): Trendlyne stock ID.
        mtype (str): 'options' or 'futures'.

    Returns:
        list: List of expiry date strings.
    """
    session = TrendlyneSession.get_session()
    url = f"https://smartoptions.trendlyne.com/phoenix/api/fno/get-expiry-dates/?mtype={mtype}&stock_id={stock_id}"
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        expiry_data = resp.json()
        if 'body' in expiry_data and 'expiryDates' in expiry_data['body']:
            return expiry_data['body']['expiryDates']
        return []
    except Exception as e:
        logger.error(f"Error fetching expiry dates for stock {stock_id}: {e}")
        return []

def fetch_futures_buildup(symbol: str, expiry: str) -> List[Dict[str, Any]]:
    """Fetches futures buildup data and caches it. Falls back to local data if needed."""
    session = TrendlyneSession.get_session()
    # Try multiple common URL formats as backup
    formats = [
        f"https://smartoptions.trendlyne.com/phoenix/api/fno/buildup-15/{expiry}/{symbol}/?fno_mtype=futures&format=json",
        f"https://smartoptions.trendlyne.com/phoenix/api/fno/buildup-15/{symbol}/{expiry}/?fno_mtype=futures&format=json"
    ]

    results = []
    for url in formats:
        try:
            resp = session.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get('results', [])
                if results: break
        except:
            continue

    # Cache in MongoDB if we got results
    if results:
        coll = get_trendlyne_buildup_collection()
        for item in results:
            item['symbol'] = symbol
            item['expiry'] = expiry
            item['mtype'] = 'futures'
            item['updated_at'] = datetime.now()
            query = {'symbol': symbol, 'expiry': expiry, 'timestamp': item.get('timestamp'), 'mtype': 'futures'}
            coll.update_one(query, {'$set': item}, upsert=True)
        return results

    # Fallback to local data if Trendlyne fails
    return get_local_buildup(symbol, mtype='futures')

def fetch_option_buildup(symbol: str, expiry: str, strike: int, option_type: str) -> List[Dict[str, Any]]:
    """Fetches option buildup data and caches it. Falls back to local data if needed."""
    session = TrendlyneSession.get_session()
    url = f"https://smartoptions.trendlyne.com/phoenix/api/fno/buildup-15/{expiry}/{symbol}/?fno_mtype=options&format=json&option_type={option_type}&strikePrice={strike}"

    results = []
    try:
        resp = session.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            results = data.get('results', [])
    except:
        pass

    # Cache in MongoDB
    if results:
        coll = get_trendlyne_buildup_collection()
        for item in results:
            item['symbol'] = symbol
            item['expiry'] = expiry
            item['strike'] = strike
            item['option_type'] = option_type
            item['mtype'] = 'options'
            item['updated_at'] = datetime.now()
            query = {
                'symbol': symbol,
                'expiry': expiry,
                'strike': strike,
                'option_type': option_type,
                'timestamp': item.get('timestamp'),
                'mtype': 'options'
            }
            coll.update_one(query, {'$set': item}, upsert=True)
        return results

    # Fallback to local data
    return get_local_buildup(symbol, mtype='options', strike=strike, option_type=option_type)

def get_local_buildup(symbol: str, mtype='futures', strike=None, option_type=None) -> List[Dict[str, Any]]:
    """Calculates buildup from local MongoDB strike_oi_data or intraday bars."""
    try:
        from db.mongodb import get_db
        from core.pcr_logic import analyze_oi_buildup
        from core import data_engine
        from external import upstox_helper

        db = get_db()

        # 1. Resolve Instrument Key
        if mtype == 'futures':
            instrument_key = upstox_helper.resolve_instrument_key(symbol, 'FUT')
        else:
            instrument_key = upstox_helper.resolve_instrument_key(symbol, option_type.upper(), strike=strike)

        if not instrument_key:
            return []

        # 2. Try fetching from strike_oi_data first
        coll = db['strike_oi_data']
        cursor = coll.find({'instrument_key': instrument_key}).sort([('date', -1), ('timestamp', -1)]).limit(40)
        docs = list(cursor)[::-1] # chronological

        # 3. If insufficient, use intraday aggregated bars
        if len(docs) < 2:
            bars = data_engine.load_intraday_data(instrument_key)
            docs = []
            for b in bars:
                docs.append({
                    'date': datetime.fromtimestamp(b['ts']/1000).strftime("%Y-%m-%d"),
                    'timestamp': datetime.fromtimestamp(b['ts']/1000).strftime("%H:%M:%S"),
                    'price': b['close'],
                    'oi': b.get('oi', 0)
                })

        if len(docs) < 2:
            return []

        results = []
        for i in range(1, len(docs)):
            curr = docs[i]
            prev = docs[i-1]

            price_change = curr['price'] - prev['price']
            oi_change = curr['oi'] - prev['oi']
            buildup = analyze_oi_buildup(curr['price'], prev['price'], curr['oi'], prev['oi'])

            results.append({
                'timestamp': f"{curr['date']}T{curr['timestamp']}",
                'price': curr['price'],
                'price_change': price_change,
                'oi': curr['oi'],
                'oi_change': oi_change,
                'buildup_type': buildup
            })

        # Ensure we don't have too many points and they are descending (newest first)
        return results[::-1][:20]
    except Exception as e:
        logger.error(f"Error in get_local_buildup: {e}")
        return []

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
        # Get Nearest Expiry using new function
        expiry_list = get_expiry_dates(stock_id, mtype='options')
        if expiry_list:
            default_expiry = expiry_list[0]
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
