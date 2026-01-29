"""
ProTrade Integrated API Server
Handles REST endpoints, Socket.IO real-time streaming, and background strategy orchestration.
"""
import os
import asyncio
import logging
from logging.config import dictConfig
from typing import List, Dict, Any, Optional
import socketio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from config import LOGGING_CONFIG, ACCESS_TOKEN, INITIAL_INSTRUMENTS
from db.mongodb import (
    get_db,
    get_tick_data_collection,
    get_instruments_collection,
    get_oi_collection,
    get_trade_signals_collection,
    SIGNAL_COLLECTION_NAME
)
from core import data_engine
from core.replay_engine import ReplayEngine
from external import trendlyne_api as trendlyne_service
from external.upstox_api import UpstoxAPI
from core.strategies.candle_cross import CandleCrossStrategy, DataPersistor
try:
    from core.strategies.combined_signal import CombinedSignalEngine
except ImportError:
    CombinedSignalEngine = None
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import unquote

# Configure Logging
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes strategies and starts the Upstox WebSocket thread."""
    logger.info("Initializing ProTrade Platform...")

    # Capture main loop and inject into data_engine
    global main_loop
    try:
        main_loop = asyncio.get_running_loop()
    except RuntimeError:
        main_loop = asyncio.get_event_loop()

    data_engine.set_socketio(sio, loop=main_loop)
    logger.info("SocketIO injected into data_engine")

    # 1. Initialize Strategies
    all_instruments = INITIAL_INSTRUMENTS

    if CombinedSignalEngine:
        logger.info("Initializing CombinedSignalEngine...")
        class DummyWriter:
            def write(self, s): pass
        dummy_writer = DummyWriter()

        for key in all_instruments:
            logger.info(f"Initializing Combined Strategy for {key}...")
            strategy = CombinedSignalEngine(
                instrument_key=key,
                csv_writer=dummy_writer,
                obi_throttle_sec=1.0
            )
            data_engine.register_strategy(key, strategy)
        logger.info("CombinedSignalEngine initialized")

    if CandleCrossStrategy:
        logger.info("Initializing CandleCrossStrategy...")
        try:
            persistor_instance = DataPersistor()
            for key in all_instruments:
                logger.info(f"Initializing Candle Cross Strategy for {key}...")
                strategy = CandleCrossStrategy(
                    instrument_key=key,
                    csv_writer=None,
                    persistor=persistor_instance,
                    is_backtesting=False
                )
                data_engine.register_strategy(key, strategy)
            logger.info("CandleCrossStrategy initialized")
        except Exception as e:
            logger.error(f"Failed to initialize CandleCrossStrategy: {e}")

    # 2. Start WebSocket Feed
    if ACCESS_TOKEN and ACCESS_TOKEN != 'YOUR_ACCESS_TOKEN_HERE':
        logger.info("Starting Upstox WebSocket thread...")
        data_engine.start_websocket_thread(ACCESS_TOKEN, all_instruments)
    else:
        logger.warning("ACCESS_TOKEN not set. WebSocket feed will not start.")

    yield
    logger.info("Shutting down ProTrade Platform...")
    # Ensure remaining ticks are flushed to DB
    try:
        data_engine.flush_tick_buffer()
        logger.info("Tick buffer flushed to MongoDB.")
    except Exception as e:
        logger.error(f"Error flushing tick buffer during shutdown: {e}")

fastapi_app = FastAPI(title="ProTrade Integrated API", lifespan=lifespan)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# Initialize Upstox API
upstox_api = UpstoxAPI(ACCESS_TOKEN)

# Initialize Replay Engine
main_loop = None

def emit_replay(event, data, room=None):
    if main_loop:
        asyncio.run_coroutine_threadsafe(sio.emit(event, data, room=room), main_loop)
    else:
        logger.error("Main event loop not captured, cannot emit replay event")

replay_engine = ReplayEngine(emit_fn=emit_replay, db_dependencies={})

# Configure CORS
ALLOWED_ORIGINS = [
    "http://localhost:5000",
    "http://localhost:5051",
    "http://localhost:4200",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5000",
    "http://127.0.0.1:5051",
    "http://127.0.0.1:4200",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")

@sio.on('subscribe')
async def handle_subscribe(sid, data):
    """Handles multiple instrument subscriptions."""
    instrument_keys = data.get('instrumentKeys', [])
    logger.info(f"Client {sid} subscribing to {instrument_keys}")
    for key in instrument_keys:
        await handle_subscribe_instrument(sid, {'instrument_key': key})

@sio.on('subscribe_to_instrument')
async def handle_subscribe_instrument(sid, data):
    """Subscribe to a single instrument, join room, and send history."""
    instrument_key = data.get('instrument_key') if isinstance(data, dict) else data
    if not instrument_key:
        return

    logger.info(f"Client {sid} subscribing to instrument: {instrument_key}")
    sio.enter_room(sid, instrument_key)

    # Delegate to data_engine for Upstox subscription
    data_engine.subscribe_instrument(instrument_key)

    # Load and send intraday history
    history = data_engine.load_intraday_data(instrument_key)
    if history:
        await sio.emit('footprint_history', history, to=sid)

    # Send current active bar if exists
    if instrument_key in data_engine.active_bars:
        current_bar = data_engine.active_bars[instrument_key]
        if current_bar:
            await sio.emit('footprint_update', current_bar, to=sid)

@sio.on('start_replay')
async def handle_start_replay(sid, data):
    """Starts a full day synchronized replay."""
    date_str = data.get('date')
    instrument_keys = data.get('instrument_keys', INITIAL_INSTRUMENTS)
    speed = float(data.get('speed', 1.0))

    logger.info(f"Full replay requested for {date_str} by {sid}")
    replay_engine.start_replay(date_str, instrument_keys, speed)

@sio.on('stop_replay')
async def handle_stop_replay(sid, data):
    """Stops active replay."""
    logger.info(f"Stop replay requested by {sid}")
    replay_engine.stop_replay()

@sio.on('pause_replay')
async def handle_pause_replay(sid, data):
    replay_engine.pause_replay()

@sio.on('resume_replay')
async def handle_resume_replay(sid, data):
    replay_engine.resume_replay()

@sio.on('set_replay_speed')
async def handle_set_speed(sid, data):
    speed = float(data.get('speed', 1.0))
    replay_engine.set_speed(speed)

@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ProTrade API"}

def get_live_report_data() -> Dict[str, Any]:
    """
    Queries MongoDB for all trade signals generated today and aggregates them into a report.

    Returns:
        Dict[str, Any]: A dictionary containing total P&L, open positions, completed trades, and summary.
    """
    db = get_db()
    if db is None:
        return {"error": "Database not connected."}

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    signals = list(db[SIGNAL_COLLECTION_NAME].find({
        "timestamp": {"$gte": today.timestamp()}
    }).sort("timestamp", 1))

    trades = defaultdict(lambda: {
        'status': 'OPEN',
        'entry_time': None,
        'entry_timestamp': 0,
        'exit_timestamp': 0,
        'instrument': None,
        'instrument_name': None,
        'pnl': 0,
        'entry_price': 0,
        'exit_price': 0,
        'quantity': 50,
        'side': '',
        'stop_loss': 0,
        'take_profit': 0,
        'strategy': ''
    })
    total_pnl = 0
    instr_coll = get_instruments_collection()

    for signal in signals:
        trade_id = signal.get('trade_id')
        instrument = signal.get('instrumentKey') or signal.get('instrument_key') or signal.get('instrument')

        instrument_name = instrument
        if instrument:
            doc = instr_coll.find_one({'instrument_key': instrument})
            if doc:
                instrument_name = doc.get('trading_symbol') or doc.get('underlying_symbol') or instrument

        if signal['type'] == 'ENTRY':
            position = signal.get('position_after', signal.get('signal', 'UNKNOWN'))
            side = 'LONG' if position == 'BUY' else 'SHORT' if position == 'SELL' else position

            ts_val = signal.get('timestamp', 0)
            entry_time = datetime.fromtimestamp(ts_val/1000).strftime('%Y-%m-%d %H:%M:%S') if ts_val else "N/A"

            trades[trade_id].update({
                'status': 'OPEN',
                'entry_time': entry_time,
                'entry_timestamp': int(ts_val),
                'instrument': instrument,
                'instrument_name': instrument_name,
                'entry_price': signal.get('ltp', 0),
                'quantity': signal.get('quantity', 50),
                'side': side,
                'stop_loss': signal.get('sl_price', 0),
                'take_profit': signal.get('tp_price', 0),
                'strategy': signal.get('strategy', 'UNKNOWN')
            })

        elif signal['type'] == 'EXIT':
            pnl = signal.get('pnl', 0)
            trades[trade_id]['status'] = 'COMPLETED'
            ts_val = signal.get('timestamp', 0)
            trades[trade_id]['exit_time'] = datetime.fromtimestamp(ts_val/1000).strftime('%Y-%m-%d %H:%M:%S') if ts_val else "N/A"
            trades[trade_id]['exit_timestamp'] = int(ts_val)
            trades[trade_id]['pnl'] = pnl
            trades[trade_id]['exit_price'] = signal.get('exit_price', signal.get('ltp', 0))
            trades[trade_id]['reason'] = signal.get('reason_code', 'EXIT')
            if not trades[trade_id]['instrument_name']:
                trades[trade_id]['instrument_name'] = instrument_name
            total_pnl += pnl

    open_positions = []
    completed_trades = []

    for trade_id, trade_data in trades.items():
        if trade_data['status'] == 'OPEN':
            open_positions.append({'id': trade_id, **trade_data})
        elif trade_data['status'] == 'COMPLETED':
            completed_trades.append({'id': trade_id, **trade_data})

    summary = defaultdict(lambda: {'trades': 0, 'pnl': 0})
    for trade in completed_trades:
        summary[trade['instrument']]['trades'] += 1
        summary[trade['instrument']]['pnl'] += trade['pnl']

    trade_summary = [{'instrument': k, 'trades': v['trades'], 'net_pnl': v['pnl']} for k, v in summary.items()]

    return {
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "total_pnl": round(total_pnl, 2),
        "open_positions": open_positions,
        "completed_trades": completed_trades,
        "trade_summary": trade_summary
    }

@fastapi_app.get("/api/live_pnl", response_model=Dict[str, Any])
async def live_pnl_api():
    """
    API endpoint to retrieve the latest P&L and trade signals summary.
    """
    data = get_live_report_data()
    if "error" in data:
        raise HTTPException(status_code=500, detail=data["error"])
    return data

@fastapi_app.get("/api/trade_signals/{instrument_key}")
async def get_trade_signals(instrument_key: str):
    """Queries MongoDB for trade signals for a specific instrument."""
    try:
        clean_key = unquote(instrument_key)
        db = get_db()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        prior_date = today - timedelta(days=1)
        timestamp = int(prior_date.timestamp())

        query = {
            "instrumentKey": clean_key,
            "timestamp": {"$gte": timestamp}
        }

        cursor = db[SIGNAL_COLLECTION_NAME].find(query).sort("timestamp", 1)
        signals_data = []
        ist_offset_seconds = 19800 # 5h 30m

        for doc in cursor:
            ts = doc.get('timestamp', 0)
            unix_time = int(ts / 1000) + ist_offset_seconds if ts else 0

            signal_entry = {
                "time": unix_time,
                "trade_id": doc.get('trade_id'),
                "signal": doc.get('signal'),
                "type": doc.get('type'),
                "price": float(doc.get('ltp', 0)) if doc.get('type') == 'ENTRY' else float(doc.get('exit_price', 0)),
                "sl_price": float(doc.get('sl_price', 0)),
                "tp_price": float(doc.get('tp_price', 0)),
                "reason": doc.get('reason', doc.get('reason_code', ""))
            }
            signals_data.append(signal_entry)

        return signals_data
    except Exception as e:
        logger.error(f"Error fetching trade signals: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/oi_data/{instrument_key}")
async def get_oi_data_route(instrument_key: str):
    """Return latest OI data for the given instrument."""
    try:
        instruments_coll = get_instruments_collection()
        oi_coll = get_oi_collection()
        instrument = instruments_coll.find_one({'instrument_key': instrument_key})
        if not instrument:
            raise HTTPException(status_code=404, detail="Instrument not found")

        symbol = instrument.get('trading_symbol') or instrument.get('underlying_symbol')
        if not symbol:
            raise HTTPException(status_code=404, detail="Symbol not found for instrument")

        oi_doc = oi_coll.find_one({'symbol': symbol}, sort=[('date', -1), ('timestamp', -1)])
        if not oi_doc:
            raise HTTPException(status_code=404, detail="OI data not found")

        return {
            'open_interest': oi_doc.get('call_oi', 0),
            'oi_change': oi_doc.get('change_in_call_oi', 0)
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching OI data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch OI data")

@fastapi_app.post("/api/backfill/trendlyne", response_model=Dict[str, Any])
async def trigger_trendlyne_backfill(symbol: str = Query("NIFTY", description="The trading symbol to backfill (e.g., NIFTY, BANKNIFTY)")):
    """
    Triggers a historical Open Interest (OI) data backfill from the Trendlyne SmartOptions API.
    """
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    try:
        logger.info(f"Triggering Trendlyne backfill for {symbol}")
        result = trendlyne_service.perform_backfill(symbol)
        if result.get("status") == "success":
            return result
        else:
            message = result.get("message", "Unknown error during backfill")
            logger.error(f"Trendlyne backfill failed: {message}")
            raise HTTPException(status_code=500, detail=message)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Trendlyne backfill error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@fastapi_app.get("/api/upstox/intraday/{instrument_key}")
async def get_upstox_intraday(instrument_key: str):
    """Fetch intraday candles from DB backfill or Upstox V3."""
    try:
        clean_key = unquote(instrument_key)

        # 1. Try backfill from MongoDB via data_engine
        db_history = data_engine.load_intraday_data(clean_key)
        if db_history and len(db_history) > 10: # If we have significant data in DB
            # Convert footprint bars to OHLC format expected by UI
            candles = []
            for bar in db_history:
                candles.append([
                    datetime.fromtimestamp(bar['ts']/1000).isoformat(),
                    bar['open'], bar['high'], bar['low'], bar['close'], bar['volume'], 0
                ])
            return {"candles": candles}

        # 2. Fallback to Upstox API
        data = upstox_api.get_intraday_candles(clean_key)
        if data and data.get('status') == 'success':
            return data.get('data', {})

        # 3. Last effort: return empty if everything fails
        return {"candles": []}
    except Exception as e:
        logger.error(f"Error in get_upstox_intraday for {instrument_key}: {e}")
        return {"candles": []}

@fastapi_app.get("/api/upstox/option_chain/{instrument_key}/{expiry_date}")
async def get_upstox_option_chain(instrument_key: str, expiry_date: str):
    """Fetch option chain from Upstox V2."""
    try:
        clean_key = unquote(instrument_key)
        data = upstox_api.get_option_chain(clean_key, expiry_date)
        if data and data.get('status') == 'success':
            return data.get('data', [])
        raise HTTPException(status_code=500, detail="Failed to fetch option chain")
    except Exception as e:
        logger.error(f"Error in get_upstox_option_chain: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/trendlyne/expiry/{symbol}")
async def get_trendlyne_expiry(symbol: str):
    """Fetch expiry dates from Trendlyne."""
    try:
        stock_id = trendlyne_service.get_stock_id_for_symbol(symbol)
        if not stock_id:
            raise HTTPException(status_code=404, detail=f"Stock ID not found for {symbol}")

        dates = trendlyne_service.get_expiry_dates(stock_id)
        # Format labels like frontend does
        formatted_dates = []
        for i, date_str in enumerate(dates):
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                day = d.day
                month = d.strftime('%b').lower()
                year = d.year
                suffix = 'near' if i == 0 else 'next' if i == 1 else 'far'
                label = f"{day}-{month}-{year}-{suffix}"
                formatted_dates.append({"date": date_str, "label": label})
            except:
                formatted_dates.append({"date": date_str, "label": date_str})

        return formatted_dates
    except Exception as e:
        logger.error(f"Error in get_trendlyne_expiry: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/trendlyne/buildup/futures/{symbol}/{expiry}")
async def get_trendlyne_futures_buildup(symbol: str, expiry: str):
    """Fetch futures buildup from Trendlyne."""
    try:
        data = trendlyne_service.fetch_futures_buildup(symbol, expiry)
        return data
    except Exception as e:
        logger.error(f"Error in get_trendlyne_futures_buildup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/trendlyne/buildup/options/{symbol}/{expiry}/{strike}/{option_type}")
async def get_trendlyne_option_buildup(symbol: str, expiry: str, strike: int, option_type: str):
    """Fetch option buildup from Trendlyne."""
    try:
        data = trendlyne_service.fetch_option_buildup(symbol, expiry, strike, option_type)
        return data
    except Exception as e:
        logger.error(f"Error in get_trendlyne_option_buildup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/analytics/pcr/{symbol}")
async def get_historical_pcr(symbol: str):
    """Fetch historical PCR and Spot data for analytics."""
    try:
        oi_coll = get_oi_collection()
        # Fetch today's OI data
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor = oi_coll.find({
            'symbol': symbol,
            'date': today_str
        }).sort('timestamp', 1)

        results = []
        for doc in cursor:
            call_oi = doc.get('call_oi', 0)
            put_oi = doc.get('put_oi', 0)
            pcr = round(put_oi / call_oi, 2) if call_oi > 0 else 0

            results.append({
                'timestamp': f"{doc['date']}T{doc['timestamp']}:00",
                'pcr': pcr,
                'call_oi': call_oi,
                'put_oi': put_oi
            })

        return results
    except Exception as e:
        logger.error(f"Error in get_historical_pcr: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/replay/dates")
async def get_replay_dates():
    """Returns a list of dates that have tick data available for replay."""
    try:
        tick_coll = get_tick_data_collection()
        # This might be slow if we have many ticks.
        # In a real app we'd have a 'sessions' collection.
        # Let's try to get distinct dates from the Insertion time or similar.
        # For now, let's look at OI data which is grouped by date.
        oi_coll = get_oi_collection()
        dates = oi_coll.distinct('date')
        return sorted(dates, reverse=True)
    except Exception as e:
        logger.error(f"Error fetching replay dates: {e}")
        return []

@fastapi_app.get("/api/instruments")
async def get_instruments():
    """Return list of instrument keys with human readable names."""
    try:
        collection = get_tick_data_collection()
        instrument_keys = collection.distinct('instrumentKey')
        instruments = []
        instr_master = get_instruments_collection()

        for key in instrument_keys:
            instr_doc = instr_master.find_one({'instrument_key': key})
            name = key
            if instr_doc:
                name = instr_doc.get('trading_symbol') or instr_doc.get('underlying_symbol') or key
            instruments.append({'key': key, 'name': name})
        return instruments
    except Exception as e:
        logger.error(f"Error fetching instruments: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch instruments")

# Static Files (Serving Frontend Build)
frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/angular-ui/dist/angular-ui/browser"))
if not os.path.exists(frontend_dist):
    frontend_dist = os.path.abspath(os.path.join(os.path.dirname(__file__), "../frontend/dist"))

if os.path.exists(frontend_dist):
    fastapi_app.mount("/static", StaticFiles(directory=frontend_dist), name="static")
    logger.info(f"Mounted static files from {frontend_dist}")

    @fastapi_app.get("/")
    async def serve_index():
        return FileResponse(os.path.join(frontend_dist, "index.html"))

    @fastapi_app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Explicitly ignore API and Socket.IO paths to avoid intercepting them
        if full_path.startswith("api/") or full_path.startswith("socket.io") or full_path.startswith("docs") or full_path.startswith("openapi.json"):
            raise HTTPException(status_code=404)

        # Check if the file exists in the static directory
        file_path = os.path.join(frontend_dist, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        # Otherwise serve index.html for SPA routing
        return FileResponse(os.path.join(frontend_dist, "index.html"))
else:
    logger.warning(f"Frontend dist directory not found at {frontend_dist}")

# Final Wrap with Socket.io
app = socketio.ASGIApp(sio, fastapi_app)
data_engine.set_socketio(sio)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=5051, reload=False)
