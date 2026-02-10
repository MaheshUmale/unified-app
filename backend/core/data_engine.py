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
# Track subscribers per (instrumentKey, interval)
room_subscribers = {} # (instrumentKey, interval) -> set of sids

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
            asyncio.run_coroutine_threadsafe(socketio_instance.emit(event, data, to=room), main_event_loop)
            if room:
                logger.info(f"Emitted {event} to room {room}")
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
            instrument_key = data.get('instrumentKey')
            interval = data.get('interval')
            if instrument_key:
                payload = data['data']
                if isinstance(payload, dict):
                    payload['instrumentKey'] = instrument_key
                    payload['interval'] = interval
                # Use full technical symbol as room name
                emit_event('chart_update', payload, room=instrument_key.upper())
            return

        feeds_map = data.get('feeds', {})
        if not feeds_map: return

        current_time = datetime.now()
        sym_feeds = {}
        today_str = current_time.strftime("%Y-%m-%d")

        for inst_key, feed_datum in feeds_map.items():
            # Use technical symbol as is
            feed_datum.update({
                'instrumentKey': inst_key,
                'date': today_str,
                'last_price': float(feed_datum.get('last_price', 0)),
                'source': feed_datum.get('source', 'tv_wss')
            })

            ts_val = feed_datum.get('ts_ms', int(time.time() * 1000))
            if 0 < ts_val < 10000000000: ts_val *= 1000
            feed_datum['ts_ms'] = ts_val

            delta_vol = 0
            curr_vol = feed_datum.get('tv_volume')
            if curr_vol is not None:
                curr_vol = float(curr_vol)
                if inst_key in latest_total_volumes:
                    delta_vol = max(0, curr_vol - latest_total_volumes[inst_key])
                latest_total_volumes[inst_key] = curr_vol
            feed_datum['ltq'] = int(delta_vol)

            sym_feeds[inst_key] = feed_datum

        # Throttled UI Emission
        now = time.time()
        if now - last_emit_times.get('GLOBAL_TICK', 0) > 0.05:
            for inst_key, feed in sym_feeds.items():
                # Emit to specific technical symbol room
                emit_event('raw_tick', {inst_key: feed}, room=inst_key.upper())
            last_emit_times['GLOBAL_TICK'] = now

        with buffer_lock:
            tick_buffer.extend(list(sym_feeds.values()))
            if len(tick_buffer) >= TICK_BATCH_SIZE:
                threading.Thread(target=flush_tick_buffer, daemon=True).start()
    except Exception as e:
        logger.error(f"Error in data_engine on_message: {e}")

def subscribe_instrument(instrument_key: str, sid: str, interval: str = "1"):
    instrument_key = instrument_key.upper()
    key = (instrument_key, str(interval))
    if key not in room_subscribers:
        room_subscribers[key] = set()

    if sid not in room_subscribers[key]:
        room_subscribers[key].add(sid)
        logger.info(f"Room {instrument_key} ({interval}m) now has {len(room_subscribers[key])} subscribers")

    from external.tv_live_wss import start_tv_wss
    wss = start_tv_wss(on_message)
    wss.subscribe([instrument_key], interval=interval)

def is_sid_using_instrument(sid: str, instrument_key: str) -> bool:
    """Check if a specific client is still using this instrument in any interval."""
    instrument_key = instrument_key.upper()
    for (r_key, r_interval), sids in room_subscribers.items():
        if r_key == instrument_key and sid in sids:
            return True
    return False

def unsubscribe_instrument(instrument_key: str, sid: str, interval: str = "1"):
    instrument_key = instrument_key.upper()
    key = (instrument_key, str(interval))

    if key in room_subscribers and sid in room_subscribers[key]:
        room_subscribers[key].remove(sid)
        logger.info(f"Room {instrument_key} ({interval}m) now has {len(room_subscribers[key])} subscribers")

        if len(room_subscribers[key]) == 0:
            logger.info(f"Unsubscribing from {instrument_key} ({interval}m) as no more subscribers")
            from external.tv_live_wss import get_tv_wss
            wss = get_tv_wss()
            if wss:
                wss.unsubscribe(instrument_key, interval=interval)
            del room_subscribers[key]

def handle_disconnect(sid: str):
    """Cleanup all subscriptions for a disconnected client."""
    to_cleanup = []
    for (key, interval), sids in room_subscribers.items():
        if sid in sids:
            to_cleanup.append((key, interval))

    for key, interval in to_cleanup:
        unsubscribe_instrument(key, sid, interval)

def start_websocket_thread(token: str, keys: List[str]):
    from external.tv_live_wss import start_tv_wss
    start_tv_wss(on_message, INITIAL_INSTRUMENTS)
