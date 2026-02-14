#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Message Processing Optimizer
Implements efficient message queues, deduplication, priority processing, and batching.
"""

import asyncio
import time
import hashlib
import json
from typing import Dict, List, Set, Optional, Callable, Any, Tuple
from collections import deque, defaultdict
from dataclasses import dataclass
from enum import Enum, auto

from tradingview.utils import get_logger

logger = get_logger(__name__)


class MessageType(Enum):
    """Message type enumeration"""
    KLINE_UPDATE = auto()
    QUOTE_UPDATE = auto()
    SYMBOL_RESOLVED = auto()
    CHART_DATA = auto()
    STUDY_DATA = auto()
    ERROR = auto()
    PING = auto()
    PONG = auto()
    OTHER = auto()


@dataclass
class ProcessedMessage:
    """Represents a processed message"""
    message_id: str
    message_type: MessageType
    symbol: Optional[str]
    data: Dict[str, Any]
    timestamp: float
    priority: int
    processed: bool = False
    retry_count: int = 0


class MessageDeduplicator:
    """Deduplicates incoming messages"""

    def __init__(self, window_size: int = 1000, ttl: float = 300.0):
        self.window_size = window_size
        self.ttl = ttl
        self.seen_messages: deque = deque(maxlen=window_size)
        self.message_timestamps: Dict[str, float] = {}

    def is_duplicate(self, message: Dict[str, Any]) -> bool:
        """Check if message is a duplicate"""
        try:
            # Generate fingerprint
            fingerprint = self._generate_fingerprint(message)
            current_time = time.time()

            # Cleanup expired
            self._cleanup_expired_messages(current_time)

            # Check duplicate
            if fingerprint in self.message_timestamps:
                logger.debug(f"Found duplicate message: {fingerprint}")
                return True

            # Record new
            self.seen_messages.append(fingerprint)
            self.message_timestamps[fingerprint] = current_time

            return False

        except Exception as e:
            logger.error(f"Deduplication check failed: {e}")
            return False

    def _generate_fingerprint(self, message: Dict[str, Any]) -> str:
        """Generate message fingerprint"""
        try:
            # Extract key fields
            key_fields = {
                'type': message.get('type'),
                'symbol': message.get('symbol'),
                'timestamp': message.get('timestamp')
            }

            # Include data hash for data messages
            if 'data' in message:
                data_str = json.dumps(message['data'], sort_keys=True)
                key_fields['data_hash'] = hashlib.md5(data_str.encode()).hexdigest()[:8]

            fingerprint_str = json.dumps(key_fields, sort_keys=True)
            return hashlib.sha256(fingerprint_str.encode()).hexdigest()[:16]

        except Exception as e:
            logger.error(f"Failed to generate fingerprint: {e}")
            return str(hash(str(message)))

    def _cleanup_expired_messages(self, current_time: float) -> None:
        """Cleanup expired message fingerprints"""
        try:
            expired_keys = [
                key for key, timestamp in self.message_timestamps.items()
                if current_time - timestamp > self.ttl
            ]

            for key in expired_keys:
                del self.message_timestamps[key]

        except Exception as e:
            logger.error(f"Failed to cleanup expired messages: {e}")


class MessageClassifier:
    """Classifies incoming raw messages"""

    def __init__(self):
        self.classification_rules = {
            'timescale_update': MessageType.KLINE_UPDATE,
            'quote_update': MessageType.QUOTE_UPDATE,
            'symbol_resolved': MessageType.SYMBOL_RESOLVED,
            'series_completed': MessageType.CHART_DATA,
            'study_completed': MessageType.STUDY_DATA,
            'protocol_error': MessageType.ERROR,
            'ping': MessageType.PING,
            'pong': MessageType.PONG
        }

        self.priority_rules = {
            MessageType.ERROR: 100,
            MessageType.PING: 90,
            MessageType.PONG: 90,
            MessageType.KLINE_UPDATE: 80,
            MessageType.QUOTE_UPDATE: 70,
            MessageType.CHART_DATA: 60,
            MessageType.SYMBOL_RESOLVED: 50,
            MessageType.STUDY_DATA: 40,
            MessageType.OTHER: 10
        }

    def classify_message(self, raw_message: Dict[str, Any]) -> ProcessedMessage:
        """Classify a raw message"""
        try:
            # Determine type
            message_type = self._determine_type(raw_message)

            # Extract symbol
            symbol = self._extract_symbol(raw_message)

            # Generate ID
            message_id = self._generate_message_id(raw_message)

            # Determine priority
            priority = self.priority_rules.get(message_type, 10)

            return ProcessedMessage(
                message_id=message_id,
                message_type=message_type,
                symbol=symbol,
                data=raw_message,
                timestamp=time.time(),
                priority=priority
            )

        except Exception as e:
            logger.error(f"Message classification failed: {e}")
            return ProcessedMessage(
                message_id=f"error_{time.time()}",
                message_type=MessageType.OTHER,
                symbol=None,
                data=raw_message,
                timestamp=time.time(),
                priority=1
            )

    def _determine_type(self, message: Dict[str, Any]) -> MessageType:
        """Determine internal message type"""
        message_method = message.get('type', '').lower()

        for pattern, msg_type in self.classification_rules.items():
            if pattern in message_method:
                return msg_type

        return MessageType.OTHER

    def _extract_symbol(self, message: Dict[str, Any]) -> Optional[str]:
        """Extract trading symbol from message"""
        try:
            if 'symbol' in message:
                return message['symbol']

            if 'data' in message and isinstance(message['data'], list):
                for item in message['data']:
                    if isinstance(item, str) and ':' in item:
                        return item

            return None

        except Exception:
            return None

    def _generate_message_id(self, message: Dict[str, Any]) -> str:
        """Generate a unique message identifier"""
        try:
            timestamp = str(time.time())
            content_hash = hashlib.md5(str(message).encode()).hexdigest()[:8]
            return f"msg_{timestamp}_{content_hash}"
        except Exception:
            return f"msg_{time.time()}"


class BatchProcessor:
    """Processes messages in optimized batches"""

    def __init__(self,
                 max_batch_size: int = 50,
                 max_wait_time: float = 0.1,
                 max_concurrent_batches: int = 5):
        self.max_batch_size = max_batch_size
        self.max_wait_time = max_wait_time
        self.max_concurrent_batches = max_concurrent_batches

        self.pending_batches: Dict[MessageType, List[ProcessedMessage]] = defaultdict(list)
        self.batch_timers: Dict[MessageType, float] = {}
        self.processing_semaphore = asyncio.Semaphore(max_concurrent_batches)

        self.processed_count = 0
        self.batch_count = 0

    async def add_message(self, message: ProcessedMessage) -> None:
        """Add message to batching queue"""
        try:
            message_type = message.message_type

            # Add to type-specific batch
            self.pending_batches[message_type].append(message)

            # Start timer if first in batch
            if message_type not in self.batch_timers:
                self.batch_timers[message_type] = time.time()

            # Check if processing triggered
            batch = self.pending_batches[message_type]
            elapsed = time.time() - self.batch_timers[message_type]

            if len(batch) >= self.max_batch_size or elapsed >= self.max_wait_time:
                await self._process_batch(message_type)

        except Exception as e:
            logger.error(f"Failed to add message to batch: {e}")

    async def _process_batch(self, message_type: MessageType) -> None:
        """Trigger processing for a batch type"""
        try:
            batch = self.pending_batches[message_type]
            if not batch:
                return

            # Clear current batch
            self.pending_batches[message_type] = []
            if message_type in self.batch_timers:
                del self.batch_timers[message_type]

            # Spawn processing task
            asyncio.create_task(self._handle_batch(message_type, batch))

        except Exception as e:
            logger.error(f"Failed to process batch: {e}")

    async def _handle_batch(self, message_type: MessageType, batch: List[ProcessedMessage]) -> None:
        """Logic for batch handling"""
        async with self.processing_semaphore:
            try:
                start_time = time.time()

                # Group by symbol
                symbol_groups = defaultdict(list)
                for message in batch:
                    symbol = message.symbol or 'unknown'
                    symbol_groups[symbol].append(message)

                # Process symbol groups concurrently
                tasks = []
                for symbol, messages in symbol_groups.items():
                    task = asyncio.create_task(
                        self._process_symbol_group(message_type, symbol, messages)
                    )
                    tasks.append(task)

                await asyncio.gather(*tasks, return_exceptions=True)

                # Update stats
                self.processed_count += len(batch)
                self.batch_count += 1

                processing_time = (time.time() - start_time) * 1000
                logger.debug(f"Batch processed: {message_type.name}, "
                           f"Count: {len(batch)}, Duration: {processing_time:.1f}ms")

            except Exception as e:
                logger.error(f"Error handling batch: {e}")

    async def _process_symbol_group(self,
                                  message_type: MessageType,
                                  symbol: str,
                                  messages: List[ProcessedMessage]) -> None:
        """Process a message group for a single symbol"""
        try:
            if message_type == MessageType.KLINE_UPDATE:
                await self._merge_kline_updates(symbol, messages)
            elif message_type == MessageType.QUOTE_UPDATE:
                await self._merge_quote_updates(symbol, messages)
            else:
                for message in messages:
                    message.processed = True

        except Exception as e:
            logger.error(f"Failed to process symbol group {symbol}: {e}")

    async def _merge_kline_updates(self, symbol: str, messages: List[ProcessedMessage]) -> None:
        """Logic for merging K-line updates"""
        try:
            # Sort by time
            messages.sort(key=lambda m: m.timestamp)

            # Keep latest only
            latest_message = messages[-1]
            latest_message.processed = True

            for message in messages[:-1]:
                message.processed = True

            logger.debug(f"Merged {symbol} K-line updates: {len(messages)} -> 1")

        except Exception as e:
            logger.error(f"Failed to merge K-line updates: {e}")

    async def _merge_quote_updates(self, symbol: str, messages: List[ProcessedMessage]) -> None:
        """Logic for merging quote updates"""
        try:
            latest_message = messages[-1]
            latest_message.processed = True

            for message in messages[:-1]:
                message.processed = True

            logger.debug(f"Merged {symbol} quote updates: {len(messages)} -> 1")

        except Exception as e:
            logger.error(f"Failed to merge quote updates: {e}")

    async def flush_all_batches(self) -> None:
        """Flush all remaining batches"""
        try:
            for message_type in list(self.pending_batches.keys()):
                if self.pending_batches[message_type]:
                    await self._process_batch(message_type)

        except Exception as e:
            logger.error(f"Failed to flush batches: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Summary of batch processing"""
        return {
            'processed_count': self.processed_count,
            'batch_count': self.batch_count,
            'pending_batches': {
                msg_type.name: len(batch)
                for msg_type, batch in self.pending_batches.items()
            },
            'avg_batch_size': self.processed_count / max(1, self.batch_count)
        }


class AdvancedMessageOptimizer:
    """Advanced message handling optimization engine"""

    def __init__(self,
                 enable_deduplication: bool = True,
                 enable_batching: bool = True,
                 max_queue_size: int = 10000):

        # Components
        self.deduplicator = MessageDeduplicator() if enable_deduplication else None
        self.classifier = MessageClassifier()
        self.batch_processor = BatchProcessor() if enable_batching else None

        # Queue
        self.message_queue: asyncio.Queue = asyncio.Queue(maxsize=max_queue_size)

        # Registries
        self.message_handlers: Dict[MessageType, Callable] = {}

        # Status
        self.is_running = False
        self.processor_task: Optional[asyncio.Task] = None

        # Stats
        self.stats = {
            'total_messages': 0,
            'processed_messages': 0,
            'duplicate_messages': 0,
            'error_messages': 0,
            'processing_time_ms': deque(maxlen=1000)
        }

    async def start(self) -> None:
        """Start the optimizer"""
        if self.is_running:
            return

        self.is_running = True
        self.processor_task = asyncio.create_task(self._process_messages())
        logger.info("Advanced Message Optimizer started")

    async def stop(self) -> None:
        """Shutdown the optimizer"""
        self.is_running = False

        if self.processor_task:
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass

        # Flush batches
        if self.batch_processor:
            await self.batch_processor.flush_all_batches()

        logger.info("Advanced Message Optimizer stopped")

    async def add_message(self, raw_message: Dict[str, Any]) -> bool:
        """Enqueue raw message for optimization"""
        try:
            if not self.is_running:
                return False

            if self.message_queue.full():
                logger.warning("Message queue full, dropping message")
                return False

            await self.message_queue.put(raw_message)
            self.stats['total_messages'] += 1
            return True

        except Exception as e:
            logger.error(f"Failed to add message: {e}")
            return False

    def register_handler(self, message_type: MessageType, handler: Callable) -> None:
        """Register a handler for a specific message type"""
        self.message_handlers[message_type] = handler
        logger.info(f"Registered message handler for: {message_type.name}")

    async def _process_messages(self) -> None:
        """Core message processing loop"""
        while self.is_running:
            try:
                raw_message = await asyncio.wait_for(
                    self.message_queue.get(), timeout=0.1
                )

                start_time = time.perf_counter()

                # Deduplication
                if self.deduplicator and self.deduplicator.is_duplicate(raw_message):
                    self.stats['duplicate_messages'] += 1
                    continue

                # Classification
                processed_message = self.classifier.classify_message(raw_message)

                # Batching vs Single
                if self.batch_processor:
                    await self.batch_processor.add_message(processed_message)
                else:
                    await self._handle_single_message(processed_message)

                # Track duration
                processing_time = (time.perf_counter() - start_time) * 1000
                self.stats['processing_time_ms'].append(processing_time)
                self.stats['processed_messages'] += 1

            except asyncio.TimeoutError:
                if self.batch_processor:
                    await self.batch_processor.flush_all_batches()
                continue
            except Exception as e:
                logger.error(f"Error in message processing loop: {e}")
                self.stats['error_messages'] += 1
                await asyncio.sleep(0.01)

    async def _handle_single_message(self, message: ProcessedMessage) -> None:
        """Dispatcher for single message processing"""
        try:
            handler = self.message_handlers.get(message.message_type)
            if handler:
                await handler(message)
                message.processed = True
            else:
                logger.debug(f"No handler registered for {message.message_type.name}")

        except Exception as e:
            logger.error(f"Single message processing failed: {e}")
            message.retry_count += 1

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Comprehensive statistics report"""
        stats = {
            'optimizer_stats': self.stats.copy(),
            'batch_processor_stats': None,
            'avg_processing_time_ms': 0.0,
            'message_throughput': 0.0
        }

        if self.stats['processing_time_ms']:
            stats['avg_processing_time_ms'] = sum(self.stats['processing_time_ms']) / len(self.stats['processing_time_ms'])

        if self.stats['processed_messages'] > 0:
            # Note: This is an approximation
            stats['message_throughput'] = self.stats['processed_messages'] / max(1, time.time())

        if self.batch_processor:
            stats['batch_processor_stats'] = self.batch_processor.get_stats()

        return stats
