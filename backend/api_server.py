"""
ProTrade Simplified API Server
Handles essential REST endpoints and Socket.IO real-time streaming for the charting terminal.
"""
import os
import asyncio
import logging
from logging.config import dictConfig
from typing import Any, Optional
import socketio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from config import LOGGING_CONFIG, INITIAL_INSTRUMENTS
from core import data_engine
from core.symbol_mapper import symbol_mapper
from external.tv_api import tv_api
from external.tv_scanner import search_options
from db.local_db import db
from datetime import datetime
from urllib.parse import unquote

# Configure Logging
dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Starts the TradingView WebSocket feed on startup."""
    logger.info("Initializing Simplified ProTrade Terminal...")

    global main_loop
    try:
        main_loop = asyncio.get_running_loop()
    except RuntimeError:
        main_loop = asyncio.get_event_loop()

    data_engine.set_socketio(sio, loop=main_loop)

    # Start WebSocket Feed
    logger.info("Starting TradingView WebSocket thread...")
    data_engine.start_websocket_thread(None, INITIAL_INSTRUMENTS)

    yield
    logger.info("Shutting down ProTrade Terminal...")
    try:
        data_engine.flush_tick_buffer()
    except Exception as e:
        logger.error(f"Error flushing tick buffers: {e}")

fastapi_app = FastAPI(title="ProTrade API", lifespan=lifespan)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', ping_timeout=60, ping_interval=25)
main_loop = None

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@sio.event
async def connect(sid, environ):
    logger.info(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    data_engine.handle_disconnect(sid)

@sio.on('subscribe')
async def handle_subscribe(sid, data):
    instrument_keys = data.get('instrumentKeys', [])
    interval = data.get('interval', '1')
    for key in instrument_keys:
        # HRN is used as the room name, derived from technical key
        hrn = symbol_mapper.get_hrn(key)
        logger.info(f"Client {sid} subscribing to: {key} ({interval}m) (Room: {hrn})")
        try:
            await sio.enter_room(sid, hrn)
            # Ensure the technical key is uppercase for consistency
            data_engine.subscribe_instrument(key.upper(), sid, interval=str(interval))
        except Exception as e:
            logger.error(f"Subscription error for {key}: {e}")
            continue

@sio.on('unsubscribe')
async def handle_unsubscribe(sid, data):
    instrument_keys = data.get('instrumentKeys', [])
    interval = data.get('interval', '1')
    for key in instrument_keys:
        hrn = symbol_mapper.get_hrn(key)
        logger.info(f"Client {sid} unsubscribing from: {key} ({interval}m) (Room: {hrn})")
        try:
            # First unsubscribe from the engine tracking
            data_engine.unsubscribe_instrument(key.upper(), sid, interval=str(interval))

            # ONLY leave room if NO other charts for this HRN exist for this client
            if not data_engine.is_sid_using_hrn(sid, hrn):
                logger.info(f"Client {sid} leaving room {hrn} (No more charts for this symbol)")
                await sio.leave_room(sid, hrn)
            else:
                logger.info(f"Client {sid} remains in room {hrn} (Other charts still active)")
        except Exception as e:
            logger.error(f"Unsubscription error for {key}: {e}")
            continue

@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy"}

@fastapi_app.get("/api/tv/search")
async def tv_search(text: str = Query(..., min_length=1)):
    """Proxies TradingView symbol search and merges results with options scanner."""
    import httpx

    exchange = ""
    search_text = text
    if ":" in text:
        parts = text.split(":", 1)
        exchange = parts[0]
        search_text = parts[1]

    # Standard proxy search
    url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={search_text}&hl=1&exchange={exchange}&lang=en&search_type=&domain=production&sort_by_country=IN"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.tradingview.com/',
        'Origin': 'https://www.tradingview.com'
    }

    tv_results = {"symbols": []}
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            if response.status_code == 200:
                tv_results = response.json()
    except Exception as e:
        logger.error(f"Search proxy error: {e}")

    # Augmented search for options
    upper_text = search_text.upper()

    # Heuristic to find underlying
    # If it's a known index or a common stock name
    indices = ["NIFTY", "BANKNIFTY", "FINNIFTY"]
    underlying = None
    for idx in indices:
        if idx in upper_text:
            underlying = idx
            break

    # If no index, and it looks like it could be a stock ticker (4-15 chars, all caps)
    if not underlying and 3 <= len(upper_text) <= 15 and upper_text.isalpha():
        underlying = upper_text

    if underlying:
        try:
            opt_data = await search_options(underlying)
            if opt_data and 'symbols' in opt_data:
                # Filter options that match the search text
                # Technical symbols are like NSE:NIFTY260210C25600
                search_parts = upper_text.split()
                filtered = []
                for item in opt_data['symbols']:
                    s = item.get('s', '')
                    s_norm = s.upper().replace(":", "")
                    if all(p in s_norm for p in search_parts):
                        exch, name = s.split(':', 1) if ':' in s else ("NSE", s)
                        filtered.append({
                            "symbol": name,
                            "description": f"{name} Option",
                            "exchange": exch,
                            "type": "option"
                        })

                # Merge into tv_results, prioritizing scanner results
                existing_syms = {s['symbol'] for s in tv_results.get('symbols', [])}
                new_symbols = []
                for f in filtered[:100]: # Limit to avoid bloat
                    if f['symbol'] not in existing_syms:
                        new_symbols.append(f)

                # Prepend merged results so they appear at the top
                tv_results['symbols'] = new_symbols + tv_results.get('symbols', [])
        except Exception as e:
            logger.error(f"Options merging error: {e}")

    return tv_results

@fastapi_app.get("/api/tv/options")
async def get_tv_options(underlying: str = Query(...)):
    """Fetches options for a given underlying."""
    data = await search_options(underlying)
    if not data:
        raise HTTPException(status_code=500, detail="Failed to fetch options")

    # Format results for frontend search dropdown
    results = []
    for item in data.get('symbols', []):
        full_symbol = item.get('s', '')
        if ':' in full_symbol:
            exch, name = full_symbol.split(':', 1)
            results.append({
                "symbol": name,
                "description": f"{name} Option",
                "exchange": exch,
                "type": "option"
            })
    return {"symbols": results}

@fastapi_app.get("/api/tv/intraday/{instrument_key}")
async def get_intraday(instrument_key: str, interval: str = '1'):
    """Fetch intraday candles from TradingView."""
    try:
        clean_key = unquote(instrument_key)
        hrn = symbol_mapper.get_hrn(clean_key)

        # Check if we have history with indicators in WSS
        from external.tv_live_wss import get_tv_wss
        wss = get_tv_wss()

        wss_candles = []
        wss_indicators = []
        hist_key = (hrn, interval)
        if wss and hist_key in wss.history:
            hist = wss.history[hist_key]
            wss_candles = hist.get('ohlcv', [])
            wss_indicators = hist.get('indicators', [])

        # Fetch high-quality historical candles from API
        tv_candles = await asyncio.to_thread(tv_api.get_hist_candles, clean_key, interval, 1000)

        # If API failed, use WSS candles
        if not tv_candles:
            tv_candles = wss_candles
        elif wss_candles:
            # tv_api.get_hist_candles returns newest first.
            newest_api_ts = tv_candles[0][0]

            # Check if wss_candles has valid timestamps (> 1e9)
            if len(wss_candles) > 0 and wss_candles[0][0] > 1e9:
                merged_map = {c[0]: c for c in tv_candles}
                for c in wss_candles:
                    # c[0] is timestamp
                    if c[0] > newest_api_ts:
                        merged_map[c[0]] = c
                tv_candles = sorted(merged_map.values(), key=lambda x: x[0], reverse=True)

        # Build Indicators from historical candles
        valid_indicators = []
        if tv_candles:
            try:
                import pandas as pd
                # tv_candles are newest first, we need oldest first for EMA
                analyzer_candles = sorted(tv_candles, key=lambda x: x[0])
                df = pd.DataFrame(analyzer_candles, columns=['ts', 'o', 'h', 'l', 'c', 'v'])

                # EMA 9 (Blue)
                ema9 = df['c'].ewm(span=9, adjust=False).mean()
                valid_indicators.append({
                    "id": "ema_9",
                    "title": "EMA 9",
                    "type": "line",
                    "style": {"color": "#3b82f6", "lineWidth": 1},
                    "data": [{"time": analyzer_candles[i][0], "value": float(val)} for i, val in enumerate(ema9) if i >= 8]
                })

                # EMA 20 (Orange)
                ema20 = df['c'].ewm(span=20, adjust=False).mean()
                valid_indicators.append({
                    "id": "ema_20",
                    "title": "EMA 20",
                    "type": "line",
                    "style": {"color": "#f97316", "lineWidth": 1},
                    "data": [{"time": analyzer_candles[i][0], "value": float(val)} for i, val in enumerate(ema20) if i >= 19]
                })

                # Market Psychology Analyzer
                from brain.MarketPsychologyAnalyzer import MarketPsychologyAnalyzer
                analyzer = MarketPsychologyAnalyzer()
                zones, signals = analyzer.analyze(analyzer_candles)

                # Add Zones as price lines
                for i, zone in enumerate(zones):
                    valid_indicators.append({
                        "id": f"battle_zone_{i}",
                        "type": "price_line",
                        "title": "BATTLE ZONE",
                        "data": {
                            "price": zone['price'],
                            "color": "rgba(59, 130, 246, 0.4)",
                            "lineStyle": 2,
                            "title": "BATTLE ZONE"
                        }
                    })

                # Add Signals as markers
                marker_data = []
                for ts, sig_type in signals.items():
                    unix_ts = int(ts.timestamp())
                    marker_data.append({
                        "time": unix_ts,
                        "position": "aboveBar" if "SHORT" in sig_type else "belowBar",
                        "color": "#ef4444" if "SHORT" in sig_type else "#22c55e",
                        "shape": "arrowDown" if "SHORT" in sig_type else "arrowUp",
                        "text": sig_type
                    })

                if marker_data:
                    valid_indicators.append({
                        "id": "psych_signals",
                        "type": "markers",
                        "title": "Psychology Signals",
                        "data": marker_data
                    })
            except Exception as e:
                logger.error(f"Error building indicators for intraday: {e}")

        return {
            "instrumentKey": clean_key,
            "hrn": hrn,
            "candles": tv_candles or [],
            "indicators": valid_indicators
        }
    except Exception as e:
        logger.error(f"Error in intraday fetch: {e}")
        return {"candles": [], "indicators": []}

# Template and Static Files
templates = Jinja2Templates(directory="backend/templates")
fastapi_app.mount("/static", StaticFiles(directory="backend/static"), name="static")

@fastapi_app.get("/")
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@fastapi_app.get("/db-viewer")
async def db_viewer(request: Request):
    return templates.TemplateResponse("db_viewer.html", {"request": request})

@fastapi_app.get("/api/db/tables")
async def get_db_tables():
    try:
        tables = db.get_tables()
        result = []
        for table in tables:
            schema = db.get_table_schema(table, json_serialize=True)
            result.append({"name": table, "schema": schema})
        return {"tables": result}
    except Exception as e:
        logger.error(f"Error fetching tables: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@fastapi_app.post("/api/db/query")
async def run_db_query(request: Request):
    try:
        body = await request.json()
        sql = body.get("sql")
        if not sql:
            raise HTTPException(status_code=400, detail="SQL query is required")

        results = db.query(sql, json_serialize=True)
        return {"results": results}
    except Exception as e:
        logger.error(f"Error running query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

app = socketio.ASGIApp(sio, fastapi_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=5051, reload=False)
