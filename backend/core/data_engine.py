"""
ProTrade Data Engine
Manages real-time data ingestion and OHLC aggregation.
"""
import asyncio
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Union
from db.local_db import db, LocalDBJSONEncoder
from core.symbol_mapper import symbol_mapper

logger = logging.getLogger(__name__)

# Configuration
try:
    from config import INITIAL_INSTRUMENTS
except ImportError:
    INITIAL_INSTRUMENTS = ["NSE:NIFTY"]

socketio_instance = None
main_event_loop = None
subscribed_instruments = set()
replay_mode = False
sim_time = None

latest_prices = {}
latest_total_volumes = {}
instrument_metadata = {}

TICK_BATCH_SIZE = 100
tick_buffer = []
buffer_lock = threading.Lock()

def set_socketio(sio, loop=None):
    global socketio_instance, main_event_loop
    socketio_instance = sio
    main_event_loop = loop

def emit_event(event: str, data: Any, room: Optional[str] = None):
    global socketio_instance, main_event_loop
    if not socketio_instance: return
    if isinstance(data, (dict, list)):
        data = json.loads(json.dumps(data, cls=LocalDBJSONEncoder))
    try:
        if main_event_loop and main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(socketio_instance.emit(event, data, room=room), main_event_loop)
    except Exception as e:
        logger.error(f"Emit Error: {e}")

def flush_tick_buffer():
    global tick_buffer
    to_insert = []
    with buffer_lock:
        if tick_buffer:
            to_insert = tick_buffer
            tick_buffer = []
    if to_insert:
        try:
            db.insert_ticks(to_insert)
        except Exception as e:
            logger.error(f"DB Insert Error: {e}")

# Session State
active_bars = {}
last_emit_times = {}

def on_message(message: Union[Dict, str]):
    global active_bars, tick_buffer
    try:
        data = json.loads(message) if isinstance(message, str) else message
        feeds_map = data.get('feeds', {})
        if not feeds_map: return

        current_time = datetime.now()
        hrn_feeds = {}
        today_str = current_time.strftime("%Y-%m-%d")

        for inst_key, feed_datum in feeds_map.items():
            hrn = symbol_mapper.get_hrn(inst_key)
            feed_datum['instrumentKey'] = hrn
            feed_datum['date'] = today_str
            hrn_feeds[hrn] = feed_datum

            ff = feed_datum.get('fullFeed', {})
            mff = ff.get('marketFF', {})
            iff = ff.get('indexFF', {})
            ltpc = iff.get('ltpc') or mff.get('ltpc')

            if ltpc and ltpc.get('ltt'):
                ts_val = int(ltpc['ltt'])
                if 0 < ts_val < 10000000000: ts_val *= 1000
                feed_datum['ts_ms'] = ts_val

                if ltpc.get('ltp'):
                    price = float(ltpc['ltp'])
                    feed_datum['last_price'] = price
                    latest_prices[hrn] = price

                # Volume Logic
                delta_vol = 0
                if feed_datum.get('tv_volume') is not None:
                    curr_vol = float(feed_datum['tv_volume'])
                    if hrn in latest_total_volumes:
                        delta_vol = max(0, curr_vol - latest_total_volumes[hrn])
                    latest_total_volumes[hrn] = curr_vol
                feed_datum['ltq'] = int(delta_vol)
                if ltpc: ltpc['ltq'] = str(int(delta_vol))

            process_footprint_tick(hrn, feed_datum)

        # Throttled UI Emission
        now = time.time()
        if now - last_emit_times.get('GLOBAL_TICK', 0) > 0.1:
            emit_event('raw_tick', hrn_feeds)
            last_emit_times['GLOBAL_TICK'] = now

        with buffer_lock:
            tick_buffer.extend(list(hrn_feeds.values()))
            if len(tick_buffer) >= TICK_BATCH_SIZE:
                threading.Thread(target=flush_tick_buffer, daemon=True).start()
    except:
        pass

def process_footprint_tick(instrument_key: str, data_datum: Dict[str, Any]):
    global active_bars
    try:
        ff = data_datum.get('fullFeed', {})
        ltpc = (ff.get('marketFF') or ff.get('indexFF', {})).get('ltpc')
        if not ltpc or not ltpc.get('ltp'): return

        raw_ltt = int(ltpc['ltt'])
        if 0 < raw_ltt < 10000000000: raw_ltt *= 1000
        current_bar_ts = (raw_ltt // 60000) * 60000
        price = float(ltpc['ltp'])
        qty = int(ltpc.get('ltq', 0))

        if instrument_key not in active_bars: active_bars[instrument_key] = None
        bar = active_bars[instrument_key]

        if bar and current_bar_ts > bar['ts']:
            active_bars[instrument_key] = None
            bar = None

        if not bar:
            bar = {'ts': current_bar_ts, 'open': price, 'high': price, 'low': price, 'close': price, 'volume': 0}
            active_bars[instrument_key] = bar

        bar['high'] = max(bar['high'], price)
        bar['low'] = min(bar['low'], price)
        bar['close'] = price
        bar['volume'] += qty
    except:
        pass

def subscribe_instrument(instrument_key: str):
    from external.tv_live_wss import start_tv_wss
    wss = start_tv_wss(on_message)
    # Map common HRNs to WSS symbols
    mapping = {'NIFTY': 'NSE:NIFTY', 'BANKNIFTY': 'NSE:BANKNIFTY', 'FINNIFTY': 'NSE:CNXFINANCE'}
    wss.subscribe([mapping.get(instrument_key, instrument_key)])

def start_websocket_thread(token: str, keys: List[str]):
    from external.tv_feed import start_tv_feed
    from external.tv_live_wss import start_tv_wss
    start_tv_feed(on_message)
    start_tv_wss(on_message, ['NSE:NIFTY', 'NSE:BANKNIFTY', 'NSE:CNXFINANCE'])

def load_intraday_data(instrument_key, date_str=None, timeframe_min=1):
    import pytz
    ist = pytz.timezone('Asia/Kolkata')
    if not date_str: date_str = datetime.now(ist).strftime("%Y-%m-%d")
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    start_ms = int(ist.localize(dt.replace(hour=9, minute=15)).timestamp() * 1000)
    end_ms = int(ist.localize(dt.replace(hour=15, minute=30)).timestamp() * 1000)

    sql = f"SELECT full_feed FROM ticks WHERE instrumentKey = '{instrument_key}' AND ts_ms >= {start_ms} AND ts_ms <= {end_ms} ORDER BY ts_ms ASC"
    rows = db.query(sql)
    bars = []

    current_bar = None
    tf_ms = timeframe_min * 60000

    for r in rows:
        tick = json.loads(r['full_feed'])
        ltpc = (tick.get('fullFeed', {}).get('marketFF') or tick.get('fullFeed', {}).get('indexFF', {})).get('ltpc')
        if not ltpc: continue
        ts = int(ltpc['ltt'])
        if 0 < ts < 10000000000: ts *= 1000
        price = float(ltpc['ltp'])
        qty = int(ltpc.get('ltq', 0))

        bar_ts = (ts // tf_ms) * tf_ms
        if not current_bar or bar_ts > current_bar['ts']:
            if current_bar: bars.append(current_bar)
            current_bar = {'ts': bar_ts, 'open': price, 'high': price, 'low': price, 'close': price, 'volume': qty}
        else:
            current_bar['high'] = max(current_bar['high'], price)
            current_bar['low'] = min(current_bar['low'], price)
            current_bar['close'] = price
            current_bar['volume'] += qty

    if current_bar: bars.append(current_bar)
    return bars
