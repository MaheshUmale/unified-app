#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Module External API Server
Provides RESTful API, WebSocket API, and data management interfaces.
"""

import asyncio
import json
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging

from fastapi import FastAPI, WebSocket, HTTPException, Query, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

from .enhanced_client import EnhancedTradingViewClient, ConnectionState
from .data_cache_manager import DataCacheManager, CacheStatus
from .data_quality_monitor import DataQualityEngine
from tradingview.utils import get_logger

logger = get_logger(__name__)


# ==================== Data Model Definitions ====================

class DataRequest(BaseModel):
    """Data request model"""
    symbol: str = Field(..., description="Trading symbol")
    timeframe: str = Field(..., description="Timeframe")
    count: int = Field(default=500, description="Data point count")
    start_time: Optional[int] = Field(None, description="Start timestamp")
    end_time: Optional[int] = Field(None, description="End timestamp")
    quality_check: bool = Field(default=True, description="Whether to perform quality check")
    use_cache: bool = Field(default=True, description="Whether to use cache")


class KlineData(BaseModel):
    """K-line data model"""
    timestamp: int
    datetime: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataResponse(BaseModel):
    """Market data response model"""
    status: str
    message: str
    data: Dict[str, Any]
    metadata: Dict[str, Any]
    timestamp: int


class HealthStatus(BaseModel):
    """Health status model"""
    status: str
    uptime: float
    connection_state: str
    data_quality_score: float
    cache_status: str
    metrics: Dict[str, Any]


class SubscriptionRequest(BaseModel):
    """Subscription request model"""
    symbols: List[str]
    timeframes: List[str]
    data_types: List[str] = ["kline", "quote"]


# ==================== API Server Class ====================

class TradingViewAPIServer:
    """TradingView API Server"""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize API server"""
        self.config = config or {}
        self.app = FastAPI(
            title="TradingView Data API",
            description="Professional-grade TradingView data source API service",
            version="2.0.0"
        )

        # Add CORS middleware
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Initialize components
        self.client = None
        self.cache_manager = None
        self.quality_engine = None
        self.websocket_connections = set()
        self.subscription_manager = {}

        # Start time
        self.start_time = time.time()

        # Register routes
        self._register_routes()

    async def initialize(self):
        """Initialize service components"""
        try:
            # Initialize enhanced client
            self.client = EnhancedTradingViewClient({
                'auto_reconnect': True,
                'health_monitoring': True,
                'performance_optimization': True
            })

            # Initialize cache manager
            self.cache_manager = DataCacheManager(
                db_path=self.config.get('cache_db_path', 'tradingview_cache.db'),
                max_memory_size=self.config.get('max_memory_cache', 1000)
            )

            # Initialize quality engine
            self.quality_engine = DataQualityEngine()

            # Connect client
            await self.client.connect()

            logger.info("TradingView API server initialized successfully")

        except Exception as e:
            logger.error(f"API server initialization failed: {e}")
            raise

    def _register_routes(self):
        """Register API routes"""

        # ==================== RESTful API ====================

        @self.app.get("/api/v1/health", response_model=HealthStatus)
        async def get_health_status():
            """Get health status"""
            try:
                uptime = time.time() - self.start_time

                # Get connection state
                connection_state = "unknown"
                if self.client and hasattr(self.client, 'monitor'):
                    connection_state = self.client.monitor.state.value

                # Get data quality score
                quality_score = 0.0
                if self.quality_engine:
                    quality_score = self.quality_engine.get_overall_quality_score()

                # Get cache status
                cache_status = "unknown"
                if self.cache_manager:
                    cache_status = self.cache_manager.get_status().value

                # Get detailed metrics
                metrics = {
                    "total_symbols": len(self.subscription_manager),
                    "active_connections": len(self.websocket_connections),
                    "cache_hit_rate": self.cache_manager.get_hit_rate() if self.cache_manager else 0.0,
                    "average_latency": self.client.monitor.get_average_latency() if self.client and hasattr(self.client, 'monitor') else 0.0
                }

                return HealthStatus(
                    status="healthy" if connection_state == "connected" else "unhealthy",
                    uptime=uptime,
                    connection_state=connection_state,
                    data_quality_score=quality_score,
                    cache_status=cache_status,
                    metrics=metrics
                )

            except Exception as e:
                logger.error(f"Failed to get health status: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/v1/data/historical", response_model=MarketDataResponse)
        async def get_historical_data(request: DataRequest):
            """Get historical data"""
            try:
                logger.info(f"Received historical data request: {request.symbol} {request.timeframe}")

                # Check cache
                cached_data = None
                if request.use_cache and self.cache_manager:
                    cached_data = await self.cache_manager.get_historical_data(
                        request.symbol,
                        request.timeframe,
                        request.count
                    )

                if cached_data and cached_data['quality_score'] >= 0.9:
                    logger.info(f"Using cached data: {request.symbol}")
                    return MarketDataResponse(
                        status="success",
                        message="Data from cache",
                        data=cached_data,
                        metadata={
                            "source": "cache",
                            "total_count": len(cached_data.get('klines', [])),
                            "quality_score": cached_data.get('quality_score', 0.0)
                        },
                        timestamp=int(time.time())
                    )

                # Retrieve data from TradingView
                if not self.client:
                    raise HTTPException(status_code=503, detail="TradingView client not connected")

                chart_session = self.client.Session.Chart()

                # Build request parameters
                params = {
                    'symbol': request.symbol,
                    'timeframe': request.timeframe,
                    'count': request.count
                }

                if request.start_time:
                    params['from_timestamp'] = request.start_time
                if request.end_time:
                    params['to_timestamp'] = request.end_time

                # Get data
                raw_data = await chart_session.get_historical_data(**params)

                # Data quality check
                quality_score = 1.0
                if request.quality_check and self.quality_engine:
                    quality_result = await self.quality_engine.validate_kline_data(raw_data)
                    quality_score = quality_result.quality_score

                    if quality_score < 0.8:
                        logger.warning(f"Low data quality: {quality_score:.2f}")

                # Format data
                formatted_data = {
                    'symbol': request.symbol,
                    'timeframe': request.timeframe,
                    'klines': raw_data.get('data', []),
                    'quality_score': quality_score
                }

                # Update cache
                if self.cache_manager and quality_score >= 0.8:
                    await self.cache_manager.store_historical_data(
                        request.symbol,
                        request.timeframe,
                        formatted_data
                    )

                return MarketDataResponse(
                    status="success",
                    message="Data retrieved successfully",
                    data=formatted_data,
                    metadata={
                        "source": "tradingview",
                        "total_count": len(formatted_data.get('klines', [])),
                        "quality_score": quality_score,
                        "cache_updated": True
                    },
                    timestamp=int(time.time())
                )

            except Exception as e:
                logger.error(f"Failed to get historical data: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/v1/symbols", response_model=Dict[str, Any])
        async def get_supported_symbols():
            """Get supported trading symbols"""
            try:
                # Get symbol list from cache
                symbols = []
                if self.cache_manager:
                    symbols = await self.cache_manager.get_cached_symbols()

                return {
                    "status": "success",
                    "data": {
                        "symbols": symbols,
                        "total": len(symbols),
                        "categories": {
                            "crypto": [s for s in symbols if "BINANCE:" in s or "COINBASE:" in s],
                            "forex": [s for s in symbols if "FX:" in s or "OANDA:" in s],
                            "stocks": [s for s in symbols if "NASDAQ:" in s or "NYSE:" in s],
                            "indices": [s for s in symbols if "TVC:" in s]
                        }
                    }
                }

            except Exception as e:
                logger.error(f"Failed to get symbol list: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/v1/cache/stats", response_model=Dict[str, Any])
        async def get_cache_statistics():
            """Get cache statistics info"""
            try:
                if not self.cache_manager:
                    raise HTTPException(status_code=503, detail="Cache manager not initialized")

                stats = await self.cache_manager.get_statistics()

                return {
                    "status": "success",
                    "data": stats
                }

            except Exception as e:
                logger.error(f"Failed to get cache statistics: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # ==================== WebSocket API ====================

        @self.app.websocket("/ws/realtime")
        async def websocket_realtime_data(websocket: WebSocket):
            """Real-time data WebSocket endpoint"""
            await websocket.accept()
            self.websocket_connections.add(websocket)

            try:
                logger.info("New WebSocket connection established")

                while True:
                    # Receive message from client
                    data = await websocket.receive_text()
                    message = json.loads(data)

                    message_type = message.get('type')

                    if message_type == 'subscribe':
                        # Handle subscription request
                        await self._handle_subscribe(websocket, message)
                    elif message_type == 'unsubscribe':
                        # Handle unsubscription
                        await self._handle_unsubscribe(websocket, message)
                    elif message_type == 'ping':
                        # Heartbeat response
                        await websocket.send_text(json.dumps({
                            'type': 'pong',
                            'timestamp': int(time.time())
                        }))

            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
            finally:
                self.websocket_connections.remove(websocket)
                logger.info("WebSocket connection closed")

        @self.app.delete("/api/v1/cache/clear")
        async def clear_cache():
            """Clear all cache"""
            try:
                if not self.cache_manager:
                    raise HTTPException(status_code=503, detail="Cache manager not initialized")

                await self.cache_manager.clear_all_cache()

                return {
                    "status": "success",
                    "message": "Cache cleared"
                }

            except Exception as e:
                logger.error(f"Failed to clear cache: {e}")
                raise HTTPException(status_code=500, detail=str(e))

    async def _handle_subscribe(self, websocket: WebSocket, message: Dict[str, Any]):
        """Handle subscription request"""
        try:
            symbols = message.get('symbols', [])
            timeframes = message.get('timeframes', ['1'])

            for symbol in symbols:
                for tf in timeframes:
                    subscription_key = f"{symbol}:{tf}"

                    if subscription_key not in self.subscription_manager:
                        self.subscription_manager[subscription_key] = set()

                    self.subscription_manager[subscription_key].add(websocket)

            # Send confirmation message
            await websocket.send_text(json.dumps({
                'type': 'subscribed',
                'symbols': symbols,
                'timeframes': timeframes,
                'timestamp': int(time.time())
            }))

            logger.info(f"WebSocket subscription successful: {symbols}")

        except Exception as e:
            logger.error(f"Failed to handle subscription request: {e}")

    async def _handle_unsubscribe(self, websocket: WebSocket, message: Dict[str, Any]):
        """Handle unsubscription request"""
        try:
            symbols = message.get('symbols', [])
            timeframes = message.get('timeframes', ['1'])

            for symbol in symbols:
                for tf in timeframes:
                    subscription_key = f"{symbol}:{tf}"

                    if subscription_key in self.subscription_manager:
                        self.subscription_manager[subscription_key].discard(websocket)

                        # If no more subscribers, remove the key
                        if not self.subscription_manager[subscription_key]:
                            del self.subscription_manager[subscription_key]

            # Send confirmation message
            await websocket.send_text(json.dumps({
                'type': 'unsubscribed',
                'symbols': symbols,
                'timeframes': timeframes,
                'timestamp': int(time.time())
            }))

            logger.info(f"WebSocket unsubscription successful: {symbols}")

        except Exception as e:
            logger.error(f"Failed to handle unsubscription request: {e}")

    async def broadcast_realtime_data(self, symbol: str, timeframe: str, data: Dict[str, Any]):
        """Broadcast real-time data"""
        subscription_key = f"{symbol}:{timeframe}"

        if subscription_key in self.subscription_manager:
            message = json.dumps({
                'type': 'realtime_data',
                'symbol': symbol,
                'timeframe': timeframe,
                'data': data,
                'timestamp': int(time.time())
            })

            # Send data to all subscribers
            disconnected_websockets = set()
            for websocket in self.subscription_manager[subscription_key]:
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    logger.warning(f"Failed to send data to WebSocket: {e}")
                    disconnected_websockets.add(websocket)

            # Cleanup disconnected websockets
            for ws in disconnected_websockets:
                self.subscription_manager[subscription_key].discard(ws)

    async def start_server(self, host: str = "0.0.0.0", port: int = 8000):
        """Start API server"""
        logger.info(f"Starting TradingView API server: {host}:{port}")

        # Initialize components
        await self.initialize()

        # Start server
        config = uvicorn.Config(
            self.app,
            host=host,
            port=port,
            log_level="info",
            access_log=True
        )
        server = uvicorn.Server(config)
        await server.serve()


# ==================== Startup Script ====================

async def main():
    """Main function"""
    config = {
        'cache_db_path': 'data/tradingview_cache.db',
        'max_memory_cache': 5000,
        'api_host': '0.0.0.0',
        'api_port': 8000
    }

    server = TradingViewAPIServer(config)
    await server.start_server(
        host=config['api_host'],
        port=config['api_port']
    )


if __name__ == "__main__":
    asyncio.run(main())
