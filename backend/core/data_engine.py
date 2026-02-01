"""
ProTrade Data Engine
Manages real-time data ingestion from Upstox, strategy dispatching, and real-time OHLC/Footprint aggregation.
"""
import asyncio
import json
from datetime import datetime, timedelta
from bson import ObjectId
import logging
import random
import ssl
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from datetime import datetime, timedelta

import MarketDataFeedV3_pb2 as pb
import pandas as pd
from google.protobuf.json_format import MessageToDict
from external import upstox_helper as ExtractInstrumentKeys
from external.upstox_feed import UpstoxFeed
from db.mongodb import (
    get_db,
    get_instruments_collection,
    get_oi_collection,
    get_raw_tick_data_collection,
    get_stocks_collection,
    get_tick_data_collection,
)
from typing import Dict, Any, List, Optional, Set, Union
from core.pcr_logic import calculate_total_pcr, analyze_oi_buildup

# Configuration from centralized config (planned migration)
try:
    from config import INITIAL_INSTRUMENTS
except ImportError:
    INITIAL_INSTRUMENTS = ["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]

socketio_instance = None
main_event_loop = None
stop_replay_flag = False
last_emit_times = {}  # Track last emit time per instrument for throttling
subscribed_instruments = set()

# Real-time Strategy & PCR tracking
replay_mode = False
sim_time = None # datetime representing simulated 'now'
sim_strike_data = {} # instrument_key -> list of docs (for replay)

def get_now():
    """Returns simulated time if in replay mode, else real time."""
    if replay_mode and sim_time:
        return sim_time
    return datetime.now()

latest_oi = {}  # instrument_key -> oi
latest_iv = {}  # instrument_key -> iv
latest_greeks = {} # instrument_key -> {delta, theta, gamma, vega}
latest_vix = {'value': 0}
latest_bid_ask = {} # instrument_key -> {'bid': p, 'ask': p}
latest_vtt = {} # instrument_key -> total_volume_today
latest_prices = {} # instrument_key -> price
instrument_metadata = {} # instrument_key -> {'symbol': str, 'type': 'CE'|'PE'|'FUT'|'INDEX', 'expiry': 'YYYY-MM-DD'}
pcr_running_totals = {} # symbol -> {'CE': total_oi, 'PE': total_oi, 'last_save': timestamp}
current_expiries = {} # symbol -> 'YYYY-MM-DD'

# Initialize Collections
tick_collection = get_tick_data_collection()
raw_tick_collection = get_raw_tick_data_collection()

# Batching for MongoDB
TICK_BATCH_SIZE = 50
tick_buffer = []
raw_tick_buffer = []
buffer_lock = threading.Lock()
raw_buffer_lock = threading.Lock()

# Worker Queue for non-blocking persistence
import queue
persistence_queue = queue.Queue()

def persistence_worker():
    """Background thread to handle throttled persistence tasks."""
    last_processed = {}
    while True:
        try:
            task = persistence_queue.get(timeout=5)
            func = task[0]
            args = task[1:]

            # Additional throttling check to be safe
            task_id = f"{func.__name__}_{args[0] if args else ''}"
            now = time.time()
            if now - last_processed.get(task_id, 0) < 0.5: # 500ms global safety throttle
                persistence_queue.task_done()
                continue

            func(*args)
            last_processed[task_id] = now
            persistence_queue.task_done()
        except queue.Empty:
            continue
        except Exception as e:
            logging.error(f"Persistence Worker Error: {e}")

threading.Thread(target=persistence_worker, daemon=True).start()

class MongoJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

def set_socketio(sio, loop=None):
    """
    Allows the main app to inject the SocketIO instance and the main event loop.

    Args:
        sio: The SocketIO instance (AsyncServer).
        loop: The main event loop for cross-thread async calls.
    """
    global socketio_instance, main_event_loop
    socketio_instance = sio
    main_event_loop = loop

def emit_event(event: str, data: Any, room: Optional[str] = None):
    """
    Helper to emit SocketIO events from background threads safely.
    Uses run_coroutine_threadsafe if an event loop is available.
    """
    global socketio_instance, main_event_loop
    if not socketio_instance:
        return

    # Ensure data is JSON serializable (handles datetimes/ObjectIds)
    if isinstance(data, (dict, list)):
        data = json.loads(json.dumps(data, cls=MongoJSONEncoder))

    try:
        if main_event_loop and main_event_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                socketio_instance.emit(event, data, room=room),
                main_event_loop
            )
        else:
            # Fallback if loop is not set/running - attempt direct emit (might block or fail if not in main thread)
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.run_coroutine_threadsafe(socketio_instance.emit(event, data, room=room), loop)
                else:
                    loop.run_until_complete(socketio_instance.emit(event, data, room=room))
            except RuntimeError:
                # No event loop in this thread
                pass
    except Exception as e:
        logging.error(f"Error emitting SocketIO event {event}: {e}")

def flush_tick_buffer():
    """Flushes the tick buffer to MongoDB."""
    global tick_buffer
    to_insert = []
    with buffer_lock:
        if tick_buffer:
            to_insert = tick_buffer
            tick_buffer = []

    if to_insert:
        try:
            tick_collection.insert_many(to_insert, ordered=False)
        except Exception as e:
            logging.error(f"MongoDB Batch Insert Error: {e}")

def flush_raw_tick_buffer():
    """Flushes the raw tick buffer to MongoDB."""
    global raw_tick_buffer
    to_insert = []
    with raw_buffer_lock:
        if raw_tick_buffer:
            to_insert = raw_tick_buffer
            raw_tick_buffer = []

    if to_insert:
        try:
            raw_tick_collection.insert_many(to_insert, ordered=False)
        except Exception as e:
            logging.error(f"MongoDB Raw Batch Insert Error: {e}")

# Session State (Per-Instrument)
active_bars = {}
session_stats = {}
active_strategies = {}

def register_strategy(instrument_key, strategy_instance):
    """
    Registers a strategy instance to receive ticks for an instrument.

    Args:
        instrument_key (str): The instrument key to subscribe to.
        strategy_instance: An instance of a strategy class with a process_tick method.
    """
    if instrument_key not in active_strategies:
        active_strategies[instrument_key] = []
    active_strategies[instrument_key].append(strategy_instance)

def decode_protobuf(buffer: bytes) -> pb.FeedResponse:
    """
    Decode the binary Protobuf message into a Python object.

    Args:
        buffer (bytes): The raw binary message from the WebSocket.

    Returns:
        pb.FeedResponse: The decoded Protobuf object.
    """
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response

def normalize_key(key: str) -> str:
    """Normalizes instrument keys to use pipe separator instead of colon."""
    if not key: return key
    return key.replace(':', '|')

def on_message(message: Union[Dict, bytes, str]):
    """
    Primary callback for incoming WebSocket messages from Upstox.
    Handles decoding (Protobuf/JSON), archiving to MongoDB, and dispatching to registered strategies and UI.

    Args:
        message: The raw message from the WebSocket feed.
    """
    global active_bars, session_stats, socketio_instance

    data = None
    if isinstance(message, dict):
        data = message
    elif isinstance(message, bytes):
        try:
            decoded_data = decode_protobuf(message)
            data = MessageToDict(decoded_data)
        except Exception as e:
            logging.error(f"Protobuf decode failed: {e}")
            return

    if data is None:
        try:
            data = json.loads(message)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return

    msg_type = data.get('type')
    if msg_type == 'initial_feed':
        logging.info("WSS: Market Data Snapshot Received.")
    elif msg_type == 'market_info':
        info = data.get('marketInfo', {})
        logging.info(f"WSS: Market Info Received. Status: {info.get('segmentStatus', 'Unknown')}")

    feeds_map = data.get('feeds', {})
    if feeds_map:
        # logging.info(f"WSS: Received ticks for {list(feeds_map.keys())}")
        pass

    # Batch raw tick persistence
    global raw_tick_buffer
    with raw_buffer_lock:
        raw_tick_buffer.append(data)
        if len(raw_tick_buffer) >= TICK_BATCH_SIZE:
            threading.Thread(target=flush_raw_tick_buffer, daemon=True).start()

    # Throttled SocketIO Emission (Global per feed message)
    try:
        if socketio_instance:
            now = time.time()
            # Only emit if 100ms has passed since last global 'raw_tick'
            if now - last_emit_times.get('GLOBAL_RAW_TICK', 0) > 0.1:
                jsonData = json.dumps(feeds_map)
                emit_event('raw_tick', jsonData)
                last_emit_times['GLOBAL_RAW_TICK'] = now
    except Exception as e:
        logging.error(f"SocketIO raw_tick Emit Error: {e}")

    if feeds_map:
        current_time = datetime.now()
        new_ticks = []

        # Normalize keys in feeds_map before processing and emitting
        normalized_feeds = {}
        for k, v in feeds_map.items():
            n_k = normalize_key(k)
            normalized_feeds[n_k] = v
            if k != n_k:
                logging.info(f"Normalized key: {k} -> {n_k}")
        feeds_map = normalized_feeds

        for inst_key, feed_datum in feeds_map.items():
            feed_datum['instrumentKey'] = inst_key
            feed_datum['_insertion_time'] = current_time

            # Extract common timestamp for easier replay/querying
            ff = feed_datum.get('fullFeed', {})

            # Real-time extraction (OI, IV, Greeks, VIX)
            market_ff = ff.get('marketFF', {})
            index_ff = ff.get('indexFF', {})

            if inst_key == "NSE_INDEX|India VIX":
                vix_ltpc = index_ff.get('ltpc', {})
                if vix_ltpc and vix_ltpc.get('ltp'):
                    latest_vix['value'] = float(vix_ltpc['ltp'])
                    # Offload to queue instead of starting a new thread
                    persistence_queue.put((save_vix_to_db, latest_vix['value']))

            if 'oi' in market_ff:
                new_oi = float(market_ff['oi'])
                latest_oi[inst_key] = new_oi
                update_pcr_for_instrument(inst_key)

            if 'iv' in market_ff:
                latest_iv[inst_key] = float(market_ff['iv'])

            if 'optionGreeks' in market_ff:
                g = market_ff['optionGreeks']
                latest_greeks[inst_key] = {
                    'delta': float(g.get('delta', 0)),
                    'theta': float(g.get('theta', 0)),
                    'gamma': float(g.get('gamma', 0)),
                    'vega': float(g.get('vega', 0))
                }

            if 'vtt' in market_ff:
                latest_vtt[inst_key] = float(market_ff['vtt'])

            market_levels = market_ff.get('marketLevel', {}).get('bidAskQuote', [])
            if market_levels:
                top = market_levels[0]
                latest_bid_ask[inst_key] = {
                    'bid': float(top.get('bidP', 0)),
                    'ask': float(top.get('askP', 0))
                }

            # Persist per-strike metrics for strategy analysis
            if inst_key in instrument_metadata:
                meta = instrument_metadata[inst_key]
                if meta['type'] in ['CE', 'PE', 'FUT']:
                    ltpc = market_ff.get('ltpc')
                    price = float(ltpc['ltp']) if ltpc and ltpc.get('ltp') else 0
                    oi = latest_oi.get(inst_key, 0)
                    iv = latest_iv.get(inst_key, 0)
                    greeks = latest_greeks.get(inst_key, {})

                    # Offload to queue instead of starting a new thread
                    persistence_queue.put((save_strike_metrics_to_db, inst_key, oi, price, iv, greeks))

            ltpc = market_ff.get('ltpc') or index_ff.get('ltpc')
            if ltpc and ltpc.get('ltt'):
                feed_datum['ts_ms'] = int(ltpc['ltt'])
                if ltpc.get('ltp'):
                    latest_prices[inst_key] = float(ltpc['ltp'])

            new_ticks.append(feed_datum)

            if inst_key in active_strategies:
                for strategy in active_strategies[inst_key]:
                    try:
                        strategy.process_tick(feed_datum)
                    except Exception as e:
                        logging.error(f"Error in strategy {strategy.__class__.__name__} for {inst_key}: {e}")

            process_footprint_tick(inst_key, feed_datum)

        # Batching logic
        global tick_buffer
        with buffer_lock:
            tick_buffer.extend(new_ticks)
            if len(tick_buffer) >= TICK_BATCH_SIZE:
                threading.Thread(target=flush_tick_buffer, daemon=True).start()

def process_footprint_tick(instrument_key: str, data_datum: Dict[str, Any]):
    """
    Processes a single tick for real-time footprint/OHLC aggregation.
    Maintains the 'active_bars' state and emits updates to the frontend.

    Args:
        instrument_key (str): The key of the instrument.
        data_datum (Dict[str, Any]): The tick data dictionary containing fullFeed details.
    """
    global active_bars, session_stats, socketio_instance

    try:
        full_feed = data_datum.get('fullFeed', {})
        ff = full_feed.get('marketFF') or full_feed.get('indexFF')
        if not ff:
            return

        ltpc = ff.get('ltpc')
        if not ltpc or not ltpc.get('ltp'):
            return

        raw_ltt = int(ltpc['ltt'])
        current_bar_ts = (raw_ltt // 60000) * 60000

        trade_price = float(ltpc['ltp'])
        trade_qty = int(ltpc.get('ltq', 0))

        if instrument_key not in active_bars:
            active_bars[instrument_key] = None
        if instrument_key not in session_stats:
            session_stats[instrument_key] = {'cvd': 0, 'total_vol': 0, 'trade_count': 0}

        aggregated_bar = active_bars[instrument_key]

        if aggregated_bar and current_bar_ts > aggregated_bar['ts']:
            if socketio_instance:
                emit_event('footprint_data', aggregated_bar, room=instrument_key)
            active_bars[instrument_key] = None
            aggregated_bar = None

        if not aggregated_bar:
            aggregated_bar = {
                'ts': current_bar_ts,
                'open': trade_price,
                'high': trade_price,
                'low': trade_price,
                'close': trade_price,
                'volume': 0,
                'buy_volume': 0,
                'sell_volume': 0,
                'oi': latest_oi.get(instrument_key, 0),
                'footprint': {},
                'instrument_token': instrument_key
            }
            active_bars[instrument_key] = aggregated_bar
            if socketio_instance:
                emit_event('footprint_update', aggregated_bar, room=instrument_key)

        if current_bar_ts < aggregated_bar['ts']:
            return

        aggregated_bar['high'] = max(aggregated_bar['high'], trade_price)
        aggregated_bar['low'] = min(aggregated_bar['low'], trade_price)
        aggregated_bar['close'] = trade_price
        aggregated_bar['volume'] += trade_qty
        aggregated_bar['oi'] = latest_oi.get(instrument_key, aggregated_bar.get('oi', 0))

        bid_ask_quotes = ff.get('marketLevel', {}).get('bidAskQuote', [])
        side = 'unknown'
        for quote in bid_ask_quotes:
            if trade_price == float(quote.get('askP', 0.0)):
                side = 'buy'
                break
        if side == 'unknown':
            for quote in bid_ask_quotes:
                if trade_price == float(quote.get('bidP', 0.0)):
                    side = 'sell'
                    break

        price_level = f"{trade_price:.2f}"
        if price_level not in aggregated_bar['footprint']:
            aggregated_bar['footprint'][price_level] = {'buy': 0, 'sell': 0}

        if side in ['buy', 'sell']:
            aggregated_bar['footprint'][price_level][side] += trade_qty

        stats = session_stats[instrument_key]
        if side == 'buy':
            stats['cvd'] += trade_qty
            aggregated_bar['buy_volume'] += trade_qty
        elif side == 'sell':
            stats['cvd'] -= trade_qty
            aggregated_bar['sell_volume'] += trade_qty

        stats['total_vol'] += trade_qty
        stats['trade_count'] += 1
        aggregated_bar['cvd'] = stats['cvd']
        aggregated_bar['avg_trade_sz'] = stats['total_vol'] / stats['trade_count']

        if socketio_instance:
            now = time.time()
            if now - last_emit_times.get(instrument_key, 0) > 0.5:
                emit_event('footprint_update', aggregated_bar, room=instrument_key)
                last_emit_times[instrument_key] = now

    except Exception as e:
        logging.error(f"Error processing footprint tick: {e}")

upstox_feed: Optional[UpstoxFeed] = None

def subscribe_instrument(instrument_key: str):
    """Dynamic subscription to an instrument."""
    if upstox_feed:
        upstox_feed.subscribe(instrument_key)

    # Try to resolve metadata if not present
    if instrument_key not in instrument_metadata:
        threading.Thread(target=resolve_metadata, args=(instrument_key,), daemon=True).start()

def resolve_metadata(instrument_key: str):
    """Resolves and caches instrument metadata (Symbol, Type, Strike, Expiry). Falls back to DB for historical."""
    try:
        # 1. Try Live Master
        df = ExtractInstrumentKeys.get_instrument_df()
        match = df[df['instrument_key'] == instrument_key]
        if not match.empty:
            row = match.iloc[0]
            expiry_date = ''
            if row.get('expiry'):
                dt = pd.to_datetime(row['expiry'])
                if not pd.isna(dt):
                    expiry_date = dt.strftime('%Y-%m-%d')

            instrument_metadata[instrument_key] = {
                'symbol': row['name'],
                'type': row['instrument_type'],
                'strike': float(row.get('strike_price', 0)),
                'expiry': expiry_date
            }

            # Cache in MongoDB for future replay discovery
            db = get_db()
            db['instruments'].update_one(
                {'instrument_key': instrument_key},
                {'$set': {
                    'name': row['name'],
                    'instrument_type': row['instrument_type'],
                    'strike_price': float(row.get('strike_price', 0)),
                    'expiry_date': expiry_date,
                    'trading_symbol': row.get('trading_symbol') or row.get('symbol'),
                    'updated_at': datetime.now()
                }},
                upsert=True
            )
        else:
            # 2. Try MongoDB (for expired/historical instruments)
            db = get_db()
            doc = db['instruments'].find_one({'instrument_key': instrument_key})
            if doc:
                instrument_metadata[instrument_key] = {
                    'symbol': doc.get('name') or doc.get('underlying_symbol') or 'UNKNOWN',
                    'type': doc.get('instrument_type') or 'UNKNOWN',
                    'strike': float(doc.get('strike_price', 0)),
                    'expiry': doc.get('expiry_date') or ''
                }

        # 3. Update current nearest expiry for the symbol (only future/today)
        if instrument_key in instrument_metadata:
            meta = instrument_metadata[instrument_key]
            symbol = meta['symbol']
            expiry_date = meta['expiry']
            today_str = datetime.now().strftime('%Y-%m-%d')
            if expiry_date and expiry_date >= today_str:
                if symbol not in current_expiries or expiry_date < current_expiries[symbol]:
                    current_expiries[symbol] = expiry_date
                    logging.info(f"Updated nearest expiry for {symbol}: {expiry_date}")
    except Exception as e:
        logging.error(f"Error resolving metadata for {instrument_key}: {e}")

def update_pcr_for_instrument(instrument_key: str):
    """Calculates and emits PCR if the instrument is part of a monitored index."""
    if instrument_key not in instrument_metadata:
        return

    meta = instrument_metadata[instrument_key]
    if meta['type'] not in ['CE', 'PE']:
        return

    raw_symbol = meta['symbol']
    # Normalize symbol for frontend consistency
    if 'NIFTY BANK' in raw_symbol.upper() or 'BANKNIFTY' in raw_symbol.upper():
        symbol = 'BANKNIFTY'
    elif 'NIFTY' in raw_symbol.upper():
        symbol = 'NIFTY'
    else:
        symbol = raw_symbol

    if symbol not in pcr_running_totals:
        pcr_running_totals[symbol] = {'CE': 0, 'PE': 0, 'last_save': 0, 'last_emit': 0}

    # Re-calculate totals for the symbol (only for the nearest expiry)
    total_ce_oi = 0
    total_pe_oi = 0

    target_expiry = current_expiries.get(meta['symbol'], '')

    for key, oi in latest_oi.items():
        m = instrument_metadata.get(key)
        if m and m['symbol'] == meta['symbol']:
            # Only include instruments for the nearest expiry
            if target_expiry and m.get('expiry') != target_expiry:
                continue

            if m['type'] == 'CE':
                total_ce_oi += oi
            elif m['type'] == 'PE':
                total_pe_oi += oi

    if total_ce_oi > 0:
        pcr = round(total_pe_oi / total_ce_oi, 2)

        now_time = time.time()

        # 1. Emit to UI (Throttled to 30 seconds)
        last_emit = pcr_running_totals[symbol].get('last_emit', 0)
        if now_time - last_emit > 30:
            emit_event('oi_update', {
                'symbol': symbol,
                'pcr': pcr,
                'timestamp': datetime.now().isoformat(),
                'put_oi': total_pe_oi,
                'call_oi': total_ce_oi,
                'source': 'live_tick'
            })
            pcr_running_totals[symbol]['last_emit'] = now_time
            # Also update the last pulse indicator
            emit_event('last_pulse', {'symbol': symbol, 'time': datetime.now().isoformat()})

        # 2. Save to MongoDB (Throttled to 1 minute)
        last_save = pcr_running_totals[symbol]['last_save']
        if now_time - last_save > 60:
            # Get latest index price for this symbol
            index_price = 0
            index_key = "NSE_INDEX|Nifty 50" if symbol == 'NIFTY' else "NSE_INDEX|Nifty Bank"
            index_price = latest_prices.get(index_key, 0)

            threading.Thread(target=save_oi_to_db, args=(symbol, total_ce_oi, total_pe_oi, index_price), daemon=True).start()
            pcr_running_totals[symbol]['last_save'] = now_time

def save_vix_to_db(vix_value):
    """Persists India VIX for strategy context. Gated by replay timestamps."""
    if replay_mode: return # Keep simulation in memory
    try:
        db = get_db()
        coll = db['vix_data']
        now = get_now()
        doc = {
            'value': vix_value,
            'date': now.strftime("%Y-%m-%d"),
            'timestamp': now.strftime("%H:%M:%S"),
            'updated_at': now
        }
        last_save = last_emit_times.get("SAVE_VIX", 0)
        if time.time() - last_save > 60:
            coll.insert_one(doc)
            last_emit_times["SAVE_VIX"] = time.time()
    except Exception as e:
        logging.error(f"Error saving VIX: {e}")

def save_strike_metrics_to_db(instrument_key, oi, price, iv=0, greeks=None):
    """Persists per-instrument metrics for buildup and strategy analysis. Gated by replay timestamps."""
    try:
        now = get_now()
        ba = latest_bid_ask.get(instrument_key, {})
        spread = abs(ba.get('ask', 0) - ba.get('bid', 0)) if ba else 0

        doc = {
            'instrument_key': instrument_key,
            'date': now.strftime("%Y-%m-%d"),
            'timestamp': now.strftime("%H:%M:%S"),
            'oi': oi,
            'price': price,
            'iv': iv,
            'gamma': greeks.get('gamma', 0) if greeks else 0,
            'theta': greeks.get('theta', 0) if greeks else 0,
            'delta': greeks.get('delta', 0) if greeks else 0,
            'spread': spread,
            'updated_at': now
        }

        if replay_mode:
            # Maintain in-memory history for strategy lookups during replay
            if instrument_key not in sim_strike_data:
                sim_strike_data[instrument_key] = []
            sim_strike_data[instrument_key].append(doc)
            # Limit history to 2 hours of 1-min data
            if len(sim_strike_data[instrument_key]) > 120:
                sim_strike_data[instrument_key].pop(0)
            return

        # Regular live persistence
        db = get_db()
        coll = db['strike_oi_data']
        # Only save every 1 minute to avoid bloat
        last_emit = last_emit_times.get(f"SAVE_STRIKE_{instrument_key}", 0)
        if time.time() - last_emit > 60: # Every 1 minute
            coll.insert_one(doc)
            last_emit_times[f"SAVE_STRIKE_{instrument_key}"] = time.time()
    except Exception as e:
        logging.error(f"Error saving strike metrics: {e}")

def save_oi_to_db(symbol, call_oi, put_oi, price=0):
    """Persists aggregated OI to MongoDB for historical analytics. Gated by replay timestamps."""
    if replay_mode: return # Skip for replay to avoid pollution
    try:
        oi_coll = get_oi_collection()
        now = get_now()
        doc = {
            'symbol': symbol,
            'date': now.strftime("%Y-%m-%d"),
            'timestamp': now.strftime("%H:%M"),
            'call_oi': call_oi,
            'put_oi': put_oi,
            'price': price,
            'source': 'live_engine',
            'updated_at': now
        }
        query = {'symbol': symbol, 'date': doc['date'], 'timestamp': doc['timestamp']}
        oi_coll.update_one(query, {'$set': doc}, upsert=True)
        logging.info(f"Saved real-time OI for {symbol}")
    except Exception as e:
        logging.error(f"Error saving real-time OI: {e}")

def start_pcr_calculation_thread():
    """Starts background threads for accurate PCR calculation and expiry tracking."""
    from external.upstox_api import UpstoxAPI
    from config import ACCESS_TOKEN

    def run_full_chain_pcr():
        from external import trendlyne_api
        api = UpstoxAPI(ACCESS_TOKEN)
        while True:
            if not is_market_hours():
                time.sleep(300)
                continue

            for symbol in ['NIFTY', 'BANKNIFTY']:
                try:
                    # 1. Get nearest expiry
                    # Ensure we have the latest expiry by resolving keys if needed
                    if symbol not in current_expiries:
                         from external import upstox_helper
                         current_spots = {
                            "NIFTY": latest_prices.get("NSE_INDEX|Nifty 50", 0),
                            "BANKNIFTY": latest_prices.get("NSE_INDEX|Nifty Bank", 0)
                         }
                         if current_spots[symbol] > 0:
                             upstox_helper.get_upstox_instruments([symbol], current_spots)

                    expiry_str = current_expiries.get(symbol)
                    if not expiry_str:
                        continue

                    # 2. Attempt to fetch Golden PCR from Trendlyne first
                    trendlyne_pcr = trendlyne_api.fetch_latest_pcr(symbol, expiry_str)
                    if trendlyne_pcr:
                        pcr = trendlyne_pcr.get('pcr')
                        total_ce = trendlyne_pcr.get('total_call_oi', 0)
                        total_pe = trendlyne_pcr.get('total_put_oi', 0)

                        logging.info(f"Golden PCR from Trendlyne for {symbol}: {pcr}")
                        emit_event('oi_update', {
                            'symbol': symbol,
                            'pcr': pcr,
                            'timestamp': datetime.now().isoformat(),
                            'put_oi': total_pe,
                            'call_oi': total_ce,
                            'source': 'trendlyne'
                        })
                        # Update the emit throttle for live ticks so we don't double emit immediately
                        if symbol in pcr_running_totals:
                            pcr_running_totals[symbol]['last_emit'] = time.time()
                        continue # Skip Upstox if Trendlyne succeeded

                    # 3. Fallback to Upstox full option chain
                    index_key = "NSE_INDEX|Nifty 50" if symbol == 'NIFTY' else "NSE_INDEX|Nifty Bank"
                    chain = api.get_option_chain(index_key, expiry_str)
                    if chain and chain.get('status') == 'success':
                        data = chain.get('data', [])

                        total_ce_oi = 0
                        total_pe_oi = 0
                        for item in data:
                            if item.get('call_options'):
                                total_ce_oi += item['call_options'].get('market_data', {}).get('oi', 0)
                            if item.get('put_options'):
                                total_pe_oi += item['put_options'].get('market_data', {}).get('oi', 0)

                        if total_ce_oi > 0:
                            pcr = round(total_pe_oi / total_ce_oi, 2)
                            logging.info(f"Fallback Full Chain PCR for {symbol}: {pcr}")

                            emit_event('oi_update', {
                                'symbol': symbol,
                                'pcr': pcr,
                                'timestamp': datetime.now().isoformat(),
                                'put_oi': total_pe_oi,
                                'call_oi': total_ce_oi,
                                'source': 'upstox_full'
                            })
                            # Update the emit throttle for live ticks
                            if symbol in pcr_running_totals:
                                pcr_running_totals[symbol]['last_emit'] = time.time()
                except Exception as e:
                    logging.error(f"Error in full chain PCR for {symbol}: {e}")

            time.sleep(60) # Every 1 minute

    threading.Thread(target=run_full_chain_pcr, daemon=True).start()

    def run_expiry_refresh():
        while True:
            try:
                # Periodically re-fetch instrument master to ensure we have latest expiries
                ExtractInstrumentKeys.get_instrument_df()
            except Exception as e:
                logging.error(f"Error refreshing instrument master: {e}")
            time.sleep(3600) # Every hour

    t = threading.Thread(target=run_expiry_refresh, daemon=True)
    t.start()

def is_market_hours() -> bool:
    """Checks if the current time is within Indian market hours (09:15 - 15:30 IST)."""
    import pytz
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)

    # Monday = 0, Sunday = 6
    if now.weekday() >= 5:
        return False

    start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    end_time = now.replace(hour=15, minute=30, second=0, microsecond=0)

    return start_time <= now <= end_time

def start_websocket_thread(access_token: str, instrument_keys: List[str]):
    """
    Starts the Upstox SDK MarketDataStreamerV3 via UpstoxFeed with market hour awareness.
    """
    global upstox_feed
    start_pcr_calculation_thread()

    def market_hour_monitor():
        global upstox_feed
        while True:
            try:
                market_active = is_market_hours()

                if market_active:
                    if upstox_feed is None:
                        logging.info("Market Hours: Initializing WebSocket Feed...")
                        upstox_feed = UpstoxFeed(access_token, on_message)
                        upstox_feed.connect(instrument_keys)
                    elif not upstox_feed.is_connected():
                        logging.info("Market Hours: Reconnecting WebSocket Feed...")
                        upstox_feed.connect(instrument_keys)
                else:
                    if upstox_feed and upstox_feed.is_connected():
                        logging.info("Outside Market Hours: Disconnecting WebSocket Feed...")
                        upstox_feed.disconnect()
            except Exception as e:
                logging.error(f"Market monitor loop error: {e}")

            time.sleep(60)

    def subscription_keep_alive():
        while True:
            time.sleep(120) # Throttled
            if not is_market_hours():
                continue

            try:
                new_keys = ExtractInstrumentKeys.getNiftyAndBNFnOKeys()
                if new_keys and upstox_feed and upstox_feed.is_connected():
                    for key in new_keys:
                        upstox_feed.subscribe(key)
            except Exception as e:
                logging.error(f"Keep-alive subscription failed: {e}")

    threading.Thread(target=market_hour_monitor, daemon=True).start()
    threading.Thread(target=subscription_keep_alive, daemon=True).start()

def load_intraday_data(instrument_key, date_str=None):
    """
    Fetches and aggregates data for a specific date (defaults to today) from 9:15 AM to 3:30 PM.

    Args:
        instrument_key (str): The instrument key.
        date_str (str): Optional date in YYYY-MM-DD format.

    Returns:
        list: A list of aggregated OHLC/Footprint bars.
    """
    import pytz
    ist = pytz.timezone('Asia/Kolkata')

    if not date_str:
        now = datetime.now(ist)
        date_str = now.strftime("%Y-%m-%d")

    start_time = ist.localize(datetime.strptime(f"{date_str} 09:15:00", "%Y-%m-%d %H:%M:%S"))
    end_time = ist.localize(datetime.strptime(f"{date_str} 15:30:00", "%Y-%m-%d %H:%M:%S"))

    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    # Query ticks within the date's market hours
    query = {
        'instrumentKey': instrument_key,
        '$or': [
            {'ts_ms': {'$gte': start_ms, '$lte': end_ms}},
            {'fullFeed.marketFF.ltpc.ltt': {'$gte': str(start_ms), '$lte': str(end_ms)}},
            {'fullFeed.indexFF.ltpc.ltt': {'$gte': str(start_ms), '$lte': str(end_ms)}},
            {'fullFeed.marketFF.ltpc.ltt': {'$gte': start_ms, '$lte': end_ms}},
            {'fullFeed.indexFF.ltpc.ltt': {'$gte': start_ms, '$lte': end_ms}}
        ]
    }

    cursor = tick_collection.find(query).sort('_id', 1)
    bars = []

    try:
        # Create a collector for replay data
        def collect_bar(event, data, room=None):
            if event == 'footprint_data':
                bars.append(data)

        replay = ReplayManager(emit_fn=collect_bar)
        replay.timeframe_sec = 60
        for doc in cursor:
            replay.process_replay_tick(doc)

        if replay.aggregated_bar:
            bars.append(replay.aggregated_bar)

        bars.sort(key=lambda x: x.get('ts', 0))
        return bars
    except Exception as e:
        logging.error(f"Error loading intraday data: {e}")
        return []

class ReplayManager:
    """Handles replaying historical tick data for simulation or backfilling UI."""
    def __init__(self, emit_fn=None):
        self.emit_fn = emit_fn or emit_event
        self.stop_flag = False
        self.aggregated_bar = None
        self.timeframe_sec = 60
        self.replay_cvd = 0
        self.replay_total_vol = 0
        self.replay_trade_count = 0

    def stop(self):
        self.stop_flag = True

    def start(self, instrument_key, speed=100, start_ts=None, timeframe=1):
        self.timeframe_sec = timeframe * 60
        self.stop_flag = False
        self.aggregated_bar = None

        query = {'instrumentKey': instrument_key}
        cursor = tick_collection.find(query).sort('_id', 1)

        count = 0
        for doc in cursor:
            if self.stop_flag:
                self.emit_fn('replay_finished', {'reason': 'stopped'})
                return

            try:
                ff = doc.get('fullFeed', {}).get('marketFF', {})
                tick_ts = int(ff.get('ltpc', {}).get('ltt', 0)) or \
                          (int(ff.get('marketOHLC', {}).get('ohlc', [{}])[0].get('ts', 0)))

                if not tick_ts: continue
                if start_ts and (tick_ts / 1000.0) < start_ts: continue

                self.process_replay_tick(doc)
                count += 1
                if count % 10 == 0:
                    if self.aggregated_bar:
                        self.emit_fn('footprint_update', self.aggregated_bar)
                    time.sleep(speed / 1000.0)
            except Exception as e:
                logging.error(f"Replay tick error: {e}")

        if self.aggregated_bar:
            self.emit_fn('footprint_data', self.aggregated_bar)
        self.emit_fn('replay_finished', {'reason': 'completed'})

    def process_replay_tick(self, data):
        full_feed = data.get('fullFeed', {})
        ff = full_feed.get('marketFF') or full_feed.get('indexFF')
        if not ff:
            return

        ltpc = ff.get('ltpc')
        if not ltpc or not ltpc.get('ltp'):
            return

        tick_ts_ms = int(ltpc.get('ltt', 0)) or \
                     int(ff.get('marketOHLC', {}).get('ohlc', [{}])[0].get('ts', 0))

        tick_ts_sec = tick_ts_ms // 1000
        bar_start_sec = tick_ts_sec - (tick_ts_sec % self.timeframe_sec)
        current_bar_ts = bar_start_sec * 1000

        trade_price = float(ltpc.get('ltp', 0))
        trade_qty = int(ltpc.get('ltq', 0))

        if self.aggregated_bar and current_bar_ts > self.aggregated_bar['ts']:
            self.emit_fn('footprint_data', self.aggregated_bar)
            self.aggregated_bar = None

        if not self.aggregated_bar:
            self.aggregated_bar = {
                'ts': current_bar_ts, 'open': trade_price, 'high': trade_price,
                'low': trade_price, 'close': trade_price, 'volume': 0,
                'buy_volume': 0, 'sell_volume': 0, 'big_buy_volume': 0,
                'big_sell_volume': 0, 'bubbles': [], 'oi': 0, 'footprint': {}
            }

        self.aggregated_bar['high'] = max(self.aggregated_bar['high'], trade_price)
        self.aggregated_bar['low'] = min(self.aggregated_bar['low'], trade_price)
        self.aggregated_bar['close'] = trade_price
        self.aggregated_bar['volume'] += trade_qty

        # Capture OI from tick if available
        if 'fullFeed' in data:
            ff_oi = data['fullFeed'].get('marketFF', {}).get('oi')
            if ff_oi is not None:
                self.aggregated_bar['oi'] = float(ff_oi)

        bid_ask_quotes = ff.get('marketLevel', {}).get('bidAskQuote', [])
        side = 'unknown'
        for quote in bid_ask_quotes:
            if trade_price >= float(quote.get('askP', 0.0)):
                side = 'buy'
                break
        if side == 'unknown':
            for quote in bid_ask_quotes:
                if trade_price <= float(quote.get('bidP', 0.0)):
                    side = 'sell'
                    break

        if side == 'buy':
            self.aggregated_bar['buy_volume'] += trade_qty
            self.replay_cvd += trade_qty
        elif side == 'sell':
            self.aggregated_bar['sell_volume'] += trade_qty
            self.replay_cvd -= trade_qty

        if trade_qty >= 50:
            self.aggregated_bar['bubbles'].append({
                'x': tick_ts_ms, 'y': trade_price, 'q': trade_qty, 'side': side
            })

        price_level = f"{trade_price:.2f}"
        if price_level not in self.aggregated_bar['footprint']:
            self.aggregated_bar['footprint'][price_level] = {'buy': 0, 'sell': 0}
        if side in ['buy', 'sell']:
            self.aggregated_bar['footprint'][price_level][side] += trade_qty

        self.replay_total_vol += trade_qty
        self.replay_trade_count += 1
        self.aggregated_bar['cvd'] = self.replay_cvd
        self.aggregated_bar['avg_trade_sz'] = self.replay_total_vol / self.replay_trade_count

        self.emit_fn('footprint_update', self.aggregated_bar)

replay_manager = None

def start_replay_thread(instrument_key, speed=100, start_ts=None, timeframe=1):
    """Starts a background thread for historical data replay."""
    global replay_manager
    if not replay_manager:
        replay_manager = ReplayManager(socketio_instance)
    t = threading.Thread(target=replay_manager.start, args=(instrument_key, speed, start_ts, timeframe))
    t.start()

def stop_active_replay():
    """Stops the currently active replay process."""
    if replay_manager:
        replay_manager.stop()
