"""
ProTrade Data Engine
Manages real-time data ingestion from Upstox, strategy dispatching, and real-time OHLC/Footprint aggregation.
"""
import asyncio
import json
from datetime import datetime, timedelta
import logging
logger = logging.getLogger(__name__)
import random
import ssl
import sys
import threading
import time
import traceback
import uuid
from collections import deque
from datetime import datetime, timedelta

from external import trendlyne_api as TrendlyneAPI
from db.local_db import db, LocalDBJSONEncoder
from typing import Dict, Any, List, Optional, Set, Union
from core.pcr_logic import calculate_total_pcr, analyze_oi_buildup
from core.symbol_mapper import symbol_mapper

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

# Batching for DuckDB
TICK_BATCH_SIZE = 100
tick_buffer = []
buffer_lock = threading.Lock()

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

    # Ensure data is JSON serializable
    if isinstance(data, (dict, list)):
        data = json.loads(json.dumps(data, cls=LocalDBJSONEncoder))

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
    """Flushes the tick buffer to LocalDB."""
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
            logging.error(f"LocalDB Batch Insert Error: {e}")

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

def normalize_key(key: str) -> str:
    """Normalizes instrument keys to use pipe separator instead of colon."""
    if not key: return key
    return key.replace(':', '|')

def on_message(message: Union[Dict, bytes, str]):
    """
    Primary callback for incoming data messages (TradingView).
    Handles archiving to LocalDB, and dispatching to registered strategies and UI.
    """
    global active_bars, session_stats, socketio_instance

    data = None
    if isinstance(message, dict):
        data = message
    elif isinstance(message, str):
        try:
            data = json.loads(message)
        except:
            return
    else:
        return

    msg_type = data.get('type')
    if msg_type == 'initial_feed':
        logging.info("WSS: Market Data Snapshot Received.")
    elif msg_type == 'market_info':
        info = data.get('marketInfo', {})
        logging.info(f"WSS: Market Info Received. Status: {info.get('segmentStatus', 'Unknown')}")

    feeds_map = data.get('feeds', {})
    # if feeds_map:
    #     logger.info(f"WSS: Received ticks for {list(feeds_map.keys())}")

    if feeds_map:
        current_time = datetime.now()
        new_ticks = []
        hrn_feeds = {}

        today_str = current_time.strftime("%Y-%m-%d")
        for inst_key, feed_datum in list(feeds_map.items()):
            # Resolve HRN
            inst_key = normalize_key(inst_key)
            meta = instrument_metadata.get(inst_key)

            # If it's already an HRN (from TV feed), use it
            if inst_key in ['NIFTY', 'BANKNIFTY', 'FINNIFTY', 'INDIA VIX']:
                hrn = inst_key
            else:
                hrn = symbol_mapper.get_hrn(inst_key, meta)

            feed_datum['instrumentKey'] = hrn
            feed_datum['raw_key'] = inst_key # Keep raw key for internal use
            feed_datum['date'] = today_str # Optimized for replay
            feed_datum['_insertion_time'] = current_time
            hrn_feeds[hrn] = feed_datum

            # Replace raw key with HRN in the main data object for uniform storage
            del feeds_map[inst_key]
            feeds_map[hrn] = feed_datum

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
                    persistence_queue.put((save_vix_to_db, latest_vix['value'], hrn))

            if 'oi' in market_ff:
                new_oi = float(market_ff['oi'])
                latest_oi[inst_key] = new_oi
                latest_oi[hrn] = new_oi
                update_pcr_for_instrument(inst_key)

            if 'iv' in market_ff:
                latest_iv[inst_key] = float(market_ff['iv'])
                latest_iv[hrn] = float(market_ff['iv'])

            if 'optionGreeks' in market_ff:
                g = market_ff['optionGreeks']
                lg = {
                    'delta': float(g.get('delta', 0)),
                    'theta': float(g.get('theta', 0)),
                    'gamma': float(g.get('gamma', 0)),
                    'vega': float(g.get('vega', 0))
                }
                latest_greeks[inst_key] = lg
                latest_greeks[hrn] = lg

            if 'vtt' in market_ff:
                latest_vtt[inst_key] = float(market_ff['vtt'])
                latest_vtt[hrn] = float(market_ff['vtt'])

            market_levels = market_ff.get('marketLevel', {}).get('bidAskQuote', [])
            if market_levels:
                top = market_levels[0]
                ba = {
                    'bid': float(top.get('bidP', 0)),
                    'ask': float(top.get('askP', 0))
                }
                latest_bid_ask[inst_key] = ba
                latest_bid_ask[hrn] = ba

            # Persist per-strike metrics for strategy analysis
            if inst_key in instrument_metadata:
                meta = instrument_metadata[inst_key]
                if meta['type'] in ['CE', 'PE', 'FUT']:
                    ltpc = market_ff.get('ltpc')
                    price = float(ltpc['ltp']) if ltpc and ltpc.get('ltp') else 0
                    oi = latest_oi.get(hrn, 0)
                    iv = latest_iv.get(hrn, 0)
                    greeks = latest_greeks.get(hrn, {})

                    # Offload to queue instead of starting a new thread
                    persistence_queue.put((save_strike_metrics_to_db, hrn, oi, price, iv, greeks))

            # Determine if this is an index tick or a market instrument tick
            # Explicitly avoid mixing index prices into option charts
            is_index = False
            if meta:
                is_index = meta.get('type') == 'INDEX'
            else:
                # Fallback: identify by field presence if metadata missing
                is_index = 'indexFF' in ff and 'marketFF' not in ff

            ltpc = index_ff.get('ltpc') if is_index else market_ff.get('ltpc')

            if ltpc and ltpc.get('ltt'):
                ts_val = int(ltpc['ltt'])
                # Robustness: Detect 10-digit (seconds) timestamps and convert to milliseconds
                if ts_val > 0 and ts_val < 10000000000:
                    ts_val *= 1000

                feed_datum['ts_ms'] = ts_val
                if ltpc.get('ltp'):
                    price = float(ltpc['ltp'])
                    feed_datum['last_price'] = price
                    latest_prices[inst_key] = price
                    latest_prices[hrn] = price

                # Explicitly capture last traded quantity for volume aggregation
                if ltpc.get('ltq'):
                    feed_datum['ltq'] = int(ltpc['ltq'])
                else:
                    feed_datum['ltq'] = 0

            new_ticks.append(feed_datum)

            # Strategy dispatch using HRN
            if hrn in active_strategies:
                for strategy in active_strategies[hrn]:
                    try:
                        strategy.process_tick(feed_datum)
                    except Exception as e:
                        logging.error(f"Error in strategy {strategy.__class__.__name__} for {hrn}: {e}")

            process_footprint_tick(hrn, feed_datum)

        # Throttled SocketIO Emission (Global per feed message)
        try:
            if socketio_instance:
                now = time.time()
                # Only emit if 100ms has passed since last global 'raw_tick'
                if now - last_emit_times.get('GLOBAL_RAW_TICK', 0) > 0.1:
                    emit_event('raw_tick', hrn_feeds)
                    last_emit_times['GLOBAL_RAW_TICK'] = now
        except Exception as e:
            logging.error(f"SocketIO raw_tick Emit Error: {e}")

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
        instrument_key (str): The HRN of the instrument.
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
        if raw_ltt > 0 and raw_ltt < 10000000000:
            raw_ltt *= 1000

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

        # Handle index volume from TradingView
        tv_vol = data_datum.get('tv_volume')
        if tv_vol is not None:
            aggregated_bar['volume'] = float(tv_vol)
        else:
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

def subscribe_instrument(instrument_key: str):
    """Dynamic subscription to an instrument. TradingView feed polls automatically."""
    raw_key = symbol_mapper.resolve_to_key(instrument_key) or instrument_key

    # Try to resolve metadata if not present
    if raw_key not in instrument_metadata:
        threading.Thread(target=resolve_metadata, args=(raw_key,), daemon=True).start()

def resolve_metadata(instrument_key: str):
    """Resolves and caches instrument metadata. Uses TradingView/Trendlyne for lookup."""
    try:
        # Resolve from Local DB first
        res = db.get_metadata(instrument_key)
        if res:
            meta = res.get('metadata')
            if meta:
                instrument_metadata[instrument_key] = meta

        # If not in DB, try to deduce from HRN if it's already an HRN
        if instrument_key not in instrument_metadata:
            if any(x in instrument_key for x in ['CALL', 'PUT', 'FUT']):
                # Deduce meta from HRN string
                parts = instrument_key.split(' ')
                # NIFTY 06 FEB 2026 CALL 25500
                if len(parts) >= 6:
                    symbol = parts[0]
                    expiry = parts[1:4] # DD MMM YYYY
                    itype = parts[4]
                    strike = parts[5]

                    try:
                        exp_dt = datetime.strptime(" ".join(expiry), "%d %b %Y")
                        meta = {
                            'symbol': symbol,
                            'type': 'CE' if itype == 'CALL' else 'PE' if itype == 'PUT' else 'FUT',
                            'strike': float(strike),
                            'expiry': exp_dt.strftime('%Y-%m-%d')
                        }
                        instrument_metadata[instrument_key] = meta
                        symbol_mapper.get_hrn(instrument_key, meta)
                    except:
                        pass

        # Update current nearest expiry for the symbol
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
    symbol = symbol_mapper.get_symbol(raw_symbol)
    if symbol == "UNKNOWN":
        symbol = raw_symbol

    if symbol not in pcr_running_totals:
        pcr_running_totals[symbol] = {'CE': 0, 'PE': 0, 'last_save': 0, 'last_emit': 0, 'last_calc': 0}

    now_time = time.time()
    # Global Throttle for calculation: 5 seconds
    if now_time - pcr_running_totals[symbol].get('last_calc', 0) < 5:
        return
    pcr_running_totals[symbol]['last_calc'] = now_time

    # Re-calculate totals for the symbol (only for the nearest expiry)
    total_ce_oi = 0
    total_pe_oi = 0

    target_expiry = current_expiries.get(meta['symbol'], '')

    for r_key, oi in latest_oi.items():
        m = instrument_metadata.get(r_key)
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
            index_key = symbol_mapper.resolve_to_key(symbol)
            if index_key:
                index_price = latest_prices.get(index_key, 0)

            threading.Thread(target=save_oi_to_db, args=(symbol, total_ce_oi, total_pe_oi, index_price), daemon=True).start()
            pcr_running_totals[symbol]['last_save'] = now_time

def save_vix_to_db(vix_value, hrn="INDIA VIX"):
    """Persists India VIX for strategy context. Gated by replay timestamps."""
    if replay_mode: return # Keep simulation in memory
    try:
        now = get_now()
        date_str = now.strftime("%Y-%m-%d")
        ts_str = now.strftime("%H:%M:%S")

        last_save = last_emit_times.get("SAVE_VIX", 0)
        if time.time() - last_save > 60:
            db.insert_vix(date_str, hrn, ts_str, vix_value)
            last_emit_times["SAVE_VIX"] = time.time()
    except Exception as e:
        logging.error(f"Error saving VIX: {e}")

def save_strike_metrics_to_db(hrn, oi, price, iv=0, greeks=None):
    """Persists per-instrument metrics for buildup and strategy analysis. Gated by replay timestamps."""
    try:
        now = get_now()
        # We need the raw key for bid_ask lookups if we haven't mapped those to HRN yet
        raw_key = symbol_mapper.resolve_to_key(hrn)
        ba = latest_bid_ask.get(raw_key or hrn, {})
        spread = abs(ba.get('ask', 0) - ba.get('bid', 0)) if ba else 0

        doc = {
            'instrument_key': hrn,
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
            if hrn not in sim_strike_data:
                sim_strike_data[hrn] = []
            sim_strike_data[hrn].append(doc)
            # Limit history to 2 hours of 1-min data
            if len(sim_strike_data[hrn]) > 120:
                sim_strike_data[hrn].pop(0)
            return

        # Regular live persistence
        # Only save every 1 minute to avoid bloat
        last_emit = last_emit_times.get(f"SAVE_STRIKE_{hrn}", 0)
        if time.time() - last_emit > 60: # Every 1 minute
            db.insert_strike_metric(doc)
            last_emit_times[f"SAVE_STRIKE_{hrn}"] = time.time()
    except Exception as e:
        logging.error(f"Error saving strike metrics: {e}")

def save_oi_to_db(symbol, call_oi, put_oi, price=0):
    """Persists aggregated OI for historical analytics. Gated by replay timestamps."""
    if replay_mode: return # Skip for replay to avoid pollution
    try:
        now = get_now()
        date_str = now.strftime("%Y-%m-%d")
        ts_str = now.strftime("%H:%M")
        db.insert_oi(symbol, date_str, ts_str, call_oi, put_oi, price, source='live_engine')
        logging.info(f"Saved real-time OI for {symbol}")
    except Exception as e:
        logging.error(f"Error saving real-time OI: {e}")

def start_pcr_calculation_thread():
    """Starts background threads for accurate PCR calculation and expiry tracking."""
    from external.tv_mcp import process_option_chain_with_analysis

    def run_full_chain_pcr():
        from external import trendlyne_api
        while True:
            if not is_market_hours():
                time.sleep(300)
                continue

            for symbol in ['NIFTY', 'BANKNIFTY', 'FINNIFTY']:
                try:
                    expiry_str = current_expiries.get(symbol)

                    # 1. Attempt to fetch Golden PCR from Trendlyne
                    if expiry_str:
                        trendlyne_pcr = trendlyne_api.fetch_latest_pcr(symbol, expiry_str)
                        if trendlyne_pcr:
                            pcr = trendlyne_pcr.get('pcr')
                            logging.info(f"Golden PCR from Trendlyne for {symbol}: {pcr}")
                            emit_event('oi_update', {
                                'symbol': symbol,
                                'pcr': pcr,
                                'timestamp': datetime.now().isoformat(),
                                'put_oi': trendlyne_pcr.get('total_put_oi', 0),
                                'call_oi': trendlyne_pcr.get('total_call_oi', 0),
                                'source': 'trendlyne'
                            })
                            continue

                    # 2. Fallback to TradingView Option Chain Scanner
                    tv_res = process_option_chain_with_analysis(symbol, 'NSE', expiry_date='nearest')
                    if tv_res['success']:
                        total_ce_oi = sum(opt['oi'] for opt in tv_res['data'] if opt['type'] == 'call')
                        total_pe_oi = sum(opt['oi'] for opt in tv_res['data'] if opt['type'] == 'put')

                        if total_ce_oi > 0:
                            pcr = round(total_pe_oi / total_ce_oi, 2)
                            logging.info(f"TradingView Scanner PCR for {symbol}: {pcr}")
                            emit_event('oi_update', {
                                'symbol': symbol,
                                'pcr': pcr,
                                'timestamp': datetime.now().isoformat(),
                                'put_oi': total_pe_oi,
                                'call_oi': total_ce_oi,
                                'source': 'tradingview_scanner'
                            })
                except Exception as e:
                    logging.error(f"Error in full chain PCR for {symbol}: {e}")

            time.sleep(60)

    threading.Thread(target=run_full_chain_pcr, daemon=True).start()

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
    Starts the TradingView live feed for indices and options.
    """
    start_pcr_calculation_thread()
    from external.tv_feed import start_tv_feed
    start_tv_feed(on_message)

    # No longer using UpstoxFeed, so we don't need the monitor or keep-alive threads for it.
    # TradingView feed handles its own reconnection/polling.
    logger.info("TradingView Live Feed initialized.")

def load_intraday_data(instrument_key, date_str=None, timeframe_min=1, lookback_days=0):
    """
    Fetches and aggregates data for a specific date (defaults to today) from 9:15 AM to 3:30 PM.

    Args:
        instrument_key (str): The instrument key.
        date_str (str): Optional date in YYYY-MM-DD format.
        timeframe_min (int): Aggregation timeframe in minutes.
        lookback_days (int): Number of previous days to include for indicator warm-up.

    Returns:
        list: A list of aggregated OHLC/Footprint bars.
    """
    import pytz
    ist = pytz.timezone('Asia/Kolkata')

    if not date_str:
        now = datetime.now(ist)
        date_str = now.strftime("%Y-%m-%d")

    base_date = datetime.strptime(date_str, "%Y-%m-%d")
    start_date = base_date - timedelta(days=lookback_days)

    start_time = ist.localize(datetime.strptime(f"{start_date.strftime('%Y-%m-%d')} 09:15:00", "%Y-%m-%d %H:%M:%S"))
    end_time = ist.localize(datetime.strptime(f"{date_str} 15:30:00", "%Y-%m-%d %H:%M:%S"))

    start_ms = int(start_time.timestamp() * 1000)
    end_ms = int(end_time.timestamp() * 1000)

    # Query ticks within the date's market hours
    keys_to_search = [instrument_key]
    raw_key = symbol_mapper.resolve_to_key(instrument_key)
    if raw_key and raw_key not in keys_to_search:
        keys_to_search.append(raw_key)

    # DuckDB Optimized query
    keys_str = ", ".join([f"'{k}'" for k in keys_to_search])
    sql = f"""
        SELECT full_feed FROM ticks
        WHERE instrumentKey IN ({keys_str})
        AND ts_ms >= {start_ms} AND ts_ms <= {end_ms}
        ORDER BY ts_ms ASC
    """

    rows = db.query(sql)
    bars = []

    try:
        def collect_bar(event, data, room=None):
            if event == 'footprint_data':
                bars.append(data)

        replay = ReplayManager(emit_fn=collect_bar)
        replay.timeframe_sec = timeframe_min * 60
        for row in rows:
            doc = json.loads(row['full_feed'])
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

        sql = f"SELECT full_feed FROM ticks WHERE instrumentKey = ? ORDER BY ts_ms ASC"
        rows = db.query(sql, (instrument_key,))

        count = 0
        for row in rows:
            doc = json.loads(row['full_feed'])
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
