"""
Enhanced ProTrade API Server
Optimized, Organized, and Simplified for high-performance trading analytics.
"""

import os
import asyncio
import logging
import httpx
import pandas as pd
import io
import socketio
from datetime import datetime, date
from typing import Any, Optional, List
from contextlib import asynccontextmanager
from logging.config import dictConfig
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from config import LOGGING_CONFIG, INITIAL_INSTRUMENTS, SERVER_PORT
from core import data_engine
from core.provider_registry import initialize_default_providers
from core.options_manager import options_manager
from core.symbol_mapper import symbol_mapper
from core.greeks_calculator import greeks_calculator
from core.strategy_builder import strategy_builder, StrategyType
from core.alert_system import alert_system, AlertType
from brain.nse_confluence_scalper import scalper
from external.tv_api import tv_api
from external.tv_scanner import search_options
from db.local_db import db

# ==================== UTILS & CACHING ====================

class APICache:
    """Simple TTL cache to reduce redundant computations and DB queries."""
    def __init__(self, ttl_seconds=60):
        self.cache = {}
        self.ttl = ttl_seconds

    def get(self, key):
        if key in self.cache:
            val, ts = self.cache[key]
            if datetime.now().timestamp() - ts < self.ttl:
                return val
            del self.cache[key]
        return None

    def set(self, key, value):
        self.cache[key] = (value, datetime.now().timestamp())

# Specialized caches
hist_cache = APICache(ttl_seconds=30)
pcr_cache = APICache(ttl_seconds=60)
modern_cache = APICache(ttl_seconds=5)

def format_error(e: Exception, message: str = "Internal Server Error"):
    logging.error(f"{message}: {str(e)}")
    return {"status": "error", "message": str(e)}

# ==================== INITIALIZATION ====================

dictConfig(LOGGING_CONFIG)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle management for the Trading Terminal."""
    logger.info("Initializing ProTrade Terminal Services...")
    global main_loop
    
    initialize_default_providers()
    main_loop = asyncio.get_running_loop()
    
    data_engine.set_socketio(sio, loop=main_loop)
    data_engine.start_websocket_thread(None, INITIAL_INSTRUMENTS)
    
    options_manager.set_socketio(sio, loop=main_loop)
    await options_manager.start()

    scalper.set_socketio(sio, loop=main_loop)
    
    yield
    
    logger.info("Shutting down ProTrade Terminal...")
    try:
        await options_manager.stop()
        data_engine.flush_tick_buffer()
    except Exception as e:
        logger.error(f"Shutdown error: {e}")

fastapi_app = FastAPI(title="ProTrade Enhanced API", lifespan=lifespan)
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*', ping_timeout=60, ping_interval=25)
main_loop = None

fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="backend/templates")

# ==================== SOCKET.IO HANDLERS ====================

@sio.event
async def connect(sid, environ): logger.info(f"Client connected: {sid}")

@sio.event
async def disconnect(sid):
    logger.info(f"Client disconnected: {sid}")
    data_engine.handle_disconnect(sid)

@sio.on('subscribe')
async def handle_subscribe(sid, data):
    keys = data.get('instrumentKeys', [])
    interval = str(data.get('interval', '1'))
    for key in keys:
        k = key.upper()
        await sio.enter_room(sid, k)
        data_engine.subscribe_instrument(k, sid, interval=interval)

@sio.on('subscribe_options')
async def handle_subscribe_options(sid, data):
    underlying = data.get('underlying')
    if underlying: await sio.enter_room(sid, f"options_{underlying}")

@sio.on('unsubscribe_options')
async def handle_unsubscribe_options(sid, data):
    underlying = data.get('underlying')
    if underlying: await sio.leave_room(sid, f"options_{underlying}")

@sio.on('unsubscribe')
async def handle_unsubscribe(sid, data):
    keys = data.get('instrumentKeys', [])
    interval = str(data.get('interval', '1'))
    for key in keys:
        k = key.upper()
        data_engine.unsubscribe_instrument(k, sid, interval=interval)
        if not data_engine.is_sid_using_instrument(sid, k):
            await sio.leave_room(sid, k)

# ==================== CORE API ====================

@fastapi_app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "3.0-optimized"}

@fastapi_app.get("/api/tv/search")
async def tv_search(text: str = Query(..., min_length=1)):
    """Proxies TradingView symbol search and merges local options results."""
    exchange = ""
    search_text = text
    if ":" in text:
        exchange, search_text = text.split(":", 1)
    
    url = f"https://symbol-search.tradingview.com/symbol_search/v3/?text={search_text}&hl=1&exchange={exchange}&lang=en&search_type=&domain=production&sort_by_country=IN"
    headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.tradingview.com/'}
    
    tv_results = {"symbols": []}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=5.0)
            if resp.status_code == 200: tv_results = resp.json()
    except Exception as e: logger.error(f"Search proxy error: {e}")
    
    # Merge options
    upper_text = search_text.upper()
    underlying = next((idx for idx in ["NIFTY", "BANKNIFTY", "FINNIFTY"] if idx in upper_text), None)
    if not underlying and 3 <= len(upper_text) <= 15 and upper_text.isalpha(): underlying = upper_text
    
    if underlying:
        try:
            opt_data = await search_options(underlying)
            if opt_data and 'symbols' in opt_data:
                parts = upper_text.split()
                filtered = []
                for item in opt_data['symbols']:
                    s = item.get('s', '')
                    if all(p in s.upper().replace(":", "") for p in parts):
                        exch, name = s.split(':', 1) if ':' in s else ("NSE", s)
                        filtered.append({"symbol": name, "description": f"{name} Option", "exchange": exch, "type": "option"})
                
                existing = {s['symbol'] for s in tv_results.get('symbols', [])}
                tv_results['symbols'] = [f for f in filtered[:100] if f['symbol'] not in existing] + tv_results.get('symbols', [])
        except Exception as e: logger.error(f"Options merging error: {e}")
    
    return tv_results

@fastapi_app.get("/api/tv/intraday/{instrument_key}")
async def get_intraday(instrument_key: str, interval: str = '1'):
    """Fetch intraday candles with automated technical indicators."""
    cache_key = f"intraday_{instrument_key}_{interval}"
    cached = hist_cache.get(cache_key)
    if cached: return cached

    try:
        clean_key = unquote(instrument_key)
        tv_candles = await asyncio.to_thread(tv_api.get_hist_candles, clean_key, interval, 1000)
        
        indicators = []
        if tv_candles:
            df = pd.DataFrame(sorted(tv_candles, key=lambda x: x[0]), columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            # Standard EMAs
            for span, color in [(9, "#3b82f6"), (20, "#f97316")]:
                ema = df['c'].ewm(span=span, adjust=False).mean()
                indicators.append({
                    "id": f"ema_{span}", "title": f"EMA {span}", "type": "line",
                    "style": {"color": color, "lineWidth": 1},
                    "data": [{"time": int(df['ts'][i]), "value": float(val)} for i, val in enumerate(ema) if i >= span-1]
                })

            # Market Psychology Signals
            try:
                from brain.MarketPsychologyAnalyzer import MarketPsychologyAnalyzer
                zones, signals = MarketPsychologyAnalyzer().analyze(tv_candles)
                for ts, sig_type in signals.items():
                    indicators.append({
                        "id": "psych_signals", "type": "markers", "title": "Psychology",
                        "data": [{"time": int(ts.timestamp()), "position": "aboveBar" if "SHORT" in sig_type else "belowBar",
                                 "color": "#ef4444" if "SHORT" in sig_type else "#22c55e", "shape": "arrowDown" if "SHORT" in sig_type else "arrowUp",
                                 "text": sig_type}]
                    })
            except Exception: pass

        result = {"instrumentKey": clean_key, "hrn": symbol_mapper.get_hrn(clean_key), "candles": tv_candles or [], "indicators": indicators}
        hist_cache.set(cache_key, result)
        return result
    except Exception as e: return format_error(e, "Intraday fetch failed")

# ==================== OPTIONS API ====================

@fastapi_app.get("/api/options/chain/{underlying}/with-greeks")
async def get_chain_with_greeks(underlying: str, spot_price: Optional[float] = None):
    chain_data = options_manager.get_chain_with_greeks(underlying)
    spot = spot_price or await options_manager.get_spot_price(underlying)
    
    for item in chain_data.get('chain', []):
        strike, o_type = item.get('strike', 0), item.get('option_type', 'call')
        item['moneyness'] = greeks_calculator.categorize_strike(strike, spot, o_type)
        item['distance_from_atm_pct'] = round(abs(strike - spot) / spot * 100, 2) if spot > 0 else 0
    
    return {"underlying": underlying, "spot_price": spot, "chain": chain_data.get('chain', []), "source": chain_data.get('source', 'unknown')}

@fastapi_app.get("/api/options/pcr-trend/{underlying}")
async def get_pcr_trend(underlying: str):
    cache_key = f"pcr_trend_{underlying}"
    cached = pcr_cache.get(cache_key)
    if cached: return cached

    history = await asyncio.to_thread(db.query, """
        SELECT timestamp, AVG(pcr_oi) as pcr_oi, AVG(pcr_vol) as pcr_vol, AVG(pcr_oi_change) as pcr_oi_change,
               AVG(underlying_price) as underlying_price, MAX(max_pain) as max_pain, AVG(spot_price) as spot_price,
               MAX(total_oi) as total_oi, MAX(total_oi_change) as total_oi_change
        FROM pcr_history WHERE underlying = ?
        AND CAST((timestamp AT TIME ZONE 'UTC') AT TIME ZONE 'Asia/Kolkata' AS DATE) =
            (SELECT CAST(MAX(timestamp) AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata' AS DATE) FROM pcr_history WHERE underlying = ?)
        GROUP BY timestamp ORDER BY timestamp ASC
    """, (underlying, underlying), json_serialize=True)
    
    result = {"history": history}
    pcr_cache.set(cache_key, result)
    return result

@fastapi_app.get("/api/options/oi-analysis/{underlying}")
async def get_oi_analysis(underlying: str):
    latest = await asyncio.to_thread(db.query, "SELECT MAX(timestamp) as ts FROM options_snapshots WHERE underlying = ?", (underlying,))
    if not latest or not latest[0]['ts']: return {"data": []}

    ts = latest[0]['ts']
    data = await asyncio.to_thread(db.query, """
        SELECT strike, SUM(CASE WHEN option_type = 'call' THEN oi ELSE 0 END) as call_oi,
               SUM(CASE WHEN option_type = 'put' THEN oi ELSE 0 END) as put_oi,
               SUM(CASE WHEN option_type = 'call' THEN oi_change ELSE 0 END) as call_oi_change,
               SUM(CASE WHEN option_type = 'put' THEN oi_change ELSE 0 END) as put_oi_change
        FROM options_snapshots WHERE underlying = ? AND timestamp = ? GROUP BY strike ORDER BY strike ASC
    """, (underlying, ts), json_serialize=True)
    return {"timestamp": ts, "data": data}

@fastapi_app.get("/api/options/genie-insights/{underlying}")
async def get_genie_insights(underlying: str): return await options_manager.get_genie_insights(underlying)

@fastapi_app.get("/api/options/oi-buildup/{underlying}")
async def get_oi_buildup(underlying: str): return options_manager.get_oi_buildup_analysis(underlying)

@fastapi_app.get("/api/options/iv-analysis/{underlying}")
async def get_iv_analysis(underlying: str): return options_manager.get_iv_analysis(underlying)

@fastapi_app.get("/api/options/support-resistance/{underlying}")
async def get_sr_levels(underlying: str): return options_manager.get_support_resistance(underlying)

@fastapi_app.get("/api/options/high-activity/{underlying}")
async def get_high_activity(underlying: str): return options_manager.get_high_activity_strikes(underlying)

@fastapi_app.post("/api/options/backfill")
async def trigger_backfill():
    asyncio.create_task(options_manager.backfill_today())
    return {"status": "success", "message": "Backfill started"}

# ==================== STRATEGY & ALERTS ====================

@fastapi_app.post("/api/strategy/build")
async def build_strategy(req: Request):
    body = await req.json()
    st_input = body.get('strategy_type', 'CUSTOM').upper()
    s_type = StrategyType[st_input] if st_input in StrategyType.__members__ else StrategyType.CUSTOM

    strat = strategy_builder.create_strategy(body.get('name', 'Custom'), s_type, body.get('underlying'), body.get('spot_price', 0), body.get('legs', []))
    return {"status": "success", "analysis": strategy_builder.analyze_strategy(strat.name)}

@fastapi_app.get("/api/alerts")
async def get_alerts(underlying: Optional[str] = None):
    return {"alerts": alert_system.get_alerts(underlying)}

@fastapi_app.post("/api/alerts/create")
async def create_alert(req: Request):
    b = await req.json()
    a = alert_system.create_alert(b.get('name'), AlertType(b.get('alert_type')), b.get('underlying'), b.get('condition'))
    return {"status": "success", "alert": a.to_dict()}

@fastapi_app.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: str):
    if alert_system.delete_alert(alert_id): return {"status": "success"}
    raise HTTPException(404, "Alert not found")

# ==================== SCALPER API ====================

@fastapi_app.post("/api/scalper/start")
async def start_scalper(underlying: str = "NSE:NIFTY"):
    scalper.underlying = underlying
    await scalper.start()
    return {"status": "success"}

@fastapi_app.post("/api/scalper/stop")
async def stop_scalper():
    await scalper.stop()
    return {"status": "success"}

@fastapi_app.get("/api/scalper/status")
async def get_scalper_status():
    return {"is_running": scalper.is_running, "underlying": scalper.underlying, "trades": scalper.order_manager.active_trades}

# ==================== TICK & DASHBOARD API ====================

@fastapi_app.get("/api/ticks/history/{instrument_key}")
async def get_tick_history(instrument_key: str, limit: int = 10000):
    history = await asyncio.to_thread(db.query, "SELECT ts_ms, price, qty FROM ticks WHERE instrumentKey = ? ORDER BY ts_ms DESC LIMIT ?", (unquote(instrument_key), limit), json_serialize=True)
    return {"history": history[::-1]}

@fastapi_app.get("/api/modern/data/{underlying}")
async def get_modern_data(underlying: str):
    cache_key = f"modern_data_{underlying}"
    cached = modern_cache.get(cache_key)
    if cached: return cached

    try:
        res = {
            "underlying": underlying,
            "spot_price": await options_manager.get_spot_price(underlying),
            "chain": options_manager.get_chain_with_greeks(underlying).get('chain', []),
            "oi_buildup": options_manager.get_oi_buildup_analysis(underlying),
            "pcr_trend": (await asyncio.to_thread(db.query, "SELECT timestamp, pcr_oi, spot_price FROM pcr_history WHERE underlying = ? ORDER BY timestamp DESC LIMIT 50", (underlying,), json_serialize=True))[::-1],
            "sr_levels": options_manager.get_support_resistance(underlying),
            "genie": await options_manager.get_genie_insights(underlying),
            "expiries": await options_manager.get_expiry_dates(underlying),
            "timestamp": datetime.now().isoformat()
        }
        modern_cache.set(cache_key, res)
        return res
    except Exception as e: return format_error(e)

# ==================== DATABASE API ====================

@fastapi_app.get("/api/db/tables")
async def get_db_tables():
    tables = await asyncio.to_thread(db.get_tables)
    return {"tables": [{"name": t, "row_count": (await asyncio.to_thread(db.query, f'SELECT COUNT(*) as c FROM "{t}"'))[0]['c']} for t in tables]}

@fastapi_app.post("/api/db/query")
async def run_db_query(req: Request):
    sql = (await req.json()).get("sql")
    if not sql: raise HTTPException(400, "SQL required")
    return {"results": await asyncio.to_thread(db.query, sql, json_serialize=True)}

@fastapi_app.post("/api/db/export")
async def export_db_query(req: Request):
    sql = (await req.json()).get("sql")
    res = await asyncio.to_thread(db.query, sql, json_serialize=False)
    if not res: raise HTTPException(400, "No data")

    stream = io.StringIO()
    pd.DataFrame(res).to_csv(stream, index=False)
    resp = StreamingResponse(iter([stream.getvalue()]), media_type="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=export.csv"
    return resp

# ==================== STATIC ROUTES ====================

@fastapi_app.get("/")
async def serve_index(request: Request): return templates.TemplateResponse("index.html", {"request": request})

@fastapi_app.get("/options")
async def serve_options(request: Request): return templates.TemplateResponse("options_dashboard.html", {"request": request})

@fastapi_app.get("/modern")
async def serve_modern(request: Request): return templates.TemplateResponse("modern_dashboard.html", {"request": request})

@fastapi_app.get("/orderflow")
async def serve_orderflow(request: Request): return templates.TemplateResponse("orderflow_chart.html", {"request": request})

@fastapi_app.get("/db-viewer")
async def serve_db(request: Request): return templates.TemplateResponse("db_viewer.html", {"request": request})

@fastapi_app.get("/tick")
async def serve_tick(request: Request): return templates.TemplateResponse("tick_chart.html", {"request": request})

fastapi_app.mount("/static", StaticFiles(directory="backend/static"), name="static")
app = socketio.ASGIApp(sio, fastapi_app)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=int(os.getenv("PORT", SERVER_PORT)), reload=False)
