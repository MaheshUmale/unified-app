
import json
import websocket
import threading
import time
from datetime import datetime
from database import get_tick_data_collection, get_oi_collection, get_instruments_collection, get_stocks_collection, get_raw_tick_data_collection
import asyncio
import json
import ssl
import websockets
import requests
from google.protobuf.json_format import MessageToDict
import sys
import time
from collections import deque
from datetime import datetime, timedelta
import uuid
import random # <-- REQUIRED FOR BACKOFF JITTER (already in your file)
import traceback # <-- REQUIRED FOR DETAILED ERROR LOGGING (already in your file)
import pandas as pd
import MarketDataFeedV3_pb2 as pb

import asyncio
import logging
import requests
from upstox_client import MarketDataStreamerV3, ApiClient, Configuration

import ExtractInstrumentKeys
socketio_instance = None
stop_replay_flag = False
last_emit_times = {} # Track last emit time per instrument for throttling
global subscribed_instruments
subscribed_instruments = set()
initial_instruments =["NSE_INDEX|Nifty 50", "NSE_INDEX|Nifty Bank"]#,"NSE_EQ|INE585B01010","NSE_EQ|INE139A01034","NSE_EQ|INE1NPP01017","NSE_EQ|INE917I01010","NSE_EQ|INE267A01025","NSE_EQ|INE466L01038","NSE_EQ|INE070A01015","NSE_EQ|INE749A01030","NSE_EQ|INE171Z01026","NSE_EQ|INE591G01025","NSE_EQ|INE160A01022","NSE_EQ|INE814H01029","NSE_EQ|INE102D01028","NSE_EQ|INE134E01011","NSE_EQ|INE009A01021","NSE_EQ|INE376G01013","NSE_EQ|INE619A01035","NSE_EQ|INE465A01025","NSE_EQ|INE540L01014","NSE_EQ|INE237A01028","NSE_EQ|INE361B01024","NSE_EQ|INE811K01011","NSE_EQ|INE01EA01019","NSE_EQ|INE030A01027","NSE_EQ|INE476A01022","NSE_EQ|INE721A01047","NSE_EQ|INE028A01039","NSE_EQ|INE670K01029","NSE_EQ|INE158A01026","NSE_EQ|INE123W01016","NSE_EQ|INE192A01025","NSE_EQ|INE118A01012","NSE_EQ|INE674K01013","NSE_EQ|INE094A01015","NSE_EQ|INE528G01035","NSE_EQ|INE093I01010","NSE_EQ|INE073K01018","NSE_EQ|INE006I01046","NSE_EQ|INE142M01025","NSE_EQ|INE169A01031","NSE_EQ|INE849A01020","NSE_EQ|INE669C01036","NSE_EQ|INE216A01030","NSE_EQ|INE111A01025","NSE_EQ|INE062A01020","NSE_EQ|INE081A01020","NSE_EQ|INE883A01011","NSE_EQ|INE075A01022","NSE_EQ|INE498L01015","NSE_EQ|INE377N01017","NSE_EQ|INE484J01027","NSE_EQ|INE205A01025","NSE_EQ|INE027H01010","NSE_EQ|INE121A01024","NSE_EQ|INE974X01010","NSE_EQ|INE854D01024","NSE_EQ|INE742F01042","NSE_EQ|INE226A01021","NSE_EQ|INE047A01021","NSE_EQ|INE326A01037","NSE_EQ|INE584A01023","NSE_EQ|INE414G01012","NSE_EQ|INE669E01016","NSE_EQ|INE211B01039","NSE_EQ|INE813H01021","NSE_EQ|INE213A01029","NSE_EQ|INE335Y01020","NSE_EQ|INE931S01010","NSE_EQ|INE704P01025","NSE_EQ|INE053F01010","NSE_EQ|INE127D01025","NSE_EQ|INE021A01026","NSE_EQ|INE356A01018","NSE_EQ|INE733E01010","NSE_EQ|INE115A01026","NSE_EQ|INE702C01027","NSE_EQ|INE388Y01029","NSE_EQ|INE117A01022","NSE_EQ|INE239A01024","NSE_EQ|INE437A01024","NSE_EQ|INE245A01021","NSE_EQ|INE053A01029","NSE_EQ|INE196A01026","NSE_EQ|INE121J01017","NSE_EQ|INE399L01023","NSE_EQ|INE121E01018","NSE_EQ|INE019A01038","NSE_EQ|INE151A01013","NSE_EQ|INE522F01014","NSE_EQ|INE296A01032","NSE_EQ|INE066F01020","NSE_EQ|INE002A01018","NSE_EQ|INE203G01027","NSE_EQ|INE467B01029","NSE_EQ|INE0ONG01011","NSE_EQ|INE079A01024","NSE_EQ|INE0J1Y01017","NSE_EQ|INE260B01028","NSE_EQ|INE040A01034","NSE_EQ|INE121A08PJ0","NSE_EQ|INE603J01030","NSE_EQ|INE202E01016","NSE_EQ|INE663F01032","NSE_EQ|INE066A01021","NSE_EQ|INE752E01010","NSE_EQ|INE271C01023","NSE_EQ|INE318A01026","NSE_EQ|INE918I01026","NSE_EQ|INE758E01017","NSE_EQ|INE089A01031","NSE_EQ|INE848E01016","NSE_EQ|INE982J01020","NSE_EQ|INE761H01022","NSE_EQ|INE494B01023","NSE_EQ|INE646L01027","NSE_EQ|INE0V6F01027","NSE_EQ|INE010B01027","NSE_EQ|INE302A01020","NSE_EQ|INE634S01028","NSE_EQ|INE397D01024","NSE_EQ|INE192R01011","NSE_EQ|INE775A08105","NSE_EQ|INE059A01026","NSE_EQ|INE377Y01014","NSE_EQ|INE343G01021","NSE_EQ|INE797F01020","NSE_EQ|INE180A01020","NSE_EQ|INE949L01017","NSE_EQ|INE881D01027","NSE_EQ|INE795G01014","NSE_EQ|INE280A01028","NSE_EQ|INE298A01020","NSE_EQ|INE155A01022","NSE_EQ|INE274J01014","NSE_EQ|INE012A01025","NSE_EQ|INE095A01012","NSE_EQ|INE562A01011","NSE_EQ|INE195A01028","NSE_EQ|INE118H01025","NSE_EQ|INE364U01010","NSE_EQ|INE238A01034","NSE_EQ|INE044A01036","NSE_EQ|INE379A01028","NSE_EQ|INE338I01027","NSE_EQ|INE935N01020","NSE_EQ|INE038A01020","NSE_EQ|INE031A01017","NSE_EQ|INE242A01010","NSE_EQ|INE692A01016","NSE_EQ|INE04I401011","NSE_EQ|INE061F01013","NSE_EQ|INE263A01024","NSE_EQ|INE020B01018","NSE_EQ|INE685A01028","NSE_EQ|INE647A01010","NSE_EQ|INE860A01027","NSE_EQ|INE0BS701011","NSE_EQ|INE00H001014","NSE_EQ|INE171A01029","NSE_EQ|INE262H01021","NSE_EQ|INE084A01016","NSE_EQ|INE775A01035","NSE_EQ|INE878B01027","NSE_EQ|INE018E01016","NSE_EQ|INE776C01039","NSE_EQ|INE417T01026","NSE_EQ|INE415G01027","NSE_EQ|INE821I01022","NSE_EQ|INE323A01026","NSE_EQ|INE214T01019","NSE_EQ|INE176B01034","NSE_EQ|INE249Z01020","NSE_EQ|INE343H01029","NSE_EQ|INE758T01015","NSE_EQ|INE154A01025","NSE_EQ|INE455K01017","NSE_EQ|INE406A01037","NSE_EQ|INE101A01026","NSE_EQ|INE208A01029","NSE_EQ|INE303R01014","NSE_EQ|INE090A01021","NSE_EQ|INE472A01039","NSE_EQ|INE628A01036","NSE_EQ|INE040H01021","NSE_EQ|INE018A01030","NSE_EQ|INE092T01019","NSE_EQ|INE067A01029","NSE_EQ|INE423A01024","NSE_EQ|INE259A01022","NSE_EQ|INE07Y701011","NSE_EQ|INE765G01017","NSE_EQ|INE257A01026","NSE_EQ|INE774D01024","NSE_EQ|INE129A01019","NSE_EQ|INE481G01011","NSE_EQ|INE114A01011","NSE_EQ|INE774D08MG3","NSE_EQ|INE935A01035","NSE_EQ|INE003A01024","NSE_EQ|INE029A01011","NSE_EQ|INE670A01012","NSE_EQ|INE200M01039","NSE_EQ|INE016A01026"]
subscribed_instruments.update(initial_instruments)
subscribed_instruments.update(ExtractInstrumentKeys.getNiftyAndBNFnOKeys())
# Initialize Collection





tick_collection = get_tick_data_collection()
raw_tick_collection = get_raw_tick_data_collection()
def set_socketio(sio):
    """Allows the main app to inject the SocketIO instance."""
    global socketio_instance
    socketio_instance = sio

# Session State (Per-Instrument)
# active_bars[instrument_token] = { aggregated_bar_data }
active_bars = {}
# session_stats[instrument_token] = { cvd: 0, vol: 0, count: 0 }
active_bars = {}
# session_stats[instrument_token] = { cvd: 0, vol: 0, count: 0 }
session_stats = {}

# --- Strategy Registry ---
# active_strategies[instrument_key] = [strategy_instance_1, strategy_instance_2]
active_strategies = {}

def register_strategy(instrument_key, strategy_instance):
    """Registers a strategy instance to receive ticks for an instrument."""
    if instrument_key not in active_strategies:
        active_strategies[instrument_key] = []
    active_strategies[instrument_key].append(strategy_instance)
    # print(f"[DATA ENGINE] Registered strategy {strategy_instance.__class__.__name__} for {instrument_key}")

# --- Upstox WebSocket Logic ---
# --- Upstox WebSocket Logic ---

import MarketDataFeedV3_pb2 as pb
def decode_protobuf(buffer: bytes) -> pb.FeedResponse:
    """Decode the binary Protobuf message into a Python object."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response

import os
import sys
# # D:\OPTIMIZEDAPP\APP\main_live.py
# sys.path.append(os.path.join(os.path.dirname('D:\OPTIMIZEDAPP\APP\main_live.py') ))
# sys.path.append(os.path.join(os.path.dirname('D:\OPTIMIZEDAPP\APP') ))

# from main_live import onMSG









def on_message(message):
    global active_bars, session_stats, socketio_instance

    # Initialize feed data container
    data = None
    # print(message)
    # 0. Check if already Dict (SDK default)
    if isinstance(message, dict):
        data = message

    # 1. Try Protobuf Decode (Binary)
    elif isinstance(message, bytes):
        try:
            decoded_data = decode_protobuf(message)
            data = MessageToDict(decoded_data)
        except Exception as e:
            print(f"Protobuf decode failed: {e}")
            pass

    # 2. Try JSON Decode (Text) if not already decoded
    if data is None:
        try:
             # If message is bytes, json.loads will try to decode as utf-8.
             # If it's invalid utf-8 (bad binary), this throws UnicodeDecodeError.
             # If it's valid string but not JSON, throws JSONDecodeError.
             data = json.loads(message)
             print(f"WSS Text Msg: {data}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Not JSON, and Protobuf failed earlier. Ignore.
            return

    # 3. Archive the raw tick to MongoDB (Optional: store 'data' dict instead of raw message)
    # Storing the processed dict is safer/easier to query than raw bytes.
    # tick_collection.insert_one({'raw_msg': message}) # Skip raw bytes storing for now
    if data:
        # Optimization: Insert specific feed items, not the whole wrapper event if possible.
        # But 'data' structure here is the FeedResponse.
        pass # We'll insert inside the feeds handling for better granularity

    # --- Strategy Dispatch & Processing ---
    # Upstox V3 FeedResponse structure: {"feeds": {"NSE_EQ|...": {"fullFeed": ...}}}

    # Check Message Type
    msg_type = data.get('type')

    # Handle 'initial_feed' (Type 0) or 'market_info' (Type 2)
    # Handle 'initial_feed' (Type 0) or 'market_info' (Type 2)
    if msg_type == 'initial_feed':
        print(f"WSS: Market Data Snapshot Received. Processing...")
        # Note: Execution falls through to feeds_map processing below
    elif msg_type == 'market_info':
        info = data.get('marketInfo', {})
        print(f"WSS: Market Info Received. Status: {info.get('segmentStatus', 'Unknown')}")
        pass

    # onMSG(data)
    feeds_map = data.get('feeds', {})
    try:
        raw_tick_collection.insert_one(data)


    except Exception as e:
        print(f"MongoDB Insert Error: {e}")

    try:
        jsonData = json.dumps(feeds_map)
        socketio_instance.emit('raw_tick',  jsonData)
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"SocketIO Emit Error: {e}")

    if feeds_map:
        for inst_key, feed_datum in feeds_map.items():
            # Inject key for strategy use and consistency
            feed_datum['instrumentKey'] = inst_key

            # Archive individual tick to MongoDB
            # Adding timestamp for querying
            feed_datum['_insertion_time'] = datetime.now()
            try:
                tick_collection.insert_one(feed_datum)
            except Exception as e:
                print(f"MongoDB Insert Error: {e}")

            # Dispatch to Strategies
            if inst_key in active_strategies:
                for strategy in active_strategies[inst_key]:
                    try:
                        strategy.process_tick(feed_datum)
                    except Exception as e:
                        print(f"Error in strategy {strategy.__class__.__name__} for {inst_key}: {e}")

            # 4. Process for Real-time Footprint (Footprint Chart Logic)
            process_footprint_tick(inst_key, feed_datum)

def process_footprint_tick(instrument_key, data_datum):
    global active_bars, session_stats, socketio_instance

    try:
        # Check if fullFeed/marketFF exists
        if 'fullFeed' not in data_datum or 'marketFF' not in data_datum['fullFeed']:
            return

        ff = data_datum['fullFeed']['marketFF']

        # We use the instrument_key we validated/injected in the loop
        instrument_token = instrument_key
        if not instrument_token:
             return

        ltpc = ff.get('ltpc')
        ohlc_list = ff.get('marketOHLC', {}).get('ohlc', [])
        bid_ask_quotes = ff.get('marketLevel', {}).get('bidAskQuote', [])

        # We look for the 1-minute candle 'I1' timestamp to bin our footprint
        ohlc_1min = next((o for o in ohlc_list if o.get('interval') == 'I1'), None)

        if (not ohlc_1min and (not ltpc or 'ltt' not in ltpc)) or not ltpc.get('ltp'):
            return

        # CRITICAL FIX: Always use LTT (Last Trade Time) for bar timestamp
        # OHLC timestamp is for the PREVIOUS completed candle, causing 1-minute lag
        # We bin LTT to the current minute ourselves
        raw_ltt = int(ltpc['ltt'])
        current_bar_ts = (raw_ltt // 60000) * 60000

        # DEBUG: Verify timestamp calculation
        if instrument_token == "NSE_EQ|INE002A01018":  # Reliance for debugging
            from datetime import datetime
            ohlc_ts = int(ohlc_1min['ts']) if ohlc_1min else 0
            # print(f"[BAR TS DEBUG] LTT: {datetime.fromtimestamp(raw_ltt/1000).strftime('%H:%M:%S')} → Bar: {datetime.fromtimestamp(current_bar_ts/1000).strftime('%H:%M:%S')} | OHLC was: {datetime.fromtimestamp(ohlc_ts/1000).strftime('%H:%M:%S') if ohlc_ts else 'N/A'}")

        # DEBUG: Log system time vs feed time
        import time
        system_time_ms = int(time.time() * 1000)
        feed_time_ms = int(ltpc.get('ltt', 0))
        lag_seconds = (system_time_ms - feed_time_ms) / 1000.0

        # Only log occasionally to avoid spam (every 10 seconds)
        if not hasattr(process_footprint_tick, '_last_log_time'):
            process_footprint_tick._last_log_time = {}

        if instrument_token not in process_footprint_tick._last_log_time or \
           (system_time_ms - process_footprint_tick._last_log_time.get(instrument_token, 0)) > 10000:
            from datetime import datetime
            bar_time_str = datetime.fromtimestamp(current_bar_ts/1000).strftime('%H:%M:%S')
            # print(f"[TIME DEBUG] {instrument_token[:20]}... | System: {datetime.fromtimestamp(system_time_ms/1000).strftime('%H:%M:%S')} | Feed LTT: {datetime.fromtimestamp(feed_time_ms/1000).strftime('%H:%M:%S')} | Bar TS: {bar_time_str} | Lag: {lag_seconds:.1f}s")
            process_footprint_tick._last_log_time[instrument_token] = system_time_ms

        trade_price = float(ltpc['ltp'])
        trade_qty = int(ltpc.get('ltq', 0))

        # Initialize Data Structures for this token if missing
        if instrument_token not in active_bars:
            active_bars[instrument_token] = None
        if instrument_token not in session_stats:
            session_stats[instrument_token] = {'cvd': 0, 'total_vol': 0, 'trade_count': 0}

        aggregated_bar = active_bars[instrument_token]

        # Check if we moved to a new bar
        if aggregated_bar and current_bar_ts > aggregated_bar['ts']:
            if socketio_instance:
                # Emit to specific room or with token in payload
                socketio_instance.emit('footprint_data', aggregated_bar, room=instrument_token)
            active_bars[instrument_token] = None
            aggregated_bar = None

        # Initialize new bar if needed
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
                'footprint': {},
                'instrument_token': instrument_token
            }
            active_bars[instrument_token] = aggregated_bar

            # Emit the new bar immediately so it appears in real-time
            if socketio_instance:
                socketio_instance.emit('footprint_update', aggregated_bar, room=instrument_token)

        # Ignore out-of-order old ticks
        if current_bar_ts < aggregated_bar['ts']:
            return

        # Update OHLC
        aggregated_bar['high'] = max(aggregated_bar['high'], trade_price)
        aggregated_bar['low'] = min(aggregated_bar['low'], trade_price)
        aggregated_bar['close'] = trade_price
        aggregated_bar['volume'] += trade_qty

        # Determine Aggressor Side (Simple B/A matching)
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

        # Binning by Price Level
        price_level = f"{trade_price:.2f}"
        if price_level not in aggregated_bar['footprint']:
            aggregated_bar['footprint'][price_level] = {'buy': 0, 'sell': 0}

        if side in ['buy', 'sell']:
            aggregated_bar['footprint'][price_level][side] += trade_qty

        # Update Session Stats
        stats = session_stats[instrument_token]
        if side == 'buy':
            stats['cvd'] += trade_qty
            aggregated_bar['buy_volume'] = aggregated_bar.get('buy_volume', 0) + trade_qty
        elif side == 'sell':
            stats['cvd'] -= trade_qty
            aggregated_bar['sell_volume'] = aggregated_bar.get('sell_volume', 0) + trade_qty

        stats['total_vol'] += trade_qty
        stats['trade_count'] += 1
        avg_trade_sz = stats['total_vol'] / stats['trade_count'] if stats['trade_count'] > 0 else 0

        aggregated_bar['cvd'] = stats['cvd']
        aggregated_bar['avg_trade_sz'] = avg_trade_sz

        # Emit partial update for smooth UI
        if socketio_instance:
             # Throttled Emit (1000ms = 1 second to reduce load)
             now = time.time()
             if now - last_emit_times.get(instrument_token, 0) > 0.5:
                socketio_instance.emit('footprint_update', aggregated_bar, room=instrument_token)
                last_emit_times[instrument_token] = now

    except (KeyError, IndexError, TypeError, ValueError) as e:
        print(f"Error processing message: {e}")



import upstox_client
from upstox_client.rest import ApiException




# You need the generated protobuf file 'upstox_pb2' available in your directory
# or generate it from the proto file provided by Upstox.
try:
    import MarketDataFeedV3_pb2
except ImportError:
    logging.error("MarketDataFeedV3_pb2.py not found. Please generate it from the .proto file.")
    exit()


# --- Upstox WebSocket Logic (SDK Implementation) ---

# Global Reference for the SDK Streamer
streamer = None

def subscribe_instrument(instrument_key):
    """Dynamic subscription to an instrument using SDK."""
    global streamer
    if streamer:
        if instrument_key in subscribed_instruments:
            # print(f"[SDK] Already subscribed to {instrument_key}")
            return

        print(f"[SDK] Subscribing to {instrument_key}")
        try:
            # Add to local set
            subscribed_instruments.add(instrument_key)
            # Subscribe
            streamer.subscribe([instrument_key], "full")
        except Exception as e:
            print(f"[SDK] Subscription Error: {e}")
    else:
        print("[SDK] Streamer not active, cannot subscribe.")

def on_error(error):
    print(f"WebSocket Error: {error} {datetime.now()}")

def on_open():
    print(f"WebSocket Connected (SDK)! {datetime.now()}")

def on_close(code, reason):
    #print timestamp
    # print()
    print(f"WebSocket Closed: {code} - {reason} -{datetime.now()}")

def on_auto_reconnect_stopped(data):
    """Handler for when auto-reconnect retries are exhausted."""
    print(f" {datetime.now()} == Auto-reconnect stopped after retries: {data}")
    # Consider manual intervention or a higher-level retry here

def start_websocket_thread(access_token, instrument_keys):
    """Starts the Upstox SDK MarketDataStreamerV3 in a background thread."""

    def run_streamer():
        global streamer

        # Populate initial set
        subscribed_instruments.update(instrument_keys)

        print(f"Starting UPSTOX SDK Streamer with {len(instrument_keys)} instruments...")

        # 1. Configure
        configuration = upstox_client.Configuration()
        configuration.access_token = access_token

        # 2. Initialize Streamer
        # Note: The SDK manages the connection, auth, and auto-reconnects.
        try:
            print("DEBUG: Initializing ApiClient...", flush=True)
            api_client = upstox_client.ApiClient(configuration)
            print("DEBUG: ApiClient Initialized. Initializing Streamer...", flush=True)
            streamer = MarketDataStreamerV3(api_client, list(subscribed_instruments), "full")
            print("DEBUG: Streamer Initialized.", flush=True)

            # 3. Register Callbacks
            streamer.on("message", on_message)
            streamer.on("open", on_open)
            streamer.on("error", on_error)
            streamer.on("close", on_close)

            streamer.on("autoReconnectStopped", on_auto_reconnect_stopped)

            # --- Configure Auto-Reconnect ---
            # Enable auto-reconnect, set interval to 15 seconds, and max retries to 5
            ENABLE_AUTO_RECONNECT = True
            INTERVAL_SECONDS = 5
            MAX_RETRIES = 5

            streamer.auto_reconnect(ENABLE_AUTO_RECONNECT, INTERVAL_SECONDS, MAX_RETRIES)


  # --- Periodic Subscription (Keep-Alive) ---
            def subscription_keep_alive(streamer_ref, instruments=[]):
                while True:
                    time.sleep(50) # Every 1 minute
                    try:
                        subscribed_instruments.update(ExtractInstrumentKeys.getNiftyAndBNFnOKeys())
                        instruments = list(subscribed_instruments)
                        print(f"Sending periodic subscription for {len(instruments)} instruments...{datetime.now()}")

                        streamer_ref.subscribe(instruments, "full")
                    except Exception as e:
                        print(f"Periodic subscription failed: {e}")

            # Start keep-alive thread
            ka_thread = threading.Thread(target=subscription_keep_alive, args=(streamer, subscribed_instruments), daemon=True)
            ka_thread.start()


            # 4. Connect (Blocking Call)
            print("Connecting to Upstox V3 via SDK...")

            streamer.connect()

        except Exception as e:
            print(f"SDK Streamer Fatal Error: {e}")
            import traceback
            traceback.print_exc()

    # Run in a daemon thread so it doesn't block the main app
    t = threading.Thread(target=run_streamer, daemon=True)
    t.start()
    return t

def load_intraday_data(instrument_key):
    """Fetches and aggregates today's data from 9:15 AM to NOW."""
    # 1. Get Today's 9:15 AM Timestamp
    now = datetime.now()
    start_time = now.replace(hour=9, minute=15, second=0, microsecond=0)
    start_ts = start_time.timestamp()
    print(f"DEBUG: Loading Intraday Data for {instrument_key} from {start_ts} (Time: {start_time})")
    # 2. Query MongoDB
    # We scan all ticks and filter by time because of index issues mentioned in comments.
    cursor = tick_collection.find({'instrumentKey': instrument_key}).sort('_id', 1)

    # ReplayManager Logic (Parity with Replay Mode)
    bars = []
    class MockSocket:
        def emit(self, event, data, room=None):
            if event == 'footprint_data': bars.append(data)

    try:
        replay = ReplayManager(MockSocket())
        replay.timeframe_sec = 60
        count = 0
        for doc in cursor:
            ff = doc.get('fullFeed', {}).get('marketFF', {})
            if not ff: continue

            ltt = int(ff.get('ltpc', {}).get('ltt', 0))
            ohlc = ff.get('marketOHLC', {}).get('ohlc', [])
            ts = ltt #int(ohlc[0].get('ts')) if ohlc else ltt

            if (ts / 1000.0) < start_ts: continue

            replay.process_replay_tick(doc)
            count += 1

        if replay.aggregated_bar: bars.append(replay.aggregated_bar)

        # Sort bars by timestamp to ensure chronological order
        bars.sort(key=lambda x: x.get('ts', 0))

        print(f"[HISTORY] Loaded {len(bars)} bars via ReplayLogic.")
        return bars
    except NameError:
        return []



# --- Replay Manager Class ---
class ReplayManager:
    def __init__(self, socketio):
        self.socketio = socketio
        self.stop_flag = False
        self.aggregated_bar = None
        self.timeframe_sec = 60  # Default 1 minute
        # Replay state variables
        self.replay_cvd = 0
        self.replay_total_vol = 0
        self.replay_trade_count = 0

    def stop(self):
        self.stop_flag = True

    def start(self, instrument_key, speed=100, start_ts=None, timeframe=1):
        self.timeframe_sec = timeframe * 60  # Convert minutes to seconds
        self.stop_flag = False
        self.aggregated_bar = None

        print(f"Starting replay for {instrument_key} at {speed}ms speed...")

        # Fetch Historical Ticks from MongoDB
        # Optimization: You might want to sort by timestamp
        query = {'instrumentKey': instrument_key}
        if start_ts:
            # start_ts is expected to be seconds or milliseconds.
            # Our ticks are stored with whatever 'ts' structure comes from Upstox.
            # Usually Upstox raw ticks don't have a top-level 'timestamp' field easily indexing ALL ticks unless added.
            # But the 'ltt' inside 'marketFF' is the time.
            # MongoDB optimization: We need to filter by something indexed.
            # Assuming 'timestamp' was added at insert time (line 42).
            # Let's check line 42: tick_collection.insert_one(data).
            # If we didn't add a timestamp field, we scan everything.
            # For now, let's assume we filter in-memory or purely by `_id` if time-sequenced.
            # Ideally: query = {'instrumentKey': instrument_key, 'timestamp': {'$gte': start_ts}}
            # Since we didn't explicitly add 'timestamp' to the insert, we might rely on implied order or 'fullFeed.marketFF.marketOHLC.ohlc.ts' inside.
            # For simplicity in this fix (without re-ingesting data), we can scan and skip.
            pass

        # Using a cursor or list. For large datasets, cursor is better.
        # But we need to sort it.
        # tick_collection is global in this module, but better to use self.db
        # Using a cursor or list. For large datasets, cursor is better.
        # But we need to sort it.
        # tick_collection is global in this module, but better to use self.db
        cursor = tick_collection.find(query).sort('_id', 1)

        # Check if we have any data at all
        total_docs = tick_collection.count_documents(query)
        print(f"[REPLAY] Found {total_docs} total documents for {instrument_key}")

        if total_docs == 0:
            print(f"[REPLAY] No data available for {instrument_key}")
            if self.socketio:
                self.socketio.emit('replay_error', {
                    'message': f'No historical data found for {instrument_key}. Please check the instrument key or date range.'
                })
            return

        # For a smoother replay, we might want to pre-fetch OI data here too
        # But let's verify basic ticks first.

        count = 0
        first_tick_ts = None
        first_valid_tick_ts = None  # First tick >= start_ts
        last_tick_ts = None

        for doc in cursor:
            if self.stop_flag:
                print("Replay stopped.")
                if self.socketio:
                    self.socketio.emit('replay_finished', {'reason': 'stopped'})
                return

            try:
                # Extract timestamp first
                tick_ts = 0
                ff = doc.get('fullFeed', {}).get('marketFF', {})
                ohlc_data = ff.get('marketOHLC', {}).get('ohlc', [])

                if ohlc_data:
                    tick_ts = int(ohlc_data[0].get('ts', 0))

                if not tick_ts:
                    tick_ts = int(ff.get('ltpc', {}).get('ltt', 0))

                if not tick_ts:
                    continue

                tick_ts_sec = tick_ts / 1000.0

                # Track first and last ticks
                if first_tick_ts is None:
                    first_tick_ts = tick_ts_sec
                last_tick_ts = tick_ts_sec

                # Skip if before start_ts
                if start_ts and tick_ts_sec < start_ts:
                    continue

                # Track first valid tick (>= start_ts)
                if first_valid_tick_ts is None:
                    first_valid_tick_ts = tick_ts_sec
                    print(f"[REPLAY] Starting from tick at {tick_ts_sec} (requested: {start_ts})")

                # Process the doc
                self.process_replay_tick(doc)

                if count == 0:
                     print(f"[REPLAY] Processing first tick")

                count += 1
                if count % 10 == 0: # Throttle checks
                    if self.aggregated_bar and self.socketio:
                        self.socketio.emit('footprint_update', self.aggregated_bar)
                    time.sleep(speed / 1000.0)

            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"Replay Error: {e}")

        print(f"[REPLAY] Finished. Processed {count} ticks out of {total_docs} total documents.")

        # Flush the last bar
        if self.aggregated_bar and self.socketio:
             print("[REPLAY] Flushing final bar.")
             self.socketio.emit('footprint_data', self.aggregated_bar)

        if count == 0:
            from datetime import datetime
            error_msg = f'No data found after the selected start date.\n'
            if first_tick_ts and last_tick_ts:
                error_msg += f'Available data range: {datetime.fromtimestamp(first_tick_ts).strftime("%Y-%m-%d %H:%M")} to {datetime.fromtimestamp(last_tick_ts).strftime("%Y-%m-%d %H:%M")}\n'
                error_msg += f'Your selected time: {datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H:%M") if start_ts else "None"}'

            print(f"[REPLAY] WARNING: {error_msg}")
            if self.socketio:
                self.socketio.emit('replay_error', {'message': error_msg})
        elif self.socketio:
            self.socketio.emit('replay_finished', {'reason': 'completed'})

    def process_replay_tick(self, data):
        # reuse the global aggregated_bar logic?
        # Better to have instance-bound aggregation for replay so it doesn't mix with live

        if 'fullFeed' not in data or 'marketFF' not in data['fullFeed']:
            return

        ff = data['fullFeed']['marketFF']
        ltpc = ff.get('ltpc')
        ohlc_list = ff.get('marketOHLC', {}).get('ohlc', [])
        bid_ask_quotes = ff.get('marketLevel', {}).get('bidAskQuote', [])


        ohlc_1min = next((o for o in ohlc_list if o.get('interval') == 'I1'), None)

        if (not ohlc_1min and (not ltpc or 'ltt' not in ltpc)) or not ltpc.get('ltp'):
            # print(f"DEBUG: Skipping tick. OHLC_1min: {bool(ohlc_1min)}, LTP: {ltpc.get('ltp')}")
            return

        # Custom Aggregation Logic based on self.timeframe_sec
        # Extract tick timestamp first
        tick_ts_ms = 0
        if ohlc_1min:
             tick_ts_ms = int(ohlc_1min['ts'])
        elif 'ltt' in ltpc:
             tick_ts_ms = int(ltpc['ltt'])
        else:
             return # Cannot Aggregate

        # Floor timestamp to timeframe
        tick_ts_sec = tick_ts_ms // 1000
        bar_start_sec = tick_ts_sec - (tick_ts_sec % self.timeframe_sec)
        current_bar_ts = bar_start_sec * 1000 # Back to ms for consistency

        # Extract price and quantity
        trade_price = float(ltpc.get('ltp', 0))
        trade_qty = int(ltpc.get('ltq', 0))

        if not trade_price or trade_price <= 0:
            return

        # Check if we moved to a new bar
        if self.aggregated_bar and current_bar_ts > self.aggregated_bar['ts']:
            if self.socketio:
                # print(f"[REPLAY] Emitting Bar: {self.aggregated_bar['ts']}")
                # Emit the finished bar
                self.socketio.emit('footprint_data', self.aggregated_bar)
            # Reset for new bar
            self.aggregated_bar = None

        if not self.aggregated_bar:
            self.aggregated_bar = {
                'ts': current_bar_ts,
                'open': trade_price,
                'high': trade_price,
                'low': trade_price,
                'close': trade_price,
                'volume': 0,
                'buy_volume': 0,
                'sell_volume': 0,
                'big_buy_volume': 0,
                'big_sell_volume': 0,
                'bubbles': [], # List of {ts, price, qty, impact}
                'footprint': {}
            }

        if current_bar_ts < self.aggregated_bar['ts']:
            return

        self.aggregated_bar['high'] = max(self.aggregated_bar['high'], trade_price)
        self.aggregated_bar['low'] = min(self.aggregated_bar['low'], trade_price)
        self.aggregated_bar['close'] = trade_price
        self.aggregated_bar['volume'] += trade_qty

        # Helper to determine side
        side = 'unknown'
        for quote in bid_ask_quotes:
            if trade_price >= float(quote.get('askP', 0.0)): # Aggressor Buy
                side = 'buy'
                break
        if side == 'unknown':
            for quote in bid_ask_quotes:
                if trade_price <= float(quote.get('bidP', 0.0)): # Aggressor Sell
                    side = 'sell'
                    break

        # Big Player Threshold (Hardcoded or Configurable)
        BIG_PLAYER_THRESHOLD = 50

        if side == 'buy':
            self.aggregated_bar['buy_volume'] += trade_qty
            if trade_qty >= BIG_PLAYER_THRESHOLD:
                self.aggregated_bar['big_buy_volume'] += trade_qty
        elif side == 'sell':
            self.aggregated_bar['sell_volume'] += trade_qty
            if trade_qty >= BIG_PLAYER_THRESHOLD:
                self.aggregated_bar['big_sell_volume'] += trade_qty

        # Bubble Logic
        # Try to get exact trade time (LTT)
        bubble_ts = current_bar_ts

        # In live feed, 'ltpc' has 'ltt' (epoch ms)
        # In replay, we might need to rely on the tick's timestamp if stored
        if 'ltt' in ltpc:
            try:
                bubble_ts = int(ltpc['ltt'])
            except:
                pass

        # If bubble_ts is 0 or very small (seconds), convert to ms if needed
        # But usually Upstox sends ms.
        # Check if bubble_ts is unreasonably far from current_bar_ts (e.g. seconds vs ms mismatch)
        # If bar is 1700000000000 and bubble is 1700000000, scale it.
        if bubble_ts < 1000000000000:
            bubble_ts *= 1000

        if trade_qty >= BIG_PLAYER_THRESHOLD:
            self.aggregated_bar['bubbles'].append({
                'x': bubble_ts,
                'y': trade_price,
                'q': trade_qty,
                'side': side
            })

        price_level = f"{trade_price:.2f}"
        if price_level not in self.aggregated_bar['footprint']:
            self.aggregated_bar['footprint'][price_level] = {'buy': 0, 'sell': 0}

        if side == 'buy':
             self.replay_cvd += trade_qty
        elif side == 'sell':
             self.replay_cvd -= trade_qty

        self.replay_total_vol += trade_qty
        self.replay_trade_count += 1
        avg_trade = self.replay_total_vol / self.replay_trade_count if self.replay_trade_count > 0 else 0

        self.aggregated_bar['cvd'] = self.replay_cvd
        self.aggregated_bar['avg_trade_sz'] = avg_trade

        if side in ['buy', 'sell']:
            self.aggregated_bar['footprint'][price_level][side] += trade_qty

        if self.socketio:
            # print(f"DEBUG: Emitting footprint_update for TS: {self.aggregated_bar['ts']}")
            self.socketio.emit('footprint_update', self.aggregated_bar)
            # print("DEBUG: Emitted.")
        else:
            # print("DEBUG: No socketio instance to emit!")
            pass


replay_manager = None
import time # Ensure time is imported processing

def start_replay_thread(instrument_key, speed=100, start_ts=None, timeframe=1):
    global replay_manager
    if not replay_manager:
        replay_manager = ReplayManager(socketio_instance)

    # Run in thread
    t = threading.Thread(target=replay_manager.start, args=(instrument_key, speed, start_ts, timeframe))
    t.start()

def stop_active_replay():
    if replay_manager:
        replay_manager.stop()
