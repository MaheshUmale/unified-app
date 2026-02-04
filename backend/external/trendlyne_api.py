"""
Trendlyne SmartOptions Service
Provides functionality to interact with Trendlyne API for searching stocks, fetching expiry dates, and backfilling historical Open Interest (OI) data.
"""
import requests
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, date
from db.local_db import db
from core.symbol_mapper import symbol_mapper

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

        # Normalize symbol to HRN (e.g., NIFTY 50 -> NIFTY)
        hrn = symbol_mapper.get_symbol(symbol)
        if hrn == "UNKNOWN": hrn = symbol.upper()

        db.insert_oi(hrn, current_date_str, timestamp_snapshot, total_call_oi, total_put_oi, 0, source='trendlyne_backfill')
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
    """Fetches futures buildup data. Falls back to local data if needed."""
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

    if results:
        return results

    # Fallback to local data if Trendlyne fails
    return get_local_buildup(symbol, mtype='futures', expiry=expiry)

def fetch_option_buildup(symbol: str, expiry: str, strike: int, option_type: str) -> List[Dict[str, Any]]:
    """Fetches option buildup data. Falls back to local data if needed."""
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

    if results:
        return results

    # Fallback to local data
    return get_local_buildup(symbol, mtype='options', strike=strike, option_type=option_type, expiry=expiry)

def get_local_buildup(symbol: str, mtype='futures', strike=None, option_type=None, expiry=None) -> List[Dict[str, Any]]:
    """Calculates buildup from local DuckDB strike_oi_data or intraday bars."""
    try:
        from core.pcr_logic import analyze_oi_buildup
        from core import data_engine

        # 1. Resolve HRN
        opt_type = 'CALL' if option_type and option_type.upper() in ['CALL', 'CE'] else 'PUT' if option_type and option_type.upper() in ['PUT', 'PE'] else None

        if mtype == 'futures':
            # This is a guess since we don't have upstox_helper anymore.
            # We'll try to find it in metadata.
            rows = db.query("SELECT hrn FROM metadata WHERE hrn LIKE ?", (f"{symbol}%FUT",))
            hrn = rows[0]['hrn'] if rows else f"{symbol} FUT"
        else:
            # Try to match metadata
            rows = db.query("SELECT hrn FROM metadata WHERE hrn LIKE ?", (f"{symbol}%{opt_type}%{strike}",))
            hrn = rows[0]['hrn'] if rows else f"{symbol} {opt_type} {strike}"

        logger.info(f"Buildup Fallback: Using hrn {hrn} for {symbol}")

        # 2. Try fetching from strike_oi_data first (cached ticks)
        sql = "SELECT date, timestamp, price, oi FROM strike_oi_data WHERE instrument_key = ? ORDER BY updated_at DESC LIMIT 60"
        docs = db.query(sql, (hrn,))
        docs = docs[::-1] # chronological
        source = "DB_STRIKE_OI"

        # 3. If insufficient, use intraday aggregated bars (from tick_data)
        if len(docs) < 2:
            bars = data_engine.load_intraday_data(hrn)
            if len(bars) >= 2:
                docs = []
                for b in bars:
                    docs.append({
                        'date': datetime.fromtimestamp(b['ts']/1000).strftime("%Y-%m-%d"),
                        'timestamp': datetime.fromtimestamp(b['ts']/1000).strftime("%H:%M:%S"),
                        'price': b['close'],
                        'oi': b.get('oi', 0)
                    })
                source = "DB_TICK_DATA"

        if len(docs) < 2:
            logger.warning(f"Buildup Fallback: Insufficient data points found for {hrn}")
            return []

        logger.info(f"Buildup Fallback: Calculated from {source} ({len(docs)} points)")

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

def generate_time_intervals(start_time="09:15", end_time="15:30", interval_minutes=5):
    """Generate time strings in HH:MM format"""
    start = datetime.strptime(start_time, "%H:%M")
    end = datetime.strptime(end_time, "%H:%M")
    current = start
    times = []
    while current <= end:
        times.append(current.strftime("%H:%M"))
        current += timedelta(minutes=interval_minutes)
    return times

def perform_backfill(symbol: str, interval_minutes=5):
    """Triggers a full backfill for the current day for a given symbol"""
    # 0. Cleanup potentially incorrect data for today first
    try:
        from core.cleanup_db import cleanup_oi_data
        cleanup_oi_data(symbol=symbol)
    except Exception as e:
        logger.error(f"Cleanup failed during backfill: {e}")

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

        time_slots = generate_time_intervals(end_time=end_time_str, interval_minutes=interval_minutes)
        logger.info(f"Backfilling {symbol} for {len(time_slots)} slots at {interval_minutes}min resolution...")

        success_count = 0
        # 1. First try fetching full history from the PCR history endpoint
        pcr_history = fetch_pcr_history(symbol, default_expiry)
        if pcr_history:
            logger.info(f"Backfill: Successfully fetched {len(pcr_history)} history points from PCR history API")
            success_count = len(pcr_history)

        # 2. Also fetch snapshots for strike-wise data (if needed by other components)
        # We do this for a few key points or if history was empty
        if not pcr_history or len(time_slots) > 0:
            for ts in time_slots:
                if fetch_and_save_oi_snapshot(symbol, stock_id, default_expiry, ts):
                    success_count += 1
                time.sleep(0.05) # Brief pause to be nice to API

        return {
            "status": "success",
            "symbol": symbol,
            "slots_processed": success_count,
            "total_slots": len(time_slots)
        }
    except Exception as e:
        logger.error(f"Backfill failed for {symbol}: {e}")
        return {"status": "error", "message": str(e)}

def fetch_pcr_history(symbol: str, expiry: str) -> List[Dict[str, Any]]:
    """
    Simulates PCR history by fetching snapshots for the current day.
    Matches logic from backfill_trendlyne.py.
    """
    stock_id = get_stock_id_for_symbol(symbol)
    if not stock_id:
        return []

    now = datetime.now()
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    end_time_str = "15:30" if now > market_close else now.strftime("%H:%M")
    time_slots = generate_time_intervals(end_time=end_time_str)

    results = []
    logger.info(f"Re-fetching PCR history via snapshots for {symbol}...")
    for ts in time_slots:
        # We don't want to spam the API too much in a single request
        # but for a daily view it's necessary if no bulk API exists.
        try:
            success = fetch_and_save_oi_snapshot(symbol, stock_id, expiry, ts)
            if success:
                results.append({"timestamp": ts})
        except:
            continue

    return results

def fetch_latest_pcr(symbol: str, expiry: str) -> Optional[Dict[str, Any]]:
    """Fetches the latest available PCR data point from Trendlyne snapshot."""
    stock_id = get_stock_id_for_symbol(symbol)
    if not stock_id:
        return None

    now = datetime.now()
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    if now < market_open:
        return None

    current_ts = now.strftime("%H:%M")

    # Try multiple intervals to find the latest
    session = TrendlyneSession.get_session()
    url = "https://smartoptions.trendlyne.com/phoenix/api/live-oi-data/"
    params = {
        'stockId': stock_id,
        'expDateList': expiry,
        'minTime': "09:15",
        'maxTime': current_ts
    }

    try:
        response = session.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data['head']['status'] == '0':
                body = data['body']
                oi_data = body.get('oiData', {})

                total_call_oi = 0
                total_put_oi = 0
                for strike_data in oi_data.values():
                    total_call_oi += int(strike_data.get('callOi', 0))
                    total_put_oi += int(strike_data.get('putOi', 0))

                if total_call_oi > 0:
                    return {
                        'pcr': round(total_put_oi / total_call_oi, 2),
                        'total_call_oi': total_call_oi,
                        'total_put_oi': total_put_oi,
                        'timestamp': current_ts
                    }
    except Exception as e:
        logger.error(f"Error fetching latest PCR for {symbol}: {e}")

    return None
