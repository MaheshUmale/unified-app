"""
ProTrade Simplified API Server
Handles essential REST endpoints and Socket.IO real-time streaming for the charting terminal.
"""
import os
import json
import asyncio
import logging
from logging.config import dictConfig
from typing import List, Dict, Any, Optional
import socketio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from config import LOGGING_CONFIG, INITIAL_INSTRUMENTS
from db.local_db import db
from core import data_engine
from core.symbol_mapper import symbol_mapper
from core.replay_engine import ReplayEngine
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
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
main_loop = None

def emit_replay(event, data, room=None):
    if main_loop:
        asyncio.run_coroutine_threadsafe(sio.emit(event, data, room=room), main_loop)

replay_engine = ReplayEngine(emit_fn=emit_replay, db_dependencies={})

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
    for key in instrument_keys:
        logger.info(f"Client {sid} subscribing to: {key}")
        try:
            await sio.enter_room(sid, key)
            data_engine.subscribe_instrument(key)
        except ValueError:
            break

@sio.on('start_replay')
async def handle_start_replay(sid, data):
    date_str = data.get('date')
    instrument_keys = data.get('instrument_keys', INITIAL_INSTRUMENTS)
    speed = float(data.get('speed', 1.0))
    replay_engine.start_replay(date_str, instrument_keys, speed)

@sio.on('stop_replay')
async def handle_stop_replay(sid, data):
    replay_engine.stop_replay()

@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy"}

@fastapi_app.get("/api/tv/search")
async def tv_search(text: str = Query(..., min_length=1)):
    """Proxies TradingView symbol search."""
    import httpx
    url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={text}&hl=1&exchange=&lang=en&search_type=undefined&domain=production&sort_by_country=IN&promo=true"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://in.tradingview.com/',
        'Origin': 'https://in.tradingview.com'
    }
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers, timeout=10.0)
            return response.json()
    except Exception as e:
        logger.error(f"Search proxy error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch search results")

@fastapi_app.get("/api/tv/intraday/{instrument_key}")
@fastapi_app.get("/api/upstox/intraday/{instrument_key}")
async def get_intraday(instrument_key: str, date: Optional[str] = None, interval: str = '1'):
    """Fetch intraday candles from TradingView or LocalDB."""
    try:
        clean_key = unquote(instrument_key)
        if not date:
            tv_candles = await asyncio.to_thread(tv_api.get_hist_candles, clean_key, interval, 1000)
            if tv_candles:
                return {"candles": tv_candles}

        db_history = data_engine.load_intraday_data(clean_key, date_str=date, timeframe_min=int(interval))
        candles = []
        for bar in db_history:
            candles.append([
                datetime.fromtimestamp(bar['ts']/1000).isoformat(),
                bar['open'], bar['high'], bar['low'], bar['close'], bar['volume']
            ])
        return {"candles": candles[::-1]}
    except Exception as e:
        logger.error(f"Error in intraday fetch: {e}")
        return {"candles": []}

@fastapi_app.get("/api/replay/dates")
async def get_replay_dates():
    try:
        rows = db.query("SELECT DISTINCT CAST(date AS VARCHAR) as d FROM ticks ORDER BY d DESC")
        return [r['d'] for r in rows]
    except:
        return []

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
