#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView K-line Data HTTP API Service

Provides a RESTful API interface to retrieve TradingView historical K-line data.

Startup:
    python -m tradingview.kline_api_server

    Or specify a port:
    python -m tradingview.kline_api_server --port 8080

API Endpoints:
    GET /klines?symbol=OANDA:XAUUSD&timeframe=15&count=100
    GET /health
    GET /stats

Example Requests:
    curl "http://localhost:8000/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100"
    curl "http://localhost:8000/klines?symbol=BINANCE:BTCUSDT&timeframe=15m&count=50"

Author: Claude Code Assistant
Created: 2024-12
Version: 1.0.0
"""

import sys
from pathlib import Path
from typing import Optional
from datetime import datetime
from contextlib import asynccontextmanager

# Add project root to sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from fastapi import FastAPI, Query, HTTPException
    from fastapi.responses import JSONResponse
    from fastapi.middleware.cors import CORSMiddleware
    import uvicorn
except ImportError:
    print("❌ Missing dependencies, please install: pip install fastapi uvicorn")
    sys.exit(1)

from tradingview.historical_kline_service import (
    HistoricalKlineService,
    KlineDataRequest,
    KlineQualityLevel,
    DataFetchStatus
)

from tradingview.utils import get_logger
logger = get_logger(__name__)

# =============================================================================
# Global Service Instance
# =============================================================================

kline_service: Optional[HistoricalKlineService] = None

# =============================================================================
# Lifecycle Management
# =============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""
    global kline_service

    # Startup logic
    logger.info("🚀 Starting K-line data API service...")
    try:
        kline_service = HistoricalKlineService(use_enhanced_client=True)
        await kline_service.initialize()
        logger.info("✅ K-line data service initialized successfully")
    except Exception as e:
        logger.error(f"❌ Service initialization failed: {e}")
        raise

    yield

    # Shutdown logic
    logger.info("🛑 Closing K-line data API service...")
    if kline_service:
        await kline_service.close()
        logger.info("✅ K-line data service shutdown complete")

# =============================================================================
# FastAPI Application Configuration
# =============================================================================

app = FastAPI(
    title="TradingView K-line Data API",
    description="RESTful API providing access to TradingView historical K-line data",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# API Endpoints
# =============================================================================

@app.get("/")
async def root():
    """Service root info"""
    return {
        "service": "TradingView K-line Data API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "klines": "/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100",
            "health": "/health",
            "stats": "/stats",
            "docs": "/docs"
        }
    }

@app.get("/klines")
async def get_klines(
    symbol: str = Query(..., description="Trading symbol, e.g., OANDA:XAUUSD, BINANCE:BTCUSDT"),
    timeframe: str = Query("15", description="Timeframe, e.g., 1, 5, 15, 30, 60, 1D (also supports 15m format)"),
    count: int = Query(100, ge=1, le=5000, description="K-line count (1-5000)"),
    quality: str = Query("production", description="Quality level: development, production, financial"),
    use_cache: bool = Query(True, description="Whether to use cache"),
    format: str = Query("json", description="Response format: json, simple")
):
    """
    Retrieve K-line data

    Parameters:
        - symbol: Trading symbol (Required)
            - Format: EXCHANGE:SYMBOL, e.g., OANDA:XAUUSD, BINANCE:BTCUSDT
            - Default prefix is BINANCE if not specified

        - timeframe: Timeframe (Default: 15)
            - Supported: 1, 5, 15, 30, 60, 240, 1D, 1W, 1M
            - Also supports: 1m, 5m, 15m, 1h, 4h, 1d (auto-converted)

        - count: Retrieval count (Default: 100, Range: 1-5000)

        - quality: Quality level (Default: production)
            - development: ≥90%
            - production: ≥95%
            - financial: ≥98%

        - use_cache: Whether to use cache (Default: true)

        - format: Response format
            - json: Full JSON (with metadata)
            - simple: Simple format (only K-line array)

    Returns:
        JSON K-line data
    """
    try:
        # Standardize timeframe (15m -> 15, 1h -> 60, etc.)
        timeframe_normalized = normalize_timeframe(timeframe)

        # Standardize symbol
        symbol_normalized = normalize_symbol(symbol)

        # Parse quality level
        try:
            quality_level = KlineQualityLevel[quality.upper()]
        except KeyError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid quality level: {quality}. Use development, production, or financial"
            )

        # Create request
        request = KlineDataRequest(
            symbol=symbol_normalized,
            timeframe=timeframe_normalized,
            count=count,
            quality_level=quality_level,
            cache_enabled=use_cache
        )

        logger.info(f"📊 K-line request: {symbol_normalized} {timeframe_normalized} x{count}")

        # Fetch data
        response = await kline_service.fetch_klines(request)

        # Handle failure status
        if response.status == DataFetchStatus.FAILED:
            raise HTTPException(
                status_code=500,
                detail=f"Data retrieval failed: {response.error_message}"
            )

        # Format results
        if format == "simple":
            return {
                "success": True,
                "symbol": response.symbol,
                "timeframe": response.timeframe,
                "count": len(response.klines),
                "data": [
                    {
                        "timestamp": k.timestamp,
                        "datetime": k.datetime,
                        "open": k.open,
                        "high": k.high,
                        "low": k.low,
                        "close": k.close,
                        "volume": k.volume
                    }
                    for k in response.klines
                ]
            }
        else:
            result = response.to_dict()
            result["success"] = True

            # Add warning if partial
            if response.status == DataFetchStatus.PARTIAL:
                result["warning"] = response.error_message

            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ K-line request failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: {str(e)}"
        )

@app.get("/batch_klines")
async def get_batch_klines(
    symbols: str = Query(..., description="Comma-separated symbol list, e.g., BINANCE:BTCUSDT,BINANCE:ETHUSDT"),
    timeframe: str = Query("15", description="Timeframe"),
    count: int = Query(100, ge=1, le=5000, description="K-line count per symbol"),
    quality: str = Query("production", description="Quality level"),
    use_cache: bool = Query(True, description="Whether to use cache")
):
    """
    Retrieve K-line data for multiple symbols.

    Parameters:
        - symbols: Comma-separated list
            e.g., BINANCE:BTCUSDT,BINANCE:ETHUSDT,OANDA:XAUUSD

    Returns:
        Array of K-line data for each symbol
    """
    try:
        # Parse symbol list
        symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]

        if not symbol_list:
            raise HTTPException(status_code=400, detail="Symbol list cannot be empty")

        if len(symbol_list) > 50:
            raise HTTPException(status_code=400, detail="Max 50 symbols per batch request")

        # Standardize timeframe
        timeframe_normalized = normalize_timeframe(timeframe)

        # Parse quality level
        try:
            quality_level = KlineQualityLevel[quality.upper()]
        except KeyError:
            raise HTTPException(status_code=400, detail=f"Invalid quality level: {quality}")

        # Create batch requests
        requests = [
            KlineDataRequest(
                symbol=normalize_symbol(symbol),
                timeframe=timeframe_normalized,
                count=count,
                quality_level=quality_level,
                cache_enabled=use_cache
            )
            for symbol in symbol_list
        ]

        logger.info(f"📊 Batch K-line request: {len(symbol_list)} symbols")

        # Batch fetch
        responses = await kline_service.batch_fetch_klines(requests)

        # Format results
        results = []
        for response in responses:
            results.append({
                "symbol": response.symbol,
                "timeframe": response.timeframe,
                "status": response.status.value,
                "count": len(response.klines),
                "quality_score": response.quality_score,
                "data": [
                    {
                        "timestamp": k.timestamp,
                        "datetime": k.datetime,
                        "open": k.open,
                        "high": k.high,
                        "low": k.low,
                        "close": k.close,
                        "volume": k.volume
                    }
                    for k in response.klines
                ],
                "error": response.error_message if response.status == DataFetchStatus.FAILED else None
            })

        return {
            "success": True,
            "total": len(results),
            "results": results
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Batch request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    if kline_service and kline_service.is_initialized:
        return {
            "status": "healthy",
            "service": "kline_api",
            "timestamp": datetime.now().isoformat(),
            "initialized": True
        }
    else:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "kline_api",
                "timestamp": datetime.now().isoformat(),
                "initialized": False
            }
        )

@app.get("/stats")
async def get_stats():
    """Retrieve service statistics"""
    if not kline_service:
        raise HTTPException(status_code=503, detail="Service not initialized")

    stats = kline_service.get_stats()

    return {
        "success": True,
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }

# =============================================================================
# Helper Functions
# =============================================================================

def normalize_timeframe(timeframe: str) -> str:
    """
    Normalize timeframe format.

    Conversion Rules:
        1m, 1min -> 1
        5m, 5min -> 5
        15m, 15min -> 15
        30m, 30min -> 30
        1h, 1hour -> 60
        2h -> 120
        4h -> 240
        1d, 1day -> 1D
        1w, 1week -> 1W
        1M, 1month -> 1M
    """
    timeframe = timeframe.lower().strip()

    # Minute format
    if timeframe.endswith('m') or timeframe.endswith('min'):
        value = timeframe.replace('m', '').replace('min', '').strip()
        return value

    # Hour format
    if timeframe.endswith('h') or timeframe.endswith('hour'):
        value = timeframe.replace('h', '').replace('hour', '').strip()
        try:
            hours = int(value)
            return str(hours * 60)  # Convert to minutes
        except ValueError:
            pass

    # Daily format
    if timeframe.endswith('d') or timeframe.endswith('day'):
        return "1D"

    # Weekly format
    if timeframe.endswith('w') or timeframe.endswith('week'):
        return "1W"

    # Monthly format
    if timeframe.upper().endswith('M') or timeframe.endswith('month'):
        return "1M"

    # Already standardized or unknown
    return timeframe

def normalize_symbol(symbol: str) -> str:
    """
    Normalize symbol format.

    Rules:
        - If exchange prefix exists, keep as is
        - If no prefix, default to BINANCE:
    """
    symbol = symbol.upper().strip()

    if ':' not in symbol:
        return f"BINANCE:{symbol}"

    return symbol

# =============================================================================
# CLI Startup
# =============================================================================

def main():
    """CLI Startup entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="TradingView K-line Data HTTP API Service")
    parser.add_argument("--host", default="0.0.0.0", help="Listen host (Default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Listen port (Default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable hot reload (dev mode)")
    parser.add_argument("--workers", type=int, default=1, help="Worker process count (Default: 1)")

    args = parser.parse_args()

    print("=" * 80)
    print("🚀 TradingView K-line Data HTTP API Service")
    print("=" * 80)
    print(f"\n📡 Service URL: http://{args.host}:{args.port}")
    print(f"📚 API Docs: http://{args.host}:{args.port}/docs")
    print(f"📊 ReDoc: http://{args.host}:{args.port}/redoc")
    print(f"\nExample Request:")
    print(f"  curl \"http://{args.host}:{args.port}/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100\"")
    print(f"  curl \"http://{args.host}:{args.port}/klines?symbol=BTCUSDT&timeframe=15m&count=50\"")
    print(f"  curl \"http://{args.host}:{args.port}/health\"")
    print(f"  curl \"http://{args.host}:{args.port}/stats\"")
    print("\n" + "=" * 80)
    print("Press Ctrl+C to stop service\n")

    uvicorn.run(
        "tradingview.kline_api_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level="info"
    )

if __name__ == "__main__":
    main()
