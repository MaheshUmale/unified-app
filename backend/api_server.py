"""
ProTrade Integrated API Server
Handles REST endpoints, Socket.IO real-time streaming, and background strategy orchestration.
"""
import os
import json
import asyncio
import logging
from logging.config import dictConfig
from typing import List, Dict, Any, Optional
import socketio # python-socketio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from config import LOGGING_CONFIG, INITIAL_INSTRUMENTS
from db.local_db import db
from core import data_engine
from core.symbol_mapper import symbol_mapper
from core.replay_engine import ReplayEngine
from core.backfill_manager import BackfillManager
from external import trendlyne_api as trendlyne_service
from external.tv_api import tv_api
from core.strategies.candle_cross import CandleCrossStrategy, DataPersistor
from core.strategies.atm_buying_strategy import ATMOptionBuyingStrategy
from collections import defaultdict
from datetime import datetime, timedelta
from urllib.parse import unquote

# Configure Logging
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes strategies and starts the TradingView WebSocket thread."""
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

    if CandleCrossStrategy:
        logger.info("Initializing CandleCrossStrategy...")
        try:
            persistor_instance = DataPersistor()
            for key in all_instruments:
                hrn = symbol_mapper.get_hrn(key)
                logger.info(f"Initializing Candle Cross Strategy for {hrn} ({key})...")
                strategy = CandleCrossStrategy(
                    instrument_key=hrn,
                    csv_writer=None,
                    persistor=persistor_instance,
                    is_backtesting=False
                )
                data_engine.register_strategy(hrn, strategy)
            logger.info("CandleCrossStrategy initialized")
        except Exception as e:
            logger.error(f"Failed to initialize CandleCrossStrategy: {e}")

    # 2. Start WebSocket Feed
    logger.info("Starting TradingView WebSocket thread...")
    data_engine.start_websocket_thread(None, all_instruments)

    yield
    logger.info("Shutting down ProTrade Platform...")
    # Ensure remaining ticks are flushed to DB
    try:
        data_engine.flush_tick_buffer()
        logger.info("Tick buffers flushed to LocalDB.")
    except Exception as e:
        logger.error(f"Error flushing tick buffers during shutdown: {e}")

fastapi_app = FastAPI(title="ProTrade Integrated API", lifespan=lifespan)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')

# Initialize Strategy Engines
atm_strategy = ATMOptionBuyingStrategy()

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
    logger.info(f"Client {sid} subscribing to {len(instrument_keys)} instruments: {instrument_keys}")
    for key in instrument_keys:
        try:
            await handle_subscribe_instrument(sid, {'instrument_key': key})
        except ValueError as e:
            if "sid is not connected" in str(e):
                logger.warning(f"Client {sid} disconnected during bulk subscription")
                break
            raise

@sio.on('subscribe_to_instrument')
async def handle_subscribe_instrument(sid, data):
    """Subscribe to a single instrument, join room, and send history."""
    instrument_key = data.get('instrument_key') if isinstance(data, dict) else data
    if not instrument_key:
        return

    logger.info(f"Client {sid} subscribing to instrument: {instrument_key}")
    # Acknowledge subscription
    await sio.emit('subscription_status', {'key': instrument_key, 'status': 'success'}, to=sid)

    try:
        await sio.enter_room(sid, instrument_key)
    except ValueError as e:
        if "sid is not connected" in str(e):
            logger.warning(f"Client {sid} disconnected before entering room {instrument_key}")
            return
        raise

    # Delegate to data_engine for Upstox subscription
    data_engine.subscribe_instrument(instrument_key)

    # Load and send intraday history (Offload heavy DB query to thread to prevent event loop lag)
    history = await asyncio.to_thread(data_engine.load_intraday_data, instrument_key)
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

@fastapi_app.get("/api/tv/search")
async def tv_search(text: str = Query(..., min_length=1)):
    """Proxies TradingView symbol search requests using async httpx."""
    import httpx
    url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={text}&hl=1&exchange=&lang=en&search_type=undefined&domain=production&sort_by_country=IN&promo=true"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json, text/plain, */*',
        'Referer': 'https://in.tradingview.com/',
        'Origin': 'https://in.tradingview.com'
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.error(f"TradingView search proxy error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch search results from TradingView")

def get_live_report_data() -> Dict[str, Any]:
    """
    Queries LocalDB for all trade signals generated today and aggregates them into a report.

    Returns:
        Dict[str, Any]: A dictionary containing total P&L, open positions, completed trades, and summary.
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    today_ts = int(today.timestamp() * 1000)

    sql = "SELECT * FROM trade_signals WHERE timestamp >= ? ORDER BY timestamp ASC"
    signals = db.query(sql, (today_ts,))

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

    for signal in signals:
        trade_id = signal.get('trade_id')
        instrument = signal.get('instrumentKey') or signal.get('instrument_key') or signal.get('instrument')

        instrument_name = instrument
        if instrument:
            res = db.get_metadata(instrument)
            if res:
                instrument_name = res.get('hrn') or instrument

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

@fastapi_app.get("/api/strategy/atm-buying")
async def get_atm_strategy_analysis(index_key: str, atm_strike: int, expiry: str):
    """Triggers and returns the ATM Option Buying Strategy analysis."""
    try:
        clean_key = unquote(index_key)
        symbol = symbol_mapper.get_symbol(clean_key)
        if symbol == "UNKNOWN":
            symbol = "NIFTY" # Default fallback

        # 1. Fetch current data
        market_data = atm_strategy.fetch_market_data(symbol, clean_key, atm_strike, expiry)
        if not market_data:
            print(f"Failed to fetch market data for {symbol} {clean_key} {atm_strike} {expiry}")
            return {"error": "Could not fetch required market data for ATM strikes"}

        # 2. Analyze
        results = atm_strategy.analyze(symbol, market_data)
        return results
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error in get_atm_strategy_analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.post("/api/strategy/context")
async def update_strategy_context(data: Dict[str, str]):
    """Updates manual context for the strategy."""
    symbol = data.get('symbol', 'NIFTY')
    global_cues = data.get('global_cues', 'Neutral')
    major_events = data.get('major_events', 'None')
    atm_strategy.set_context(symbol, global_cues, major_events)
    return {"status": "success"}

@fastapi_app.get("/api/strategy/search-cues")
async def search_market_cues():
    """Returns placeholder market cues."""
    return {
        "global_cues": "US Markets: Neutral | Gift Nifty: Slightly Positive (+20 pts) | Crude Oil: Stable",
        "major_events": "RBI Monetary Policy Meeting today at 10:00 AM | Reliance Industries Results later today"
    }


@fastapi_app.get("/api/trade_signals/{instrument_key}")
async def get_trade_signals(instrument_key: str):
    """Queries LocalDB for trade signals for a specific instrument."""
    try:
        clean_key = unquote(instrument_key)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        prior_date = today - timedelta(days=1)
        timestamp = int(prior_date.timestamp() * 1000)

        sql = "SELECT * FROM trade_signals WHERE instrumentKey = ? AND timestamp >= ? ORDER BY timestamp ASC"
        rows = db.query(sql, (clean_key, timestamp))

        signals_data = []
        ist_offset_seconds = 19800 # 5h 30m

        for doc in rows:
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
        res = db.get_metadata(instrument_key)
        if not res:
            raise HTTPException(status_code=404, detail="Instrument not found")

        symbol = symbol_mapper.get_symbol(instrument_key)

        sql = "SELECT * FROM oi_data WHERE symbol = ? ORDER BY date DESC, timestamp DESC LIMIT 1"
        rows = db.query(sql, (symbol,))
        if not rows:
            raise HTTPException(status_code=404, detail="OI data not found")

        oi_doc = rows[0]
        return {
            'open_interest': oi_doc.get('call_oi', 0),
            'oi_change': 0 # Needs historical comparison for change
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching OI data: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch OI data")

@fastapi_app.post("/api/cleanup/oi", response_model=Dict[str, Any])
async def trigger_oi_cleanup(symbol: Optional[str] = None):
    """
    Manually triggers cleanup of potentially incorrect OI data for today.
    """
    try:
        from core.cleanup_db import cleanup_oi_data
        cleanup_oi_data(symbol=symbol)
        return {"status": "success", "message": "Cleanup completed successfully"}
    except Exception as e:
        logger.error(f"Manual cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.post("/api/backfill/session", response_model=Dict[str, Any])
async def trigger_session_backfill():
    """
    Triggers a full recovery of today's market session data (Price, OI, PCR).
    """
    try:
        logger.info("Manual session backfill triggered")
        manager = BackfillManager()
        result = await manager.backfill_today_session()
        if result.get("status") == "success":
            return result
        else:
            raise HTTPException(status_code=500, detail=result.get("message", "Backfill failed"))
    except Exception as e:
        logger.error(f"Session backfill API error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.post("/api/backfill/trendlyne", response_model=Dict[str, Any])
async def trigger_trendlyne_backfill(
    symbol: str = Query("NIFTY", description="The trading symbol to backfill (e.g., NIFTY, BANKNIFTY)"),
    interval: int = Query(5, description="Interval in minutes (e.g., 5, 15)")
):
    """
    Triggers a historical Open Interest (OI) data backfill from the Trendlyne SmartOptions API.
    """
    if not symbol:
        raise HTTPException(status_code=400, detail="Symbol is required")

    try:
        logger.info(f"Triggering Trendlyne backfill for {symbol} at {interval}min interval")
        result = trendlyne_service.perform_backfill(symbol, interval_minutes=interval)
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
async def get_upstox_intraday(instrument_key: str, date: Optional[str] = None, interval: str = '1'):
    """Fetch intraday candles from DB backfill or TradingView. instrument_key can be HRN."""
    try:
        clean_key = unquote(instrument_key)
        raw_key = symbol_mapper.resolve_to_key(clean_key) or clean_key

        # 0. Priority: TradingView for Index and Option Symbols
        if not date:
            # We pass the HRN to TV API which handles mapping
            tv_candles = await asyncio.to_thread(tv_api.get_hist_candles, clean_key, interval, 1000)
            if tv_candles:
                logger.info(f"Using TradingView history for {clean_key}")
                return {"candles": tv_candles}

        # 1. Try backfill from LocalDB via data_engine (uses HRN)
        # In live mode (date is None), fetch 2 extra days for indicator warm-up
        lookback = 3 if not date else 0 # 3 calendar days to safely cover 2 trading days
        db_history = data_engine.load_intraday_data(clean_key, date_str=date, timeframe_min=int(interval), lookback_days=lookback)

        if db_history and len(db_history) > (10 if not date else 5): # If we have significant data in DB
            # Convert footprint bars to OHLC format expected by UI
            candles = []
            for bar in db_history:
                candles.append([
                    datetime.fromtimestamp(bar['ts']/1000).isoformat(),
                    bar['open'], bar['high'], bar['low'], bar['close'], bar['volume'], bar.get('oi', 0)
                ])
            # Reverse to match Upstox V3 descending order (newest first)
            return {"candles": candles[::-1]}

        # 2. Last effort: return empty if everything fails
        return {"candles": []}
    except Exception as e:
        logger.error(f"Error in get_upstox_intraday for {instrument_key}: {e}")
        return {"candles": []}

@fastapi_app.get("/api/upstox/option_chain/{instrument_key}/{expiry_date}")
async def get_upstox_option_chain(instrument_key: str, expiry_date: str):
    """Fetch option chain from TradingView. instrument_key can be HRN."""
    try:
        from external.tv_mcp import process_option_chain_with_analysis
        clean_key = unquote(instrument_key)
        symbol = symbol_mapper.get_symbol(clean_key)
        if symbol == "UNKNOWN": symbol = clean_key

        # expiry_date might be in YYYY-MM-DD format from UI, TradingView wants YYYYMMDD
        tv_expiry = expiry_date.replace('-', '')

        res = process_option_chain_with_analysis(symbol, 'NSE', expiry_date=tv_expiry)
        if res['success']:
            chain_data = []
            # Group by strike for UI compatibility
            strikes = defaultdict(lambda: {'strike_price': 0, 'call_options': None, 'put_options': None})
            for opt in res['data']:
                strike = opt['strike']
                strikes[strike]['strike_price'] = strike

                # Construct HRN
                expiry_dt = datetime.strptime(str(res['target_expiry']), '%Y%m%d')
                expiry_str = expiry_dt.strftime('%d %b %Y').upper()
                hrn = f"{symbol} {expiry_str} {opt['type'].upper()} {int(strike)}"

                side = 'call_options' if opt['type'] == 'call' else 'put_options'
                strikes[strike][side] = {
                    'instrument_key': hrn,
                    'market_data': {
                        'oi': opt['oi'],
                        'ltp': opt['close'],
                        'iv': opt['iv'],
                        'greeks': {
                            'delta': opt['delta'],
                            'gamma': opt['gamma'],
                            'theta': opt['theta'],
                            'vega': opt['vega']
                        }
                    }
                }
            return sorted(list(strikes.values()), key=lambda x: x['strike_price'])
        raise HTTPException(status_code=500, detail="Failed to fetch option chain from TradingView")
    except Exception as e:
        logger.error(f"Error in get_upstox_option_chain: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/trendlyne/expiry/{symbol}")
async def get_trendlyne_expiry(symbol: str):
    """Fetch expiry dates from Trendlyne."""
    try:
        clean_key = unquote(symbol)
        hrn_symbol = symbol_mapper.get_symbol(clean_key)
        if hrn_symbol == "UNKNOWN":
            hrn_symbol = clean_key.split(':')[-1] if ':' in clean_key else clean_key

        logger.info(f"Fetching Trendlyne expiry for symbol: {hrn_symbol}")
        stock_id = trendlyne_service.get_stock_id_for_symbol(hrn_symbol)
        if not stock_id:
            logger.warning(f"Stock ID not found for {symbol}")
            return []

        dates = trendlyne_service.get_expiry_dates(stock_id)

        # User Requirement: BANKNIFTY should prioritize Monthly
        if symbol == 'BANKNIFTY':
            try:
                # Basic monthly heuristic: last 7 days of the month
                def is_monthly(d):
                    next_month = d.replace(day=28) + timedelta(days=4)
                    last_day = next_month - timedelta(days=next_month.day)
                    return (last_day - d).days < 7

                dt_dates = sorted([datetime.strptime(d, "%Y-%m-%d") for d in dates])
                monthly_dates = [d.strftime("%Y-%m-%d") for d in dt_dates if is_monthly(d)]
                # Move monthly dates to the front
                other_dates = [d for d in dates if d not in monthly_dates]
                dates = monthly_dates + other_dates
            except Exception as e:
                logger.error(f"Error prioritizing monthly BankNifty expiries: {e}")

        # Format labels like frontend does
        formatted_dates = []
        for i, date_str in enumerate(dates):
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d")
                day = d.day
                month = d.strftime('%b').lower()
                year = d.year
                # Re-calculate suffix based on new order
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
async def get_historical_pcr(symbol: str, date: Optional[str] = None):
    """Fetch historical PCR and Spot data for analytics."""
    try:
        clean_key = unquote(symbol)
        hrn_symbol = symbol_mapper.get_symbol(clean_key)

        # Fetch today's OI data
        today_str = date or datetime.now().strftime("%Y-%m-%d")

        sql = "SELECT CAST(date AS VARCHAR) as date_str, timestamp, call_oi, put_oi, price, source FROM oi_data WHERE symbol = ? AND date = ? ORDER BY timestamp ASC"
        rows = db.query(sql, (hrn_symbol, today_str))

        results_map = {}
        for doc in rows:
            ts = f"{doc['date_str']}T{doc['timestamp']}:00"
            call_oi = doc.get('call_oi', 0)
            put_oi = doc.get('put_oi', 0)
            pcr = round(put_oi / call_oi, 2) if call_oi > 0 else 0
            price = doc.get('price', 0)
            source = doc.get('source', 'unknown')

            if ts not in results_map or source in ['trendlyne', 'trendlyne_backfill']:
                results_map[ts] = {
                    'timestamp': ts,
                    'pcr': pcr,
                    'call_oi': call_oi,
                    'put_oi': put_oi,
                    'price': price
                }

        results = sorted(results_map.values(), key=lambda x: x['timestamp'])

        # If no data for today, try getting last 10 points and trigger a backfill
        if not results:
            # Trigger Trendlyne backfill in background
            logger.info(f"No PCR data for {hrn_symbol} today. Triggering Trendlyne backfill...")
            import threading
            threading.Thread(target=trendlyne_service.perform_backfill, args=(hrn_symbol,), kwargs={'interval_minutes': 5}, daemon=True).start()

            fallback_sql = "SELECT CAST(date AS VARCHAR) as date_str, timestamp, call_oi, put_oi, price FROM oi_data WHERE symbol = ? ORDER BY date DESC, timestamp DESC LIMIT 10"
            fallback_rows = db.query(fallback_sql, (hrn_symbol,))
            for doc in fallback_rows[::-1]:
                call_oi = doc.get('call_oi', 0)
                put_oi = doc.get('put_oi', 0)
                pcr = round(put_oi / call_oi, 2) if call_oi > 0 else 0
                results.append({
                    'timestamp': f"{doc['date_str']}T{doc['timestamp']}:00",
                    'pcr': pcr,
                    'call_oi': call_oi,
                    'put_oi': put_oi,
                    'price': doc.get('price', 0)
                })

        return results
    except Exception as e:
        logger.error(f"Error in get_historical_pcr: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.get("/api/replay/dates")
async def get_replay_dates():
    """Returns a list of dates that have tick data available for replay."""
    try:
        rows = db.query("SELECT DISTINCT CAST(date AS VARCHAR) as d FROM ticks ORDER BY d DESC")
        return [r['d'] for r in rows]
    except Exception as e:
        logger.error(f"Error fetching replay dates: {e}")
        return []

@fastapi_app.get("/api/replay/session_info/{date}/{index_key}")
async def get_replay_session_info(date: str, index_key: str):
    """Discovers the initial state and available instruments for a historical date."""
    try:
        clean_key = unquote(index_key)

        # 1. Find the first index tick for this date to get starting price
        sql = "SELECT full_feed FROM ticks WHERE instrumentKey = ? AND CAST(date AS VARCHAR) = ? ORDER BY ts_ms ASC LIMIT 1"
        rows = db.query(sql, (clean_key, date))

        if not rows:
            return {"error": "No index data found for this date"}

        first_tick = json.loads(rows[0]['full_feed'])
        ff = first_tick.get('fullFeed', {}).get('indexFF', {})
        start_price = float(ff.get('ltpc', {}).get('ltp', 0))

        # 2. Get all recorded keys for this date
        all_keys_rows = db.query("SELECT DISTINCT instrumentKey FROM ticks WHERE CAST(date AS VARCHAR) = ?", (date,))
        all_keys = [r['instrumentKey'] for r in all_keys_rows]
        logger.info(f"Discovered {len(all_keys)} keys for date {date}: {all_keys}")

        # 3. Identify closest CE and PE recorded on that day
        step = 50 if "NIFTY" in clean_key.upper() else 100
        atm = round(start_price / step) * step

        # Find matching keys from the recorded list
        suggested_ce = None
        suggested_pe = None
        expiry = None

        for key in all_keys:
            if clean_key == key: continue

            res = db.get_metadata(key)
            if not res: continue
            meta = res['metadata']

            if meta.get('type') == 'CE' and meta.get('strike') == atm:
                suggested_ce = res['hrn']
                expiry = meta.get('expiry')
            elif meta.get('type') == 'PE' and meta.get('strike') == atm:
                suggested_pe = res['hrn']
                if not expiry: expiry = meta.get('expiry')

        # Convert all_keys to HRNs
        hrn_keys = []
        for k in all_keys:
             hrn_keys.append(symbol_mapper.get_hrn(k))

        return {
            "date": date,
            "start_price": start_price,
            "atm": atm,
            "expiry": expiry,
            "suggested_ce": suggested_ce,
            "suggested_pe": suggested_pe,
            "available_keys": hrn_keys
        }
    except Exception as e:
        logger.error(f"Error in get_replay_session_info: {e}")
        return {"error": str(e)}

@fastapi_app.get("/api/instruments")
async def get_instruments():
    """Return list of instrument keys with human readable names."""
    try:
        rows = db.query("SELECT DISTINCT instrumentKey FROM ticks")
        instruments = []

        for r in rows:
            key = r['instrumentKey']
            instruments.append({'key': key, 'name': key})
        return instruments
    except Exception as e:
        logger.error(f"Error fetching instruments: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch instruments")

# Template and Static Files Setup
templates = Jinja2Templates(directory="backend/templates")
fastapi_app.mount("/static", StaticFiles(directory="backend/static"), name="static")

@fastapi_app.get("/")
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Final Wrap with Socket.io
app = socketio.ASGIApp(sio, fastapi_app)
# Do NOT call set_socketio(sio) here as it will overwrite the loop-aware injection in lifespan()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=5051, reload=False)
