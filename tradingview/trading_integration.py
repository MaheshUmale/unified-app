#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView and trading_core Integration Adapter
Implements data format conversion, real-time data adaptation, and system integration.
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum, auto

from tradingview.utils import get_logger

logger = get_logger(__name__)


class DataSourceStatus(Enum):
    """Data source status"""
    INITIALIZING = auto()
    CONNECTED = auto()
    DISCONNECTED = auto()
    ERROR = auto()
    RECONNECTING = auto()


class DataQuality(Enum):
    """Data quality level"""
    EXCELLENT = auto()  # Excellent
    GOOD = auto()       # Good
    FAIR = auto()       # Fair
    POOR = auto()       # Poor
    CRITICAL = auto()   # Critical


@dataclass
class MarketDataPoint:
    """Standardized market data point"""
    symbol: str
    timeframe: str
    timestamp: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    # Data quality info
    quality_score: float = 1.0
    source: str = "tradingview"
    latency_ms: float = 0.0

    # Metadata
    is_complete: bool = True
    is_realtime: bool = False
    sequence_id: Optional[int] = None


@dataclass
class DataSourceMetrics:
    """Data source metrics"""
    symbol: str
    connection_status: DataSourceStatus = DataSourceStatus.DISCONNECTED
    last_update_time: float = 0.0

    # Performance metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_latency_ms: float = 0.0

    # Data quality metrics
    data_quality: DataQuality = DataQuality.EXCELLENT
    missing_data_count: int = 0
    invalid_data_count: int = 0

    # Connection metrics
    connection_uptime: float = 0.0
    reconnection_count: int = 0
    last_error: Optional[str] = None


class TradingViewDataConverter:
    """TradingView data converter"""

    def __init__(self):
        self.conversion_stats = {
            'total_conversions': 0,
            'successful_conversions': 0,
            'failed_conversions': 0
        }

    def convert_kline_to_market_data(self, tv_kline: Dict[str, Any],
                                   symbol: str, timeframe: str = "15m") -> Optional[MarketDataPoint]:
        """
        Convert TradingView K-line data to MarketDataPoint.

        Args:
            tv_kline: TradingView K-line data
            symbol: Trading symbol
            timeframe: Timeframe

        Returns:
            MarketDataPoint: Standardized market data point
        """
        try:
            self.conversion_stats['total_conversions'] += 1

            # Validate required fields
            required_fields = ['time', 'open', 'high', 'low', 'close']
            if not all(field in tv_kline for field in required_fields):
                logger.warning(f"TradingView data missing required fields: {tv_kline}")
                return None

            # Type conversion and validation
            timestamp = float(tv_kline['time'])
            open_price = float(tv_kline['open'])
            high_price = float(tv_kline['high'])
            low_price = float(tv_kline['low'])
            close_price = float(tv_kline['close'])
            volume = float(tv_kline.get('volume', 0))

            # Basic validation
            if not self._validate_ohlc_data(open_price, high_price, low_price, close_price):
                logger.warning(f"TradingView OHLC validation failed: {tv_kline}")
                self.conversion_stats['failed_conversions'] += 1
                return None

            # Calculate quality score
            quality_score = self._calculate_quality_score(tv_kline)

            # Check if real-time (within 5 minutes)
            current_time = time.time()
            is_realtime = (current_time - timestamp) < 300

            market_data = MarketDataPoint(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=timestamp,
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=volume,
                quality_score=quality_score,
                source="tradingview",
                is_realtime=is_realtime,
                is_complete=True
            )

            self.conversion_stats['successful_conversions'] += 1
            return market_data

        except (ValueError, TypeError, KeyError) as e:
            logger.error(f"TradingView data conversion failed: {e}, raw: {tv_kline}")
            self.conversion_stats['failed_conversions'] += 1
            return None
        except Exception as e:
            logger.error(f"TradingView data conversion exception: {e}")
            self.conversion_stats['failed_conversions'] += 1
            return None

    def convert_to_chanpy_format(self, market_data_list: List[MarketDataPoint]) -> Dict[str, List]:
        """
        Convert list of MarketDataPoint to chanpy format.

        Args:
            market_data_list: List of MarketDataPoint

        Returns:
            Dict: Data in chanpy format
        """
        try:
            # Group by timeframe
            timeframe_data = defaultdict(list)

            for data_point in market_data_list:
                # Convert to chanpy KLine_Unit format
                kline_dict = {
                    'time': data_point.timestamp,
                    'open': data_point.open,
                    'high': data_point.high,
                    'low': data_point.low,
                    'close': data_point.close,
                    'volume': data_point.volume
                }

                # Categorize by timeframe
                timeframe_key = self._map_timeframe_to_chanpy(data_point.timeframe)
                timeframe_data[timeframe_key].append(kline_dict)

            # Sort by timestamp
            for timeframe in timeframe_data:
                timeframe_data[timeframe].sort(key=lambda x: x['time'])

            return dict(timeframe_data)

        except Exception as e:
            logger.error(f"chanpy format conversion failed: {e}")
            return {}

    def convert_to_trading_core_format(self, market_data: MarketDataPoint) -> Dict[str, Any]:
        """
        Convert to trading_core standard format.

        Args:
            market_data: MarketDataPoint

        Returns:
            Dict: Data in trading_core format
        """
        try:
            return {
                'symbol': market_data.symbol,
                'timeframe': market_data.timeframe,
                'timestamp': market_data.timestamp,
                'datetime': datetime.fromtimestamp(market_data.timestamp).isoformat(),
                'ohlcv': {
                    'open': market_data.open,
                    'high': market_data.high,
                    'low': market_data.low,
                    'close': market_data.close,
                    'volume': market_data.volume
                },
                'metadata': {
                    'quality_score': market_data.quality_score,
                    'source': market_data.source,
                    'latency_ms': market_data.latency_ms,
                    'is_realtime': market_data.is_realtime,
                    'is_complete': market_data.is_complete
                }
            }

        except Exception as e:
            logger.error(f"trading_core format conversion failed: {e}")
            return {}

    def _validate_ohlc_data(self, open_price: float, high_price: float,
                          low_price: float, close_price: float) -> bool:
        """Validate logical OHLC relationship"""
        try:
            # Check positive prices
            if any(price <= 0 for price in [open_price, high_price, low_price, close_price]):
                return False

            # Check high/low relationship
            if high_price < max(open_price, close_price):
                return False
            if low_price > min(open_price, close_price):
                return False

            # Check for extreme price movements
            price_range = high_price - low_price
            avg_price = (high_price + low_price) / 2
            if avg_price > 0 and (price_range / avg_price) > 0.5:  # 50% price movement
                logger.warning("Extreme price movement detected")
                return False

            return True

        except Exception:
            return False

    def _calculate_quality_score(self, kline_data: Dict) -> float:
        """Calculate data quality score"""
        try:
            score = 1.0

            # Check completeness
            required_fields = ['time', 'open', 'high', 'low', 'close']
            missing_fields = sum(1 for field in required_fields if field not in kline_data)
            score *= (1 - missing_fields * 0.2)

            # Check volume
            if 'volume' not in kline_data or kline_data['volume'] <= 0:
                score *= 0.9  # Deduct 10% for missing/zero volume

            # Check freshness
            current_time = time.time()
            time_diff = current_time - float(kline_data.get('time', 0))
            if time_diff > 3600:  # > 1 hour
                score *= 0.8
            elif time_diff > 300:  # > 5 minutes
                score *= 0.95

            return max(0.0, min(1.0, score))

        except Exception:
            return 0.5  # Default medium quality

    def _map_timeframe_to_chanpy(self, timeframe: str) -> str:
        """Map timeframe to chanpy format"""
        mapping = {
            '1m': 'K_1M',
            '5m': 'K_5M',
            '15m': 'K_15M',
            '30m': 'K_30M',
            '1h': 'K_1H',
            '4h': 'K_4H',
            '1d': 'K_DAY',
            '1w': 'K_WEEK'
        }
        return mapping.get(timeframe, 'K_15M')

    def get_conversion_stats(self) -> Dict[str, Any]:
        """Get conversion statistics information"""
        total = self.conversion_stats['total_conversions']
        if total == 0:
            return {'success_rate': 0.0, **self.conversion_stats}

        success_rate = self.conversion_stats['successful_conversions'] / total
        return {
            'success_rate': success_rate,
            **self.conversion_stats
        }


class RealtimeDataAdapter:
    """Real-time data adapter"""

    def __init__(self, buffer_size: int = 1000):
        self.buffer_size = buffer_size
        self.data_buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=buffer_size))
        self.subscribers: Dict[str, List[Callable]] = defaultdict(list)
        self.metrics: Dict[str, DataSourceMetrics] = {}
        self.converter = TradingViewDataConverter()

        # Real-time stats
        self.realtime_stats = {
            'messages_received': 0,
            'messages_processed': 0,
            'messages_dropped': 0,
            'average_processing_time_ms': 0.0
        }

    async def process_realtime_update(self, symbol: str, tv_data: Dict[str, Any]) -> bool:
        """
        Process real-time data update.

        Args:
            symbol: Trading symbol
            tv_data: Raw TradingView data

        Returns:
            bool: Success or failure
        """
        try:
            start_time = time.perf_counter()
            self.realtime_stats['messages_received'] += 1

            # Initialize or update metrics
            if symbol not in self.metrics:
                self.metrics[symbol] = DataSourceMetrics(symbol=symbol)

            metrics = self.metrics[symbol]
            metrics.total_requests += 1

            # Convert data format
            market_data = self.converter.convert_kline_to_market_data(tv_data, symbol)

            if not market_data:
                metrics.failed_requests += 1
                metrics.invalid_data_count += 1
                self.realtime_stats['messages_dropped'] += 1
                return False

            # Set latency info
            processing_time = (time.perf_counter() - start_time) * 1000
            market_data.latency_ms = processing_time

            # Update metrics
            metrics.successful_requests += 1
            metrics.last_update_time = time.time()
            metrics.connection_status = DataSourceStatus.CONNECTED

            # Calculate average latency
            if metrics.successful_requests > 0:
                metrics.average_latency_ms = (
                    (metrics.average_latency_ms * (metrics.successful_requests - 1) + processing_time)
                    / metrics.successful_requests
                )

            # Update data quality rating
            self._update_data_quality(metrics, market_data.quality_score)

            # Add to buffer
            self.data_buffers[symbol].append(market_data)

            # Notify subscribers
            await self._notify_subscribers(symbol, market_data)

            # Update stats
            self.realtime_stats['messages_processed'] += 1
            self._update_processing_time_stats(processing_time)

            logger.debug(f"Real-time update processed: {symbol}, latency: {processing_time:.2f}ms")
            return True

        except Exception as e:
            logger.error(f"Failed to process real-time update for {symbol}: {e}")
            if symbol in self.metrics:
                self.metrics[symbol].failed_requests += 1
                self.metrics[symbol].last_error = str(e)

            self.realtime_stats['messages_dropped'] += 1
            return False

    def subscribe_to_symbol(self, symbol: str, callback: Callable[[MarketDataPoint], None]) -> bool:
        """
        Subscribe to symbol updates.

        Args:
            symbol: Trading symbol
            callback: Data callback function

        Returns:
            bool: Success or failure
        """
        try:
            self.subscribers[symbol].append(callback)
            logger.info(f"Subscribed to {symbol}, active subscribers: {len(self.subscribers[symbol])}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to {symbol}: {e}")
            return False

    def unsubscribe_from_symbol(self, symbol: str, callback: Callable[[MarketDataPoint], None]) -> bool:
        """
        Unsubscribe from symbol updates.

        Args:
            symbol: Trading symbol
            callback: Callback function to remove

        Returns:
            bool: Success or failure
        """
        try:
            if symbol in self.subscribers and callback in self.subscribers[symbol]:
                self.subscribers[symbol].remove(callback)
                logger.info(f"Unsubscribed from {symbol}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to unsubscribe from {symbol}: {e}")
            return False

    async def _notify_subscribers(self, symbol: str, market_data: MarketDataPoint) -> None:
        """Notify subscribers of update"""
        try:
            callbacks = self.subscribers.get(symbol, [])

            if callbacks:
                # Notify all subscribers concurrently
                tasks = []
                for callback in callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            tasks.append(asyncio.create_task(callback(market_data)))
                        else:
                            # Synchronous callback in executor
                            tasks.append(asyncio.create_task(
                                asyncio.get_event_loop().run_in_executor(None, callback, market_data)
                            ))
                    except Exception as e:
                        logger.error(f"Failed to create callback task: {e}")

                # Wait for all callbacks
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            logger.error(f"Subscriber notification failed: {e}")

    def _update_data_quality(self, metrics: DataSourceMetrics, quality_score: float) -> None:
        """Update data quality rating"""
        try:
            if quality_score >= 0.95:
                metrics.data_quality = DataQuality.EXCELLENT
            elif quality_score >= 0.85:
                metrics.data_quality = DataQuality.GOOD
            elif quality_score >= 0.70:
                metrics.data_quality = DataQuality.FAIR
            elif quality_score >= 0.50:
                metrics.data_quality = DataQuality.POOR
            else:
                metrics.data_quality = DataQuality.CRITICAL

        except Exception as e:
            logger.error(f"Failed to update data quality rating: {e}")

    def _update_processing_time_stats(self, processing_time: float) -> None:
        """Update processing time statistics"""
        try:
            processed_count = self.realtime_stats['messages_processed']
            if processed_count > 0:
                current_avg = self.realtime_stats['average_processing_time_ms']
                new_avg = ((current_avg * (processed_count - 1)) + processing_time) / processed_count
                self.realtime_stats['average_processing_time_ms'] = new_avg

        except Exception as e:
            logger.error(f"Failed to update processing time stats: {e}")

    def get_latest_data(self, symbol: str) -> Optional[MarketDataPoint]:
        """Get most recent data point"""
        try:
            buffer = self.data_buffers.get(symbol)
            if buffer and len(buffer) > 0:
                return buffer[-1]
            return None

        except Exception as e:
            logger.error(f"Failed to get latest data for {symbol}: {e}")
            return None

    def get_historical_buffer(self, symbol: str, count: int = 100) -> List[MarketDataPoint]:
        """Get history from buffer"""
        try:
            buffer = self.data_buffers.get(symbol, deque())
            return list(buffer)[-count:] if buffer else []

        except Exception as e:
            logger.error(f"Failed to get history from buffer for {symbol}: {e}")
            return []

    def get_symbol_metrics(self, symbol: str) -> Optional[DataSourceMetrics]:
        """Get metrics for a specific symbol"""
        return self.metrics.get(symbol)

    def get_all_metrics(self) -> Dict[str, DataSourceMetrics]:
        """Get all symbol metrics"""
        return self.metrics.copy()

    def get_realtime_stats(self) -> Dict[str, Any]:
        """Get overall real-time stats"""
        stats = self.realtime_stats.copy()

        # Calculate success rates
        total_received = stats['messages_received']
        if total_received > 0:
            stats['success_rate'] = stats['messages_processed'] / total_received
            stats['drop_rate'] = stats['messages_dropped'] / total_received
        else:
            stats['success_rate'] = 0.0
            stats['drop_rate'] = 0.0

        return stats


class TradingCoreIntegrationManager:
    """Manager for trading_core integration"""

    def __init__(self):
        self.converter = TradingViewDataConverter()
        self.realtime_adapter = RealtimeDataAdapter()
        self.integration_status = DataSourceStatus.INITIALIZING

        # Data pipeline
        self.data_pipeline: List[Callable] = []
        self.error_handlers: List[Callable] = []

        # Integration stats
        self.integration_stats = {
            'data_throughput': 0,
            'processing_errors': 0,
            'pipeline_latency_ms': 0.0,
            'active_subscriptions': 0
        }

    async def initialize_integration(self) -> bool:
        """Initialize the integration layer"""
        try:
            self.integration_status = DataSourceStatus.INITIALIZING

            # Initialize converter
            logger.info("Initializing data converter...")

            # Initialize real-time adapter
            logger.info("Initializing real-time data adapter...")

            self.integration_status = DataSourceStatus.CONNECTED
            logger.info("✅ trading_core integration initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ trading_core integration failed: {e}")
            self.integration_status = DataSourceStatus.ERROR
            return False

    def add_data_pipeline_stage(self, processor: Callable[[MarketDataPoint], MarketDataPoint]) -> None:
        """Add a stage to the data pipeline"""
        self.data_pipeline.append(processor)
        logger.info(f"Added pipeline stage: {processor.__name__}")

    def add_error_handler(self, handler: Callable[[Exception, str], None]) -> None:
        """Add an error handler"""
        self.error_handlers.append(handler)
        logger.info(f"Added error handler: {handler.__name__}")

    async def process_data_through_pipeline(self, market_data: MarketDataPoint) -> Optional[MarketDataPoint]:
        """Process data through the pipeline"""
        try:
            start_time = time.perf_counter()
            processed_data = market_data

            # Pass data through all stages
            for stage in self.data_pipeline:
                try:
                    if asyncio.iscoroutinefunction(stage):
                        processed_data = await stage(processed_data)
                    else:
                        processed_data = stage(processed_data)

                    if processed_data is None:
                        logger.warning("Data filtered out in pipeline")
                        return None

                except Exception as e:
                    logger.error(f"Pipeline stage failed: {stage.__name__}: {e}")
                    await self._handle_pipeline_error(e, stage.__name__)
                    return None

            # Update latency stats
            pipeline_time = (time.perf_counter() - start_time) * 1000
            self._update_pipeline_stats(pipeline_time)

            return processed_data

        except Exception as e:
            logger.error(f"Pipeline processing failed: {e}")
            await self._handle_pipeline_error(e, "pipeline")
            return None

    async def _handle_pipeline_error(self, error: Exception, stage_name: str) -> None:
        """Handle error within the pipeline"""
        try:
            self.integration_stats['processing_errors'] += 1

            for handler in self.error_handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(error, stage_name)
                    else:
                        handler(error, stage_name)
                except Exception as e:
                    logger.error(f"Error handler failed: {e}")

        except Exception as e:
            logger.error(f"Pipeline error handling failed: {e}")

    def _update_pipeline_stats(self, processing_time: float) -> None:
        """Update pipeline statistics"""
        try:
            self.integration_stats['data_throughput'] += 1

            # Update average processing latency
            current_latency = self.integration_stats['pipeline_latency_ms']
            throughput = self.integration_stats['data_throughput']

            if throughput > 0:
                new_latency = ((current_latency * (throughput - 1)) + processing_time) / throughput
                self.integration_stats['pipeline_latency_ms'] = new_latency

        except Exception as e:
            logger.error(f"Failed to update pipeline statistics: {e}")

    def get_integration_status(self) -> Dict[str, Any]:
        """Get integration layer status"""
        return {
            'status': self.integration_status.name,
            'converter_stats': self.converter.get_conversion_stats(),
            'realtime_stats': self.realtime_adapter.get_realtime_stats(),
            'integration_stats': self.integration_stats,
            'pipeline_stages': len(self.data_pipeline),
            'error_handlers': len(self.error_handlers)
        }

    def get_symbol_summary(self) -> Dict[str, Any]:
        """Get summary of symbols"""
        all_metrics = self.realtime_adapter.get_all_metrics()

        summary = {
            'total_symbols': len(all_metrics),
            'connected_symbols': sum(1 for m in all_metrics.values()
                                   if m.connection_status == DataSourceStatus.CONNECTED),
            'quality_distribution': defaultdict(int),
            'average_latency_ms': 0.0,
            'total_throughput': 0
        }

        total_latency = 0
        total_requests = 0

        for metrics in all_metrics.values():
            summary['quality_distribution'][metrics.data_quality.name] += 1
            total_latency += metrics.average_latency_ms * metrics.successful_requests
            total_requests += metrics.successful_requests
            summary['total_throughput'] += metrics.successful_requests

        if total_requests > 0:
            summary['average_latency_ms'] = total_latency / total_requests

        summary['quality_distribution'] = dict(summary['quality_distribution'])

        return summary


# Helper function
def create_tradingview_integration() -> TradingCoreIntegrationManager:
    """Create a new integration manager"""
    return TradingCoreIntegrationManager()


async def test_data_conversion():
    """Test data conversion functionality"""
    converter = TradingViewDataConverter()

    # Mock TradingView data
    tv_data = {
        'time': time.time(),
        'open': 50000.0,
        'high': 51000.0,
        'low': 49500.0,
        'close': 50500.0,
        'volume': 1000.0
    }

    # Convert data
    market_data = converter.convert_kline_to_market_data(tv_data, "BTC/USDT")

    if market_data:
        print(f"✅ Conversion successful: {market_data.symbol} {market_data.close}")

        # Convert to trading_core format
        tc_format = converter.convert_to_trading_core_format(market_data)
        print(f"trading_core format: {tc_format}")

        # Convert to chanpy format
        chanpy_format = converter.convert_to_chanpy_format([market_data])
        print(f"chanpy format: {chanpy_format}")
    else:
        print("❌ Conversion failed")


if __name__ == "__main__":
    # Run test
    asyncio.run(test_data_conversion())
