#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Enhanced TradingView Client
Implements smart reconnection, connection monitoring, and message processing optimization.
"""

import asyncio
import time
import random
import json
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum

from .client import Client, TradingViewClient
from tradingview.utils import get_logger

logger = get_logger(__name__)


class ConnectionState(Enum):
    """Connection state enum"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class MessagePriority(Enum):
    """Message priority"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class ConnectionMonitor:
    """Connection state monitor"""

    def __init__(self, client_ref=None):
        self.state = ConnectionState.DISCONNECTED
        self.last_ping_time = 0
        self.last_pong_time = 0
        self.latency_history = deque(maxlen=100)
        self.error_count = 0
        self.total_reconnects = 0
        self.uptime_start = time.time()
        self.connection_quality = 1.0
        self.client_ref = client_ref  # Reference to the client, used to access connection state

        # Health check thresholds
        self.max_latency = 5000  # 5 seconds
        self.max_errors = 5
        self.ping_interval = 30  # 30 seconds

    def record_ping(self) -> None:
        """Record ping send time"""
        self.last_ping_time = time.time()

    def record_pong(self) -> None:
        """Record pong receive time"""
        self.last_pong_time = time.time()
        if self.last_ping_time > 0:
            latency = (self.last_pong_time - self.last_ping_time) * 1000
            self.latency_history.append(latency)

    def record_error(self) -> None:
        """Record error"""
        self.error_count += 1

    def record_reconnect(self) -> None:
        """Record reconnect"""
        self.total_reconnects += 1
        self.error_count = 0  # Reset error count

    def get_average_latency(self) -> float:
        """Get average latency"""
        if not self.latency_history:
            return 0.0
        return sum(self.latency_history) / len(self.latency_history)

    def get_uptime(self) -> float:
        """Get uptime (seconds)"""
        return time.time() - self.uptime_start

    def is_healthy(self) -> bool:
        """Check if connection is healthy"""
        if self.state != ConnectionState.CONNECTED:
            return False

        # Check basic connection state - access via client reference
        if self.client_ref and hasattr(self.client_ref, 'is_open'):
            try:
                if not self.client_ref.is_open:
                    return False
            except AttributeError:
                # If attribute access fails, skip this check
                pass

        # Check latency (if latency history exists)
        avg_latency = self.get_average_latency()
        if avg_latency > 0 and avg_latency > self.max_latency:
            return False

        # Check error rate
        if self.error_count > self.max_errors:
            return False

        # Check connection uptime - ensure connection exists for a while before heartbeat check
        uptime = self.get_uptime()
        if uptime > 60:  # Check heartbeat only after 60 seconds of uptime
            # Check heartbeat - if last_pong_time is 0 (just connected), give a grace period
            if self.last_pong_time > 0 and time.time() - self.last_pong_time > self.ping_interval * 3:
                return False

        return True

    def calculate_quality_score(self) -> float:
        """Calculate connection quality score 0.0-1.0"""
        if self.state != ConnectionState.CONNECTED:
            return 0.0

        quality_factors = []

        # Latency factor (0.4 weight)
        avg_latency = self.get_average_latency()
        if avg_latency > 0:
            latency_score = max(0, 1 - (avg_latency / self.max_latency))
            quality_factors.append(latency_score * 0.4)
        else:
            quality_factors.append(0.4)

        # Error rate factor (0.3 weight)
        error_score = max(0, 1 - (self.error_count / self.max_errors))
        quality_factors.append(error_score * 0.3)

        # Stability factor (0.3 weight)
        uptime = self.get_uptime()
        stability_score = min(1.0, uptime / 3600)  # Perfect score after 1 hour
        quality_factors.append(stability_score * 0.3)

        self.connection_quality = sum(quality_factors)
        return self.connection_quality


class MessageProcessor:
    """Message processor - supports priority and batch processing"""

    def __init__(self, batch_size: int = 10, batch_timeout: float = 0.1):
        self.message_queues = {
            MessagePriority.CRITICAL: asyncio.Queue(),
            MessagePriority.HIGH: asyncio.Queue(),
            MessagePriority.NORMAL: asyncio.Queue(),
            MessagePriority.LOW: asyncio.Queue()
        }
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.processing_task: Optional[asyncio.Task] = None
        self.is_running = False
        self.processed_count = 0
        self.error_count = 0
        self.message_handlers = {}

    async def start(self) -> None:
        """Start message processor"""
        if self.is_running:
            return

        self.is_running = True
        self.processing_task = asyncio.create_task(self._process_messages())
        logger.info("Message processor started")

    async def stop(self) -> None:
        """Stop message processor"""
        self.is_running = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        logger.info("Message processor stopped")

    async def add_message(self, message: Dict, priority: MessagePriority = MessagePriority.NORMAL) -> None:
        """Add message to queue"""
        try:
            await self.message_queues[priority].put(message)
        except Exception as e:
            logger.error(f"Failed to add message: {e}")

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register message handler"""
        self.message_handlers[message_type] = handler

    async def _process_messages(self) -> None:
        """Main message processing loop"""
        while self.is_running:
            try:
                # Process messages by priority
                message_batch = []

                # Prioritize high priority messages
                for priority in [MessagePriority.CRITICAL, MessagePriority.HIGH,
                               MessagePriority.NORMAL, MessagePriority.LOW]:
                    queue = self.message_queues[priority]

                    # Collect batch of messages
                    batch_start = time.time()
                    while (len(message_batch) < self.batch_size and
                           time.time() - batch_start < self.batch_timeout):
                        try:
                            message = await asyncio.wait_for(queue.get(), timeout=0.01)
                            message_batch.append((message, priority))
                        except asyncio.TimeoutError:
                            break

                    if message_batch:
                        break

                # Process batch
                if message_batch:
                    await self._process_batch(message_batch)
                else:
                    await asyncio.sleep(0.01)  # Avoid spinning

            except Exception as e:
                logger.error(f"Message processing error: {e}")
                self.error_count += 1
                await asyncio.sleep(0.1)

    async def _process_batch(self, message_batch: List) -> None:
        """Process batch of messages"""
        try:
            # Group by message type
            grouped_messages = defaultdict(list)
            for message, priority in message_batch:
                msg_type = message.get('type', 'unknown')
                grouped_messages[msg_type].append((message, priority))

            # Batch process messages of the same type
            for msg_type, messages in grouped_messages.items():
                if msg_type in self.message_handlers:
                    try:
                        handler = self.message_handlers[msg_type]
                        await handler([msg[0] for msg in messages])
                        self.processed_count += len(messages)
                    except Exception as e:
                        logger.error(f"Failed to process {msg_type} messages: {e}")
                        self.error_count += 1
                else:
                    logger.warning(f"No handler found for message type: {msg_type}")

        except Exception as e:
            logger.error(f"Batch message processing failed: {e}")
            self.error_count += 1

    def get_stats(self) -> Dict[str, Any]:
        """Get processing statistics"""
        return {
            'processed_count': self.processed_count,
            'error_count': self.error_count,
            'queue_sizes': {
                priority.name: queue.qsize()
                for priority, queue in self.message_queues.items()
            }
        }


class ReconnectStrategy:
    """Reconnection strategy"""

    def __init__(self,
                 initial_delay: float = 1.0,
                 max_delay: float = 60.0,
                 backoff_factor: float = 2.0,
                 max_retries: int = -1,  # -1 for infinite retries
                 jitter: bool = True):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.max_retries = max_retries
        self.jitter = jitter

        self.current_delay = initial_delay
        self.retry_count = 0

    def get_next_delay(self) -> float:
        """Get the delay for the next reconnection attempt"""
        if self.max_retries > 0 and self.retry_count >= self.max_retries:
            raise Exception("Maximum retries reached")

        delay = self.current_delay

        # Add jitter to avoid thundering herd problem
        if self.jitter:
            delay += random.uniform(0, delay * 0.1)

        # Exponential backoff
        self.current_delay = min(self.max_delay, self.current_delay * self.backoff_factor)
        self.retry_count += 1

        return delay

    def reset(self) -> None:
        """Reset the strategy"""
        self.current_delay = self.initial_delay
        self.retry_count = 0


class EnhancedTradingViewClient(Client):
    """Enhanced TradingView Client"""

    def __init__(self, options=None, **kwargs):
        # If no auth info provided, try to get from auth manager
        if options is None:
            options = {}

        if not options.get('token') or not options.get('signature'):
            try:
                from .auth_config import get_tradingview_auth
                auth_info = get_tradingview_auth(options.get('account_name'))
                if auth_info:
                    options.update(auth_info)
            except ImportError:
                pass  # Auth manager unavailable, continue with provided parameters

        super().__init__(options, **kwargs)

        # Connection monitoring
        self.monitor = ConnectionMonitor(client_ref=self)

        # Message processor
        self.message_processor = MessageProcessor()

        # Reconnect strategy
        self.reconnect_strategy = ReconnectStrategy()

        # Enhanced feature configuration
        self.auto_reconnect = kwargs.get('auto_reconnect', True)
        self.health_check_interval = kwargs.get('health_check_interval', 30)
        self.enable_message_batching = kwargs.get('enable_message_batching', True)

        # Task management
        self.health_check_task: Optional[asyncio.Task] = None
        self.ping_task: Optional[asyncio.Task] = None

        # Enhanced callbacks
        self.connection_state_callbacks = []
        self.health_callbacks = []

        # Statistics
        self.stats = {
            'total_messages': 0,
            'successful_connections': 0,
            'failed_connections': 0,
            'total_reconnects': 0
        }

    async def connect(self, **kwargs) -> bool:
        """Enhanced connection method"""
        try:
            self.monitor.state = ConnectionState.CONNECTING
            self._notify_connection_state_change(ConnectionState.CONNECTING)

            # Call parent connection method
            success = await super().connect(**kwargs)

            if success:
                self.monitor.state = ConnectionState.CONNECTED
                self.monitor.uptime_start = time.time()
                # Initialize heartbeat time to avoid immediate health check failure
                self.monitor.last_pong_time = time.time()
                self.stats['successful_connections'] += 1

                # Start enhanced features
                await self._start_enhanced_features()

                self._notify_connection_state_change(ConnectionState.CONNECTED)
                logger.info("✅ TradingView Enhanced Client connected successfully")
                return True
            else:
                self.monitor.state = ConnectionState.FAILED
                self.stats['failed_connections'] += 1
                self._notify_connection_state_change(ConnectionState.FAILED)
                logger.error("❌ TradingView Enhanced Client connection failed")
                logger.debug(f"🐛 Connection failure details:")
                logger.debug(f"🐛   - Client type: {type(self).__name__}")
                logger.debug(f"🐛   - WebSocket object exists: {self._ws is not None}")
                if self._ws:
                    ws_state = getattr(self._ws, 'state', 'unknown')
                    logger.debug(f"🐛   - WebSocket state: {ws_state}")
                    logger.debug(f"🐛   - WebSocket closed: {getattr(self._ws, 'closed', 'unknown')}")
                logger.debug(f"🐛   - Connection monitor state: {self.monitor.state}")
                logger.debug(f"🐛   - Connection quality: {self.monitor.connection_quality}")
                logger.debug(f"🐛   - Error count: {self.monitor.error_count}")
                return False

        except Exception as e:
            self.monitor.state = ConnectionState.FAILED
            self.stats['failed_connections'] += 1
            self._notify_connection_state_change(ConnectionState.FAILED)
            logger.error(f"Connection exception: {e}")
            logger.debug(f"🐛 Connection exception details:")
            logger.debug(f"🐛   - Exception type: {type(e).__name__}")
            logger.debug(f"🐛   - Exception message: {str(e)}")
            if hasattr(e, '__traceback__'):
                import traceback
                logger.debug(f"🐛   - Exception stack trace: {traceback.format_exc()}")

            # Start auto-reconnect if enabled
            if self.auto_reconnect:
                asyncio.create_task(self._auto_reconnect())

            return False

    async def _start_enhanced_features(self) -> None:
        """Start enhanced features"""
        try:
            # Start message processor
            if self.enable_message_batching:
                await self.message_processor.start()

            # Start health check loop
            self.health_check_task = asyncio.create_task(self._health_check_loop())

            # Start heartbeat monitoring
            self.ping_task = asyncio.create_task(self._ping_loop())

            logger.info("Enhanced features started")

        except Exception as e:
            logger.error(f"Failed to start enhanced features: {e}")

    async def _health_check_loop(self) -> None:
        """Health check loop"""
        while self.monitor.state == ConnectionState.CONNECTED:
            try:
                is_healthy = self.monitor.is_healthy()
                quality_score = self.monitor.calculate_quality_score()

                # Notify health update callbacks
                health_info = {
                    'is_healthy': is_healthy,
                    'quality_score': quality_score,
                    'average_latency': self.monitor.get_average_latency(),
                    'error_count': self.monitor.error_count,
                    'uptime': self.monitor.get_uptime()
                }

                for callback in self.health_callbacks:
                    try:
                        await callback(health_info)
                    except Exception as e:
                        logger.error(f"Health state callback failed: {e}")

                # Trigger reconnection if unhealthy
                if not is_healthy and self.auto_reconnect:
                    logger.warning("Connection unhealthy, triggering reconnect")
                    asyncio.create_task(self._auto_reconnect())
                    break

                await asyncio.sleep(self.health_check_interval)

            except Exception as e:
                logger.error(f"Health check error: {e}")
                await asyncio.sleep(5)

    async def _ping_loop(self) -> None:
        """Heartbeat loop - primarily for monitoring updates"""
        while self.monitor.state == ConnectionState.CONNECTED:
            try:
                # Record ping time for monitoring
                self.monitor.record_ping()
                # If basic connection is open, also record pong
                if self.is_open:
                    self.monitor.record_pong()

                await asyncio.sleep(self.monitor.ping_interval)

            except Exception as e:
                logger.error(f"Heartbeat check error: {e}")
                await asyncio.sleep(5)

    async def _auto_reconnect(self) -> None:
        """Automatic reconnection"""
        if self.monitor.state == ConnectionState.RECONNECTING:
            return  # Avoid duplicate reconnection attempts

        self.monitor.state = ConnectionState.RECONNECTING
        self._notify_connection_state_change(ConnectionState.RECONNECTING)

        try:
            while self.auto_reconnect:
                try:
                    delay = self.reconnect_strategy.get_next_delay()
                    logger.info(f"🔄 Reconnecting in {delay:.1f}s (Attempt #{self.reconnect_strategy.retry_count})")

                    await asyncio.sleep(delay)

                    # Cleanup existing connection
                    await self._cleanup_connection()

                    # Attempt connection
                    success = await self.connect()

                    if success:
                        self.reconnect_strategy.reset()
                        self.monitor.record_reconnect()
                        self.stats['total_reconnects'] += 1
                        logger.info("✅ Reconnected successfully")
                        return
                    else:
                        logger.warning("❌ Reconnection failed, continuing attempts")

                except Exception as e:
                    if "Maximum retries reached" in str(e):
                        logger.error("Maximum retries reached, stopping auto-reconnect")
                        break
                    else:
                        logger.error(f"Reconnection exception: {e}")

        except Exception as e:
            logger.error(f"Auto-reconnect failed: {e}")
        finally:
            if self.monitor.state == ConnectionState.RECONNECTING:
                self.monitor.state = ConnectionState.FAILED
                self._notify_connection_state_change(ConnectionState.FAILED)

    async def _cleanup_connection(self) -> None:
        """Cleanup connection"""
        try:
            # Stop enhanced features
            if self.health_check_task:
                self.health_check_task.cancel()

            if self.ping_task:
                self.ping_task.cancel()

            # Stop message processor
            await self.message_processor.stop()

            # Close WebSocket connection
            if self._ws:
                await self._ws.close()

        except Exception as e:
            logger.error(f"Connection cleanup failed: {e}")

    def _notify_connection_state_change(self, new_state: ConnectionState) -> None:
        """Notify connection state change"""
        for callback in self.connection_state_callbacks:
            try:
                callback(new_state)
            except Exception as e:
                logger.error(f"Connection state callback failed: {e}")

    # Enhanced public interface
    def on_connection_state_change(self, callback: Callable[[ConnectionState], None]) -> None:
        """Register connection state change callback"""
        self.connection_state_callbacks.append(callback)

    def on_health_update(self, callback: Callable[[Dict], None]) -> None:
        """Register health state update callback"""
        self.health_callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        """Check if connected - compatible with ConnectionManager interface"""
        return self.is_open and self.monitor.state == ConnectionState.CONNECTED

    def get_connection_stats(self) -> Dict[str, Any]:
        """Get connection statistics"""
        return {
            'state': self.monitor.state.value,
            'quality_score': self.monitor.connection_quality,
            'average_latency': self.monitor.get_average_latency(),
            'uptime': self.monitor.get_uptime(),
            'error_count': self.monitor.error_count,
            'total_reconnects': self.monitor.total_reconnects,
            'stats': self.stats,
            'message_processor_stats': self.message_processor.get_stats()
        }

    async def disconnect(self) -> None:
        """Enhanced disconnect method"""
        self.auto_reconnect = False  # Disable auto-reconnect

        await self._cleanup_connection()

        self.monitor.state = ConnectionState.DISCONNECTED
        self._notify_connection_state_change(ConnectionState.DISCONNECTED)

        await super().end()
        logger.info("🔌 TradingView Enhanced Client disconnected")


# Create alias for backward compatibility
EnhancedTradingViewClient = EnhancedTradingViewClient
