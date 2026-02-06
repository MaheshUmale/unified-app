"""
ProTrade Data Engine
Manages real-time data ingestion and OHLC aggregation.
"""
import asyncio
import json
import logging
import threading
import time
from datetime import datetime
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
latest_total_volumes = {}

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
            # Use 'to' for modern python-socketio compatibility
            asyncio.run_coroutine_threadsafe(socketio_instance.emit(event, data, to=room), main_event_loop)
            if room:
                logger.debug(f"Emitted {event} to room {room}")
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

last_emit_times = {}

def on_message(message: Union[Dict, str]):
    global tick_buffer
    try:
        data = json.loads(message) if isinstance(message, str) else message

        # Handle Chart/OHLCV Updates
        if data.get('type') == 'chart_update':
            hrn = data.get('instrumentKey')
            if hrn:
                emit_event('chart_update', data['data'], room=hrn)
            return

        feeds_map = data.get('feeds', {})
        if not feeds_map: return

        current_time = datetime.now()
        hrn_feeds = {}
        today_str = current_time.strftime("%Y-%m-%d")

        for inst_key, feed_datum in feeds_map.items():
            hrn = symbol_mapper.get_hrn(inst_key)
            feed_datum.update({
                'instrumentKey': hrn,
                'date': today_str,
                'last_price': float(feed_datum.get('last_price', 0)),
                'source': feed_datum.get('source', 'tv_wss')
            })

            # Standardize Timestamp (Ensure milliseconds)
            ts_val = feed_datum.get('ts_ms', int(time.time() * 1000))
            if 0 < ts_val < 10000000000: ts_val *= 1000
            feed_datum['ts_ms'] = ts_val

            # Volume Logic (Delta calculation from cumulative volume)
            delta_vol = 0
            curr_vol = feed_datum.get('tv_volume')
            if curr_vol is not None:
                curr_vol = float(curr_vol)
                if hrn in latest_total_volumes:
                    delta_vol = max(0, curr_vol - latest_total_volumes[hrn])
                latest_total_volumes[hrn] = curr_vol
            feed_datum['ltq'] = int(delta_vol)

            hrn_feeds[hrn] = feed_datum

        # Throttled UI Emission
        now = time.time()
        if now - last_emit_times.get('GLOBAL_TICK', 0) > 0.05: # Increased frequency to 20Hz
            for hrn, feed in hrn_feeds.items():
                emit_event('raw_tick', {hrn: feed}, room=hrn)
            last_emit_times['GLOBAL_TICK'] = now

        with buffer_lock:
            tick_buffer.extend(list(hrn_feeds.values()))
            if len(tick_buffer) >= TICK_BATCH_SIZE:
                threading.Thread(target=flush_tick_buffer, daemon=True).start()
    except Exception as e:
        logger.error(f"Error in data_engine on_message: {e}")

def subscribe_instrument(instrument_key: str):
    from external.tv_live_wss import start_tv_wss
    wss = start_tv_wss(on_message)
    # Map common HRNs to WSS symbols
    mapping = {'NIFTY': 'NSE:NIFTY', 'BANKNIFTY': 'NSE:BANKNIFTY', 'FINNIFTY': 'NSE:CNXFINANCE'}
    # Ensure uppercase for mapping lookup and WSS subscription
    key_upper = instrument_key.upper()
    target = mapping.get(key_upper, key_upper)
    wss.subscribe([target])

def start_websocket_thread(token: str, keys: List[str]):
    from external.tv_live_wss import start_tv_wss
    # Only start WSS, removed polling feed as per "live feed from Tradingview wss" requirement
    start_tv_wss(on_message, ['NSE:NIFTY', 'NSE:BANKNIFTY', 'NSE:CNXFINANCE'])
