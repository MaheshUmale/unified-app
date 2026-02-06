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
            data_engine.subscribe_instrument(key.upper(), interval=str(interval))
        except Exception as e:
            logger.error(f"Subscription error for {key}: {e}")
            continue

@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy"}

@fastapi_app.get("/api/tv/search")
async def tv_search(text: str = Query(..., min_length=1)):
    """Proxies TradingView symbol search with improved handling for prefixed symbols."""
    import httpx

    exchange = ""
    search_text = text
    if ":" in text:
        parts = text.split(":", 1)
        exchange = parts[0]
        search_text = parts[1]

    url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={search_text}&hl=1&exchange={exchange}&lang=en&search_type=&domain=production&sort_by_country=IN"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://www.tradingview.com/',
        'Origin': 'https://www.tradingview.com'
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            return response.json()
    except Exception as e:
        logger.error(f"Search proxy error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch search results")

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

        # If we have WSS history, we might want to append the very latest candles
        # from WSS if they are newer than what the API returned.
        if tv_candles and wss_candles:
            # tv_api.get_hist_candles returns newest first.
            newest_api_ts = tv_candles[0][0]

            # Check if wss_candles has valid timestamps (> 1e9)
            if wss_candles[0][0] > 1e9:
                merged_map = {c[0]: c for c in tv_candles}
                for c in wss_candles:
                    # c[0] is timestamp
                    if c[0] > newest_api_ts:
                        merged_map[c[0]] = c
                tv_candles = sorted(merged_map.values(), key=lambda x: x[0], reverse=True)

        # Ensure indicators also have valid timestamps
        valid_indicators = []
        for ind in wss_indicators:
            if ind.get('timestamp', 0) > 1e9:
                valid_indicators.append(ind)

        return {
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

app = socketio.ASGIApp(sio, fastapi_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=5051, reload=False)
