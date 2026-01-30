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

# Real-time PCR tracking
latest_oi = {}  # instrument_key -> oi
latest_prices = {} # instrument_key -> price
instrument_metadata = {} # instrument_key -> {'symbol': str, 'type': 'CE'|'PE'|'FUT'|'INDEX'}
pcr_running_totals = {} # symbol -> {'CE': total_oi, 'PE': total_oi, 'last_save': timestamp}

# Initialize Collections
tick_collection = get_tick_data_collection()
raw_tick_collection = get_raw_tick_data_collection()

# Batching for MongoDB
TICK_BATCH_SIZE = 50
tick_buffer = []
buffer_lock = threading.Lock()

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
    try:
        raw_tick_collection.insert_one(data)
    except Exception as e:
        logging.error(f"MongoDB Raw Insert Error: {e}")

    try:
        if socketio_instance:
            jsonData = json.dumps(feeds_map)
            emit_event('raw_tick', jsonData)
    except Exception as e:
        logging.error(f"SocketIO raw_tick Emit Error: {e}")

    if feeds_map:
        current_time = datetime.now()
        new_ticks = []
        for inst_key, feed_datum in feeds_map.items():
            feed_datum['instrumentKey'] = inst_key
            feed_datum['_insertion_time'] = current_time

            # Extract common timestamp for easier replay/querying
            ff = feed_datum.get('fullFeed', {})

            # Real-time OI extraction
            market_ff = ff.get('marketFF', {})
            if 'oi' in market_ff:
                new_oi = float(market_ff['oi'])
                latest_oi[inst_key] = new_oi
                update_pcr_for_instrument(inst_key)

                # Also save per-strike OI for Flow tab fallback
                if inst_key in instrument_metadata:
                    meta = instrument_metadata[inst_key]
                    if meta['type'] in ['CE', 'PE', 'FUT']:
                        ltpc = market_ff.get('ltpc')
                        price = float(ltpc['ltp']) if ltpc and ltpc.get('ltp') else 0
                        threading.Thread(target=save_strike_oi_to_db, args=(inst_key, new_oi, price), daemon=True).start()

            ltpc = market_ff.get('ltpc') or ff.get('indexFF', {}).get('ltpc')
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
        if 'fullFeed' not in data_datum or 'marketFF' not in data_datum['fullFeed']:
            return

        ff = data_datum['fullFeed']['marketFF']
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
    """Resolves and caches instrument metadata (Symbol, Type, Strike)."""
    try:
        df = ExtractInstrumentKeys.get_instrument_df()
        match = df[df['instrument_key'] == instrument_key]
        if not match.empty:
            row = match.iloc[0]
            instrument_metadata[instrument_key] = {
                'symbol': row['name'],
                'type': row['instrument_type'],
                'strike': float(row.get('strike_price', 0))
            }
    except Exception as e:
        logging.error(f"Error resolving metadata for {instrument_key}: {e}")

def update_pcr_for_instrument(instrument_key: str):
    """Calculates and emits PCR if the instrument is part of a monitored index."""
    if instrument_key not in instrument_metadata:
        return

    meta = instrument_metadata[instrument_key]
    if meta['type'] not in ['CE', 'PE']:
        return

    symbol = meta['symbol']
    if symbol not in pcr_running_totals:
        pcr_running_totals[symbol] = {'CE': 0, 'PE': 0, 'last_save': 0}

    # Re-calculate totals for the symbol (could be optimized further by tracking diffs)
    total_ce_oi = 0
    total_pe_oi = 0

    for key, oi in latest_oi.items():
        m = instrument_metadata.get(key)
        if m and m['symbol'] == symbol:
            if m['type'] == 'CE':
                total_ce_oi += oi
            elif m['type'] == 'PE':
                total_pe_oi += oi

    if total_ce_oi > 0:
        pcr = round(total_pe_oi / total_ce_oi, 2)

        now_time = time.time()
        # 1. Emit live update (Throttled to 5s)
        last_pcr_emit = last_emit_times.get(f"PCR_{symbol}", 0)
        if now_time - last_pcr_emit > 5:
            emit_event('oi_update', {
                'symbol': symbol,
                'pcr': pcr,
                'timestamp': datetime.now().isoformat(),
                'put_oi': total_pe_oi,
                'call_oi': total_ce_oi
            })
            last_emit_times[f"PCR_{symbol}"] = now_time

        # 2. Save to MongoDB (Throttled to 1 minute)
        last_save = pcr_running_totals[symbol]['last_save']
        if now_time - last_save > 60:
            # Get latest index price for this symbol
            index_price = 0
            index_key = "NSE_INDEX|Nifty 50" if symbol == "NIFTY" else "NSE_INDEX|Nifty Bank"
            index_price = latest_prices.get(index_key, 0)

            threading.Thread(target=save_oi_to_db, args=(symbol, total_ce_oi, total_pe_oi, index_price), daemon=True).start()
            pcr_running_totals[symbol]['last_save'] = now_time

def save_strike_oi_to_db(instrument_key, oi, price):
    """Persists per-instrument OI for buildup analysis."""
    try:
        db = get_db()
        coll = db['strike_oi_data']
        now = datetime.now()
        doc = {
            'instrument_key': instrument_key,
            'date': now.strftime("%Y-%m-%d"),
            'timestamp': now.strftime("%H:%M:%S"),
            'oi': oi,
            'price': price,
            'updated_at': now
        }
        # Only save if OI changed or every 1 minute to avoid bloat
        last_emit = last_emit_times.get(f"SAVE_STRIKE_{instrument_key}", 0)
        if time.time() - last_emit > 60: # Every 1 minute
            coll.insert_one(doc)
            last_emit_times[f"SAVE_STRIKE_{instrument_key}"] = time.time()
    except Exception as e:
        logging.error(f"Error saving strike OI: {e}")

def save_oi_to_db(symbol, call_oi, put_oi, price=0):
    """Persists aggregated OI to MongoDB for historical analytics."""
    try:
        oi_coll = get_oi_collection()
        now = datetime.now()
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
    """Starts a background thread to calculate PCR periodically."""
    def run_pcr_loop():
        while True:
            try:
                # In a real app, we'd fetch the latest option chain from DB or API
                # For now, we'll look at the latest OI data in MongoDB
                oi_coll = get_oi_collection()
                # Aggregate PCR for NIFTY (example)
                # This is a placeholder for actual aggregation logic
                # We would normally filter by current expiry and instrument
                pass
            except Exception as e:
                logging.error(f"PCR Calculation loop error: {e}")
            time.sleep(60)

    t = threading.Thread(target=run_pcr_loop, daemon=True)
    t.start()

def is_market_hours() -> bool:
    """Checks if the current time is within Indian market hours (09:15 - 15:30 IST)."""
    import pytz
    ist = pytz.timezone('Asia/Kolkata')
    now_ist = datetime.now(ist)

    # Weekends (Saturday=5, Sunday=6)
    if now_ist.weekday() >= 5:
        return False

    start_time = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    end_time = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    return start_time <= now_ist <= end_time

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

def load_intraday_data(instrument_key):
    """
    Fetches and aggregates today's data from 9:15 AM to NOW for an instrument.

    Args:
        instrument_key (str): The instrument key.

    Returns:
        list: A list of aggregated OHLC/Footprint bars.
    """
    now = datetime.now()
    start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    start_ts = start_time.timestamp()

    cursor = tick_collection.find({'instrumentKey': instrument_key}).sort('_id', 1)
    bars = []

    try:
        # Create a collector for replay data
        def collect_bar(event, data, room=None):
            if event == 'footprint_data':
                bars.append(data)

        replay = ReplayManager(emit_fn=collect_bar)
        replay.timeframe_sec = 60
        for doc in cursor:
            ff = doc.get('fullFeed', {}).get('marketFF', {})
            if not ff: continue
            ltt = int(ff.get('ltpc', {}).get('ltt', 0))
            if (ltt / 1000.0) < start_ts: continue
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
        if 'fullFeed' not in data or 'marketFF' not in data['fullFeed']:
            return

        ff = data['fullFeed']['marketFF']
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
        if 'fullFeed' in data and 'marketFF' in data['fullFeed']:
            self.aggregated_bar['oi'] = float(data['fullFeed']['marketFF'].get('oi', self.aggregated_bar.get('oi', 0)))

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
