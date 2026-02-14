#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Real-time Data Adapter
Handles real-time data streams, cache management, and event dispatching.
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Any, Callable, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum, auto
import threading
from concurrent.futures import ThreadPoolExecutor

from tradingview.utils import get_logger

logger = get_logger(__name__)


class SubscriptionType(Enum):
    """Subscription type"""
    KLINE_1M = "1m"
    KLINE_5M = "5m"
    KLINE_15M = "15m"
    KLINE_1H = "1h"
    KLINE_1D = "1d"
    QUOTE_REALTIME = "quote"
    ORDER_BOOK = "orderbook"


class EventType(Enum):
    """Event type"""
    DATA_UPDATE = auto()
    CONNECTION_STATUS = auto()
    SUBSCRIPTION_STATUS = auto()
    DATA_QUALITY_ALERT = auto()
    PERFORMANCE_ALERT = auto()


@dataclass
class SubscriptionInfo:
    """Subscription info"""
    symbol: str
    subscription_type: SubscriptionType
    callback: Callable
    created_time: float = field(default_factory=time.time)
    is_active: bool = True
    error_count: int = 0
    last_update_time: float = 0.0


@dataclass
class RealtimeEvent:
    """Real-time event"""
    event_type: EventType
    symbol: str
    data: Any
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class RealtimeDataBuffer:
    """Real-time data buffer"""

    def __init__(self, max_size: int = 1000, max_age_seconds: int = 3600):
        self.max_size = max_size
        self.max_age_seconds = max_age_seconds
        self.data_buffer: deque = deque(maxlen=max_size)
        self.index_by_timestamp: Dict[int, int] = {}
        self.lock = threading.RLock()

        # Statistics
        self.stats = {
            'total_added': 0,
            'total_expired': 0,
            'current_size': 0,
            'oldest_timestamp': 0,
            'newest_timestamp': 0
        }

    def add_data(self, data: Any, timestamp: Optional[float] = None) -> bool:
        """Add data to buffer"""
        try:
            with self.lock:
                if timestamp is None:
                    timestamp = time.time()

                # Check if data is expired
                if time.time() - timestamp > self.max_age_seconds:
                    return False

                # Add data
                self.data_buffer.append((timestamp, data))
                self.stats['total_added'] += 1
                self.stats['current_size'] = len(self.data_buffer)

                # Update timestamp range
                if self.stats['oldest_timestamp'] == 0:
                    self.stats['oldest_timestamp'] = timestamp
                self.stats['newest_timestamp'] = timestamp

                # Cleanup expired data
                self._cleanup_expired_data()

                return True

        except Exception as e:
            logger.error(f"Failed to add data to buffer: {e}")
            return False

    def get_latest_data(self, count: int = 1) -> List[Tuple[float, Any]]:
        """Get latest data"""
        try:
            with self.lock:
                if not self.data_buffer:
                    return []

                # Return latest count items
                return list(self.data_buffer)[-count:]

        except Exception as e:
            logger.error(f"Failed to get latest data: {e}")
            return []

    def get_data_in_range(self, start_time: float, end_time: float) -> List[Tuple[float, Any]]:
        """Get data within time range"""
        try:
            with self.lock:
                result = []
                for timestamp, data in self.data_buffer:
                    if start_time <= timestamp <= end_time:
                        result.append((timestamp, data))

                return result

        except Exception as e:
            logger.error(f"Failed to get data in range: {e}")
            return []

    def _cleanup_expired_data(self) -> None:
        """Cleanup expired data"""
        try:
            current_time = time.time()
            expired_count = 0

            # Remove from left
            while (self.data_buffer and
                   current_time - self.data_buffer[0][0] > self.max_age_seconds):
                self.data_buffer.popleft()
                expired_count += 1

            self.stats['total_expired'] += expired_count
            self.stats['current_size'] = len(self.data_buffer)

            # Update oldest timestamp
            if self.data_buffer:
                self.stats['oldest_timestamp'] = self.data_buffer[0][0]
            else:
                self.stats['oldest_timestamp'] = 0

        except Exception as e:
            logger.error(f"Failed to cleanup expired data: {e}")

    def get_buffer_stats(self) -> Dict[str, Any]:
        """Get buffer statistics"""
        with self.lock:
            stats = self.stats.copy()
            if stats['current_size'] > 0:
                stats['data_age_seconds'] = time.time() - stats['oldest_timestamp']
            else:
                stats['data_age_seconds'] = 0

            return stats


class EventDispatcher:
    """Event Dispatcher"""

    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.event_handlers: Dict[EventType, List[Callable]] = defaultdict(list)
        self.event_queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self.is_running = False
        self.dispatch_task: Optional[asyncio.Task] = None

        # Event statistics
        self.event_stats = {
            'events_received': 0,
            'events_dispatched': 0,
            'events_failed': 0,
            'queue_size': 0,
            'average_dispatch_time_ms': 0.0
        }

    async def start(self) -> None:
        """Start event dispatcher"""
        if self.is_running:
            return

        self.is_running = True
        self.dispatch_task = asyncio.create_task(self._dispatch_loop())
        logger.info("Event dispatcher started")

    async def stop(self) -> None:
        """Stop event dispatcher"""
        self.is_running = False

        if self.dispatch_task:
            self.dispatch_task.cancel()
            try:
                await self.dispatch_task
            except asyncio.CancelledError:
                pass

        # Shutdown executor
        self.executor.shutdown(wait=True)
        logger.info("Event dispatcher stopped")

    def register_handler(self, event_type: EventType, handler: Callable[[RealtimeEvent], None]) -> None:
        """Register event handler"""
        self.event_handlers[event_type].append(handler)
        logger.info(f"Registered event handler: {event_type.name}")

    def unregister_handler(self, event_type: EventType, handler: Callable) -> bool:
        """Unregister event handler"""
        try:
            self.event_handlers[event_type].remove(handler)
            logger.info(f"Unregistered event handler: {event_type.name}")
            return True
        except ValueError:
            logger.warning(f"Handler not found for unregistration: {event_type.name}")
            return False

    async def dispatch_event(self, event: RealtimeEvent) -> bool:
        """Dispatch event"""
        try:
            if not self.is_running:
                return False

            # Add to queue
            await self.event_queue.put(event)
            self.event_stats['events_received'] += 1
            self.event_stats['queue_size'] = self.event_queue.qsize()

            return True

        except asyncio.QueueFull:
            logger.warning("Event queue full, dropping event")
            self.event_stats['events_failed'] += 1
            return False
        except Exception as e:
            logger.error(f"Event dispatch failed: {e}")
            self.event_stats['events_failed'] += 1
            return False

    async def _dispatch_loop(self) -> None:
        """Main dispatch loop"""
        while self.is_running:
            try:
                # Get event
                event = await asyncio.wait_for(self.event_queue.get(), timeout=0.1)

                start_time = time.perf_counter()

                # Get handlers
                handlers = self.event_handlers.get(event.event_type, [])

                if handlers:
                    # Execute all handlers concurrently
                    tasks = []
                    for handler in handlers:
                        try:
                            if asyncio.iscoroutinefunction(handler):
                                tasks.append(asyncio.create_task(handler(event)))
                            else:
                                # Synchronous handlers run in executor
                                tasks.append(asyncio.create_task(
                                    asyncio.get_event_loop().run_in_executor(
                                        self.executor, handler, event
                                    )
                                ))
                        except Exception as e:
                            logger.error(f"Failed to create event handler task: {e}")

                    # Wait for all handlers
                    if tasks:
                        results = await asyncio.gather(*tasks, return_exceptions=True)

                        # Check results
                        for i, result in enumerate(results):
                            if isinstance(result, Exception):
                                logger.error(f"Event handler {i} failed: {result}")

                # Update stats
                dispatch_time = (time.perf_counter() - start_time) * 1000
                self.event_stats['events_dispatched'] += 1
                self._update_dispatch_time_stats(dispatch_time)
                self.event_stats['queue_size'] = self.event_queue.qsize()

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Dispatch loop error: {e}")
                self.event_stats['events_failed'] += 1
                await asyncio.sleep(0.01)

    def _update_dispatch_time_stats(self, dispatch_time: float) -> None:
        """Update dispatch time statistics"""
        try:
            dispatched_count = self.event_stats['events_dispatched']
            if dispatched_count > 0:
                current_avg = self.event_stats['average_dispatch_time_ms']
                new_avg = ((current_avg * (dispatched_count - 1)) + dispatch_time) / dispatched_count
                self.event_stats['average_dispatch_time_ms'] = new_avg
        except Exception as e:
            logger.error(f"Failed to update dispatch time stats: {e}")

    def get_event_stats(self) -> Dict[str, Any]:
        """Get event statistics"""
        stats = self.event_stats.copy()
        stats['handler_counts'] = {
            event_type.name: len(handlers)
            for event_type, handlers in self.event_handlers.items()
        }
        return stats


class AdvancedRealtimeAdapter:
    """Advanced Real-time Data Adapter"""

    def __init__(self, buffer_size: int = 1000, max_workers: int = 4):
        # Components
        self.subscriptions: Dict[str, SubscriptionInfo] = {}
        self.data_buffers: Dict[str, RealtimeDataBuffer] = {}
        self.event_dispatcher = EventDispatcher(max_workers=max_workers)

        # Configuration
        self.buffer_size = buffer_size
        self.is_running = False

        # Monitoring
        self.performance_monitor = PerformanceMonitor()
        self.quality_monitor = DataQualityMonitor()

        # Status
        self.connection_status = defaultdict(lambda: False)

    async def initialize(self) -> bool:
        """Initialize adapter"""
        try:
            # Start dispatcher
            await self.event_dispatcher.start()

            # Start performance monitoring
            await self.performance_monitor.start()

            # Start quality monitoring
            await self.quality_monitor.start()

            self.is_running = True
            logger.info("✅ Advanced Real-time Data Adapter initialized")
            return True

        except Exception as e:
            logger.error(f"❌ Advanced Real-time Data Adapter failed to initialize: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown adapter"""
        try:
            self.is_running = False

            # Stop monitors
            await self.performance_monitor.stop()
            await self.quality_monitor.stop()

            # Stop dispatcher
            await self.event_dispatcher.stop()

            # Cleanup subscriptions
            self.subscriptions.clear()
            self.data_buffers.clear()

            logger.info("Advanced Real-time Data Adapter shutdown completed")

        except Exception as e:
            logger.error(f"Failed to shutdown adapter: {e}")

    async def subscribe_symbol_data(self, symbol: str, subscription_type: SubscriptionType,
                                  callback: Callable[[str, Any], None]) -> bool:
        """Subscribe to symbol data"""
        try:
            subscription_key = f"{symbol}_{subscription_type.value}"

            # Check existing
            if subscription_key in self.subscriptions:
                logger.warning(f"Symbol {symbol} already subscribed to {subscription_type.value}")
                return True

            # Create subscription
            subscription = SubscriptionInfo(
                symbol=symbol,
                subscription_type=subscription_type,
                callback=callback
            )

            self.subscriptions[subscription_key] = subscription

            # Create buffer
            if symbol not in self.data_buffers:
                self.data_buffers[symbol] = RealtimeDataBuffer(max_size=self.buffer_size)

            # Dispatch event
            await self.event_dispatcher.dispatch_event(RealtimeEvent(
                event_type=EventType.SUBSCRIPTION_STATUS,
                symbol=symbol,
                data={'status': 'subscribed', 'type': subscription_type.value}
            ))

            logger.info(f"✅ Subscription successful: {symbol} {subscription_type.value}")
            return True

        except Exception as e:
            logger.error(f"Subscription failed for {symbol}: {e}")
            return False

    async def unsubscribe_symbol_data(self, symbol: str, subscription_type: SubscriptionType) -> bool:
        """Unsubscribe from symbol data"""
        try:
            subscription_key = f"{symbol}_{subscription_type.value}"

            if subscription_key not in self.subscriptions:
                logger.warning(f"Subscription not found: {symbol} {subscription_type.value}")
                return False

            # Remove subscription
            del self.subscriptions[subscription_key]

            # Dispatch event
            await self.event_dispatcher.dispatch_event(RealtimeEvent(
                event_type=EventType.SUBSCRIPTION_STATUS,
                symbol=symbol,
                data={'status': 'unsubscribed', 'type': subscription_type.value}
            ))

            logger.info(f"Unsubscription successful: {symbol} {subscription_type.value}")
            return True

        except Exception as e:
            logger.error(f"Unsubscription failed for {symbol}: {e}")
            return False

    async def process_realtime_data(self, symbol: str, raw_data: Dict[str, Any],
                                  subscription_type: SubscriptionType) -> bool:
        """Process real-time data"""
        try:
            start_time = time.perf_counter()

            # Performance monitoring
            self.performance_monitor.record_data_processing_start(symbol)

            # Quality check
            quality_score = self.quality_monitor.evaluate_data_quality(raw_data)

            if quality_score < 0.5:
                logger.warning(f"Data quality too low: {symbol}, score: {quality_score}")
                await self.event_dispatcher.dispatch_event(RealtimeEvent(
                    event_type=EventType.DATA_QUALITY_ALERT,
                    symbol=symbol,
                    data={'quality_score': quality_score, 'raw_data': raw_data}
                ))
                return False

            # Add to buffer
            buffer = self.data_buffers.get(symbol)
            if buffer:
                buffer.add_data(raw_data)

            # Find subscriptions
            subscription_key = f"{symbol}_{subscription_type.value}"
            subscription = self.subscriptions.get(subscription_key)

            if subscription and subscription.is_active:
                try:
                    # Trigger callback
                    if asyncio.iscoroutinefunction(subscription.callback):
                        await subscription.callback(symbol, raw_data)
                    else:
                        subscription.callback(symbol, raw_data)

                    subscription.last_update_time = time.time()

                    # Dispatch data update event
                    await self.event_dispatcher.dispatch_event(RealtimeEvent(
                        event_type=EventType.DATA_UPDATE,
                        symbol=symbol,
                        data=raw_data,
                        metadata={
                            'subscription_type': subscription_type.value,
                            'quality_score': quality_score,
                            'processing_time_ms': (time.perf_counter() - start_time) * 1000
                        }
                    ))

                except Exception as e:
                    logger.error(f"Subscription callback failed for {symbol}: {e}")
                    subscription.error_count += 1

                    # Suspend if too many errors
                    if subscription.error_count > 10:
                        subscription.is_active = False
                        logger.warning(f"Subscription {symbol} suspended due to excessive errors")

            # Performance monitoring
            processing_time = (time.perf_counter() - start_time) * 1000
            self.performance_monitor.record_data_processing_end(symbol, processing_time)

            return True

        except Exception as e:
            logger.error(f"Failed to process real-time data for {symbol}: {e}")
            return False

    def get_symbol_buffer_data(self, symbol: str, count: int = 100) -> List[Tuple[float, Any]]:
        """Get buffered data for symbol"""
        try:
            buffer = self.data_buffers.get(symbol)
            if buffer:
                return buffer.get_latest_data(count)
            return []

        except Exception as e:
            logger.error(f"Failed to get buffered data for {symbol}: {e}")
            return []

    def get_subscription_status(self) -> Dict[str, Any]:
        """Get subscription status"""
        try:
            active_subscriptions = sum(1 for sub in self.subscriptions.values() if sub.is_active)
            total_subscriptions = len(self.subscriptions)

            symbol_counts = defaultdict(int)
            type_counts = defaultdict(int)

            for subscription in self.subscriptions.values():
                symbol_counts[subscription.symbol] += 1
                type_counts[subscription.subscription_type.value] += 1

            return {
                'total_subscriptions': total_subscriptions,
                'active_subscriptions': active_subscriptions,
                'inactive_subscriptions': total_subscriptions - active_subscriptions,
                'symbols_count': len(symbol_counts),
                'subscription_by_symbol': dict(symbol_counts),
                'subscription_by_type': dict(type_counts),
                'buffer_stats': {
                    symbol: buffer.get_buffer_stats()
                    for symbol, buffer in self.data_buffers.items()
                }
            }

        except Exception as e:
            logger.error(f"Failed to get subscription status: {e}")
            return {}

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get comprehensive statistics"""
        return {
            'subscription_status': self.get_subscription_status(),
            'event_stats': self.event_dispatcher.get_event_stats(),
            'performance_stats': self.performance_monitor.get_performance_stats(),
            'quality_stats': self.quality_monitor.get_quality_stats(),
            'is_running': self.is_running
        }


class PerformanceMonitor:
    """Performance Monitor"""

    def __init__(self):
        self.processing_times: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.throughput_counters: Dict[str, int] = defaultdict(int)
        self.start_times: Dict[str, float] = {}
        self.is_running = False

    async def start(self) -> None:
        self.is_running = True
        logger.info("Performance monitor started")

    async def stop(self) -> None:
        self.is_running = False
        logger.info("Performance monitor stopped")

    def record_data_processing_start(self, symbol: str) -> None:
        self.start_times[symbol] = time.perf_counter()

    def record_data_processing_end(self, symbol: str, processing_time_ms: float) -> None:
        if symbol in self.start_times:
            del self.start_times[symbol]

        self.processing_times[symbol].append(processing_time_ms)
        self.throughput_counters[symbol] += 1

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        try:
            stats = {
                'symbols': {},
                'overall_avg_processing_time_ms': 0.0,
                'total_throughput': 0
            }

            total_processing_time = 0
            total_samples = 0

            for symbol, times in self.processing_times.items():
                if times:
                    avg_time = sum(times) / len(times)
                    max_time = max(times)
                    min_time = min(times)

                    stats['symbols'][symbol] = {
                        'avg_processing_time_ms': avg_time,
                        'max_processing_time_ms': max_time,
                        'min_processing_time_ms': min_time,
                        'total_processed': self.throughput_counters[symbol],
                        'samples_count': len(times)
                    }

                    total_processing_time += avg_time * len(times)
                    total_samples += len(times)

            if total_samples > 0:
                stats['overall_avg_processing_time_ms'] = total_processing_time / total_samples

            stats['total_throughput'] = sum(self.throughput_counters.values())

            return stats

        except Exception as e:
            logger.error(f"Failed to get performance stats: {e}")
            return {}


class DataQualityMonitor:
    """Data Quality Monitor"""

    def __init__(self):
        self.quality_scores: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self.quality_alerts_count: Dict[str, int] = defaultdict(int)
        self.is_running = False

    async def start(self) -> None:
        self.is_running = True
        logger.info("Data quality monitor started")

    async def stop(self) -> None:
        self.is_running = False
        logger.info("Data quality monitor stopped")

    def evaluate_data_quality(self, data: Dict[str, Any]) -> float:
        """Evaluate data quality"""
        try:
            score = 1.0

            # Check required fields
            required_fields = ['time', 'open', 'high', 'low', 'close']
            missing_fields = sum(1 for field in required_fields if field not in data)
            score *= (1 - missing_fields * 0.2)

            # Check data validity
            if 'open' in data and 'high' in data and 'low' in data and 'close' in data:
                try:
                    open_price = float(data['open'])
                    high_price = float(data['high'])
                    low_price = float(data['low'])
                    close_price = float(data['close'])

                    # Check logic
                    if high_price < max(open_price, close_price) or low_price > min(open_price, close_price):
                        score *= 0.5

                    # Check positive
                    if any(price <= 0 for price in [open_price, high_price, low_price, close_price]):
                        score *= 0.3

                except (ValueError, TypeError):
                    score *= 0.4

            # Check timestamp
            if 'time' in data:
                try:
                    timestamp = float(data['time'])
                    current_time = time.time()
                    time_diff = abs(current_time - timestamp)

                    if time_diff > 3600:  # > 1 hour
                        score *= 0.7
                    elif time_diff > 300:  # > 5 minutes
                        score *= 0.9

                except (ValueError, TypeError):
                    score *= 0.6

            return max(0.0, min(1.0, score))

        except Exception as e:
            logger.error(f"Failed to evaluate data quality: {e}")
            return 0.5

    def record_quality_score(self, symbol: str, score: float) -> None:
        self.quality_scores[symbol].append(score)

        if score < 0.5:
            self.quality_alerts_count[symbol] += 1

    def get_quality_stats(self) -> Dict[str, Any]:
        """Get quality statistics"""
        try:
            stats = {
                'symbols': {},
                'overall_avg_quality': 0.0,
                'total_alerts': sum(self.quality_alerts_count.values())
            }

            total_quality = 0
            total_samples = 0

            for symbol, scores in self.quality_scores.items():
                if scores:
                    avg_quality = sum(scores) / len(scores)
                    min_quality = min(scores)

                    stats['symbols'][symbol] = {
                        'avg_quality': avg_quality,
                        'min_quality': min_quality,
                        'samples_count': len(scores),
                        'alerts_count': self.quality_alerts_count[symbol]
                    }

                    total_quality += avg_quality * len(scores)
                    total_samples += len(scores)

            if total_samples > 0:
                stats['overall_avg_quality'] = total_quality / total_samples

            return stats

        except Exception as e:
            logger.error(f"Failed to get quality stats: {e}")
            return {}


# Helper functions
def create_realtime_adapter(buffer_size: int = 1000, max_workers: int = 4) -> AdvancedRealtimeAdapter:
    """Create advanced real-time data adapter"""
    return AdvancedRealtimeAdapter(buffer_size=buffer_size, max_workers=max_workers)


async def test_realtime_adapter():
    """Test real-time data adapter"""
    adapter = create_realtime_adapter()

    try:
        await adapter.initialize()

        async def on_kline_data(symbol: str, data: Dict[str, Any]):
            print(f"Received K-line data: {symbol} {data['close']}")

        await adapter.subscribe_symbol_data(
            "BTC/USDT",
            SubscriptionType.KLINE_15M,
            on_kline_data
        )

        test_data = {
            'time': time.time(),
            'open': 50000.0,
            'high': 51000.0,
            'low': 49500.0,
            'close': 50500.0,
            'volume': 1000.0
        }

        await adapter.process_realtime_data("BTC/USDT", test_data, SubscriptionType.KLINE_15M)
        await asyncio.sleep(1)

        stats = adapter.get_comprehensive_stats()
        print(f"Adapter Statistics: {json.dumps(stats, indent=2, default=str)}")

    finally:
        await adapter.shutdown()


if __name__ == "__main__":
    asyncio.run(test_realtime_adapter())
