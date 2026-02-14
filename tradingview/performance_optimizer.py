#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Performance Optimization System
Implements intelligent caching, connection pool management, and performance tuning.
"""

import asyncio
import time
import json
import weakref
import hashlib
from typing import Dict, List, Optional, Any, Callable, Union, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict, OrderedDict
from enum import Enum, auto
import threading
from concurrent.futures import ThreadPoolExecutor
import psutil
import gc

from tradingview.utils import get_logger

logger = get_logger(__name__)


class CacheStrategy(Enum):
    """Cache strategy"""
    LRU = auto()        # Least Recently Used
    LFU = auto()        # Least Frequently Used
    TTL = auto()        # Time To Live
    ADAPTIVE = auto()   # Adaptive


class ConnectionStatus(Enum):
    """Connection status"""
    IDLE = auto()
    ACTIVE = auto()
    ERROR = auto()
    CLOSED = auto()


@dataclass
class CacheEntry:
    """Cache entry"""
    key: str
    value: Any
    access_count: int = 0
    last_access_time: float = field(default_factory=time.time)
    created_time: float = field(default_factory=time.time)
    ttl_seconds: Optional[float] = None
    size_bytes: int = 0

    def is_expired(self) -> bool:
        """Check if expired"""
        if self.ttl_seconds is None:
            return False
        return time.time() - self.created_time > self.ttl_seconds

    def touch(self) -> None:
        """Update access info"""
        self.access_count += 1
        self.last_access_time = time.time()


@dataclass
class ConnectionMetrics:
    """Connection metrics"""
    connection_id: str
    created_time: float = field(default_factory=time.time)
    last_used_time: float = field(default_factory=time.time)
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_bytes_sent: int = 0
    total_bytes_received: int = 0
    average_latency_ms: float = 0.0
    status: ConnectionStatus = ConnectionStatus.IDLE


class IntelligentCache:
    """Intelligent Cache System"""

    def __init__(self, max_size: int = 10000, strategy: CacheStrategy = CacheStrategy.ADAPTIVE,
                 default_ttl: Optional[float] = 3600):
        self.max_size = max_size
        self.strategy = strategy
        self.default_ttl = default_ttl

        # Cache storage
        self.cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self.lock = threading.RLock()

        # Statistics
        self.stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'total_size_bytes': 0,
            'entry_count': 0
        }

        # Adaptive configuration
        self.adaptive_config = {
            'hit_rate_threshold': 0.8,
            'size_threshold_ratio': 0.9,
            'adjustment_interval': 300  # 5 minutes
        }

        # Tasks
        self.cleanup_task: Optional[asyncio.Task] = None
        self.is_running = False

    async def start(self) -> None:
        """Start cache system"""
        if self.is_running:
            return

        self.is_running = True
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Intelligent cache system started")

    async def stop(self) -> None:
        """Stop cache system"""
        self.is_running = False

        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass

        logger.info("Intelligent cache system stopped")

    def get(self, key: str) -> Optional[Any]:
        """Get cache value"""
        try:
            with self.lock:
                if key not in self.cache:
                    self.stats['misses'] += 1
                    return None

                entry = self.cache[key]

                # Check expiration
                if entry.is_expired():
                    del self.cache[key]
                    self.stats['misses'] += 1
                    self._update_size_stats()
                    return None

                # Update access
                entry.touch()

                # LRU: move to end
                if self.strategy in [CacheStrategy.LRU, CacheStrategy.ADAPTIVE]:
                    self.cache.move_to_end(key)

                self.stats['hits'] += 1
                return entry.value

        except Exception as e:
            logger.error(f"Failed to get cache: {e}")
            return None

    async def put(self, key: str, value: Any, ttl: Optional[float] = None) -> bool:
        """Set cache value"""
        try:
            with self.lock:
                # Calculate size
                size_bytes = self._calculate_size(value)

                # Create entry
                entry = CacheEntry(
                    key=key,
                    value=value,
                    ttl_seconds=ttl or self.default_ttl,
                    size_bytes=size_bytes
                )

                # Update if existing
                if key in self.cache:
                    old_entry = self.cache[key]
                    self.stats['total_size_bytes'] -= old_entry.size_bytes

                # Add to cache
                self.cache[key] = entry
                self.stats['total_size_bytes'] += size_bytes
                self.stats['entry_count'] = len(self.cache)

                # Evict if needed
                await self._check_and_evict()

                return True

        except Exception as e:
            logger.error(f"Failed to set cache: {e}")
            return False

    def remove(self, key: str) -> bool:
        """Remove cache entry"""
        try:
            with self.lock:
                if key in self.cache:
                    entry = self.cache[key]
                    del self.cache[key]
                    self.stats['total_size_bytes'] -= entry.size_bytes
                    self.stats['entry_count'] = len(self.cache)
                    return True
                return False

        except Exception as e:
            logger.error(f"Failed to remove cache entry: {e}")
            return False

    def clear(self) -> None:
        """Clear cache"""
        try:
            with self.lock:
                self.cache.clear()
                self.stats['total_size_bytes'] = 0
                self.stats['entry_count'] = 0
                self.stats['evictions'] += len(self.cache)

        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")

    async def _check_and_evict(self) -> None:
        """Eviction check"""
        try:
            if len(self.cache) <= self.max_size:
                return

            if self.strategy == CacheStrategy.LRU:
                await self._evict_lru()
            elif self.strategy == CacheStrategy.LFU:
                await self._evict_lfu()
            elif self.strategy == CacheStrategy.TTL:
                await self._evict_expired()
            elif self.strategy == CacheStrategy.ADAPTIVE:
                await self._evict_adaptive()

        except Exception as e:
            logger.error(f"Cache eviction failed: {e}")

    async def _evict_lru(self) -> None:
        """LRU eviction"""
        try:
            evict_count = len(self.cache) - self.max_size + 1
            for _ in range(min(evict_count, len(self.cache))):
                if self.cache:
                    key, entry = self.cache.popitem(last=False)
                    self.stats['total_size_bytes'] -= entry.size_bytes
                    self.stats['evictions'] += 1
        except Exception as e:
            logger.error(f"LRU eviction failed: {e}")

    async def _evict_lfu(self) -> None:
        """LFU eviction"""
        try:
            items = sorted(self.cache.items(), key=lambda x: x[1].access_count)
            evict_count = len(self.cache) - self.max_size + 1
            for i in range(min(evict_count, len(items))):
                key, entry = items[i]
                if key in self.cache:
                    del self.cache[key]
                    self.stats['total_size_bytes'] -= entry.size_bytes
                    self.stats['evictions'] += 1
        except Exception as e:
            logger.error(f"LFU eviction failed: {e}")

    async def _evict_expired(self) -> None:
        """Cleanup expired entries"""
        try:
            expired_keys = [
                key for key, entry in self.cache.items()
                if entry.is_expired()
            ]
            for key in expired_keys:
                if key in self.cache:
                    entry = self.cache[key]
                    del self.cache[key]
                    self.stats['total_size_bytes'] -= entry.size_bytes
                    self.stats['evictions'] += 1
        except Exception as e:
            logger.error(f"Expiration cleanup failed: {e}")

    async def _evict_adaptive(self) -> None:
        """Adaptive eviction strategy"""
        try:
            await self._evict_expired()
            if len(self.cache) > self.max_size:
                hit_rate = self._calculate_hit_rate()
                if hit_rate > self.adaptive_config['hit_rate_threshold']:
                    await self._evict_lfu()
                else:
                    await self._evict_lru()
        except Exception as e:
            logger.error(f"Adaptive eviction failed: {e}")

    async def _cleanup_loop(self) -> None:
        """Periodic cleanup loop"""
        while self.is_running:
            try:
                await self._evict_expired()
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Cleanup loop error: {e}")
                await asyncio.sleep(5)

    def _calculate_size(self, value: Any) -> int:
        """Estimate object size"""
        try:
            if isinstance(value, (str, bytes)):
                return len(value)
            elif isinstance(value, (int, float)):
                return 8
            elif isinstance(value, (list, tuple)):
                return sum(self._calculate_size(item) for item in value)
            elif isinstance(value, dict):
                return sum(self._calculate_size(k) + self._calculate_size(v)
                          for k, v in value.items())
            else:
                return len(json.dumps(value, default=str))
        except Exception:
            return 1024

    def _calculate_hit_rate(self) -> float:
        """Calculate cache hit rate"""
        total_requests = self.stats['hits'] + self.stats['misses']
        if total_requests == 0:
            return 0.0
        return self.stats['hits'] / total_requests

    def _update_size_stats(self) -> None:
        """Update size metrics"""
        self.stats['entry_count'] = len(self.cache)
        self.stats['total_size_bytes'] = sum(entry.size_bytes for entry in self.cache.values())

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        with self.lock:
            hit_rate = self._calculate_hit_rate()
            return {
                **self.stats,
                'hit_rate': hit_rate,
                'miss_rate': 1 - hit_rate,
                'max_size': self.max_size,
                'current_size': len(self.cache),
                'fill_ratio': len(self.cache) / self.max_size,
                'average_entry_size': (self.stats['total_size_bytes'] / max(1, len(self.cache))),
                'strategy': self.strategy.name
            }


class ConnectionPool:
    """Connection Pool Manager"""

    def __init__(self, min_connections: int = 5, max_connections: int = 50,
                 connection_timeout: float = 30.0, idle_timeout: float = 300.0):
        self.min_connections = min_connections
        self.max_connections = max_connections
        self.connection_timeout = connection_timeout
        self.idle_timeout = idle_timeout

        # Pool storage
        self.idle_connections: deque = deque()
        self.active_connections: Dict[str, Any] = {}
        self.connection_metrics: Dict[str, ConnectionMetrics] = {}

        # Sync
        self.lock = threading.RLock()
        self.connection_semaphore = asyncio.Semaphore(max_connections)

        # Factory
        self.connection_factory: Optional[Callable] = None

        # Management
        self.management_task: Optional[asyncio.Task] = None
        self.is_running = False

        # Statistics
        self.pool_stats = {
            'total_created': 0,
            'total_destroyed': 0,
            'current_active': 0,
            'current_idle': 0,
            'connection_requests': 0,
            'connection_timeouts': 0,
            'average_wait_time_ms': 0.0
        }

    async def initialize(self, connection_factory: Callable) -> bool:
        """Initialize connection pool"""
        try:
            self.connection_factory = connection_factory
            for _ in range(self.min_connections):
                connection = await self._create_connection()
                if connection:
                    self.idle_connections.append(connection)

            self.is_running = True
            self.management_task = asyncio.create_task(self._management_loop())
            logger.info(f"✅ Connection pool initialized with {len(self.idle_connections)} initial connections")
            return True
        except Exception as e:
            logger.error(f"❌ Connection pool initialization failed: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown connection pool"""
        try:
            self.is_running = False
            if self.management_task:
                self.management_task.cancel()

            with self.lock:
                while self.idle_connections:
                    connection = self.idle_connections.popleft()
                    await self._destroy_connection(connection)

                for connection_id, connection in list(self.active_connections.items()):
                    await self._destroy_connection(connection)
                    del self.active_connections[connection_id]

            logger.info("Connection pool closed")
        except Exception as e:
            logger.error(f"Failed to shutdown connection pool: {e}")

    async def get_connection(self, timeout: Optional[float] = None) -> Optional[Any]:
        """Acquire a connection"""
        start_time = time.perf_counter()
        timeout = timeout or self.connection_timeout
        try:
            await asyncio.wait_for(self.connection_semaphore.acquire(), timeout=timeout)
            self.pool_stats['connection_requests'] += 1

            with self.lock:
                connection = await self._get_idle_connection()
                if connection is None:
                    connection = await self._create_connection()

                if connection:
                    connection_id = id(connection)
                    self.active_connections[str(connection_id)] = connection

                    if str(connection_id) not in self.connection_metrics:
                        self.connection_metrics[str(connection_id)] = ConnectionMetrics(
                            connection_id=str(connection_id)
                        )

                    metrics = self.connection_metrics[str(connection_id)]
                    metrics.last_used_time = time.time()
                    metrics.status = ConnectionStatus.ACTIVE

                    self._update_pool_stats()
                    wait_time = (time.perf_counter() - start_time) * 1000
                    self._update_wait_time_stats(wait_time)
                    return connection
                else:
                    self.connection_semaphore.release()
                    return None
        except asyncio.TimeoutError:
            logger.warning("Connection acquisition timeout")
            self.pool_stats['connection_timeouts'] += 1
            return None
        except Exception as e:
            logger.error(f"Failed to get connection: {e}")
            self.connection_semaphore.release()
            return None

    async def return_connection(self, connection: Any) -> bool:
        """Return a connection to the pool"""
        try:
            with self.lock:
                connection_id = str(id(connection))
                if connection_id in self.active_connections:
                    del self.active_connections[connection_id]
                    if await self._is_connection_healthy(connection):
                        self.idle_connections.append(connection)
                        if connection_id in self.connection_metrics:
                            self.connection_metrics[connection_id].status = ConnectionStatus.IDLE
                    else:
                        await self._destroy_connection(connection)
                        del self.connection_metrics[connection_id]

                    self._update_pool_stats()
                    self.connection_semaphore.release()
                    return True
            return False
        except Exception as e:
            logger.error(f"Failed to return connection: {e}")
            return False

    async def _get_idle_connection(self) -> Optional[Any]:
        """Fetch an idle connection"""
        try:
            while self.idle_connections:
                connection = self.idle_connections.popleft()
                if await self._is_connection_healthy(connection):
                    return connection
                else:
                    await self._destroy_connection(connection)
                    connection_id = str(id(connection))
                    if connection_id in self.connection_metrics:
                        del self.connection_metrics[connection_id]
            return None
        except Exception as e:
            logger.error(f"Failed to get idle connection: {e}")
            return None

    async def _create_connection(self) -> Optional[Any]:
        """Create new connection instance"""
        try:
            if not self.connection_factory:
                return None
            connection = await self.connection_factory()
            if connection:
                self.pool_stats['total_created'] += 1
                logger.debug("Successfully created new connection")
                return connection
            return None
        except Exception as e:
            logger.error(f"Connection creation failed: {e}")
            return None

    async def _destroy_connection(self, connection: Any) -> None:
        """Destroy connection instance"""
        try:
            if hasattr(connection, 'close'):
                await connection.close()
            elif hasattr(connection, 'disconnect'):
                await connection.disconnect()
            self.pool_stats['total_destroyed'] += 1
            logger.debug("Successfully destroyed connection")
        except Exception as e:
            logger.error(f"Failed to destroy connection: {e}")

    async def _is_connection_healthy(self, connection: Any) -> bool:
        """Evaluate connection health"""
        try:
            if hasattr(connection, 'is_connected'):
                return connection.is_connected()
            elif hasattr(connection, 'ping'):
                await connection.ping()
                return True
            return True
        except Exception:
            return False

    async def _management_loop(self) -> None:
        """Pool management background loop"""
        while self.is_running:
            try:
                await self._maintain_min_connections()
                await self._cleanup_idle_connections()
                await asyncio.sleep(30)
            except Exception as e:
                logger.error(f"Pool management exception: {e}")
                await asyncio.sleep(5)

    async def _maintain_min_connections(self) -> None:
        """Ensure minimum connection count"""
        try:
            with self.lock:
                current_total = len(self.idle_connections) + len(self.active_connections)
                if current_total < self.min_connections:
                    needed = self.min_connections - current_total
                    for _ in range(needed):
                        connection = await self._create_connection()
                        if connection:
                            self.idle_connections.append(connection)
                        else:
                            break
        except Exception as e:
            logger.error(f"Failed to maintain minimum connections: {e}")

    async def _cleanup_idle_connections(self) -> None:
        """Remove stale idle connections"""
        try:
            current_time = time.time()
            with self.lock:
                idle_to_remove = []
                for connection in list(self.idle_connections):
                    connection_id = str(id(connection))
                    metrics = self.connection_metrics.get(connection_id)
                    if metrics and current_time - metrics.last_used_time > self.idle_timeout:
                        if len(self.idle_connections) + len(self.active_connections) > self.min_connections:
                            idle_to_remove.append(connection)

                for connection in idle_to_remove:
                    self.idle_connections.remove(connection)
                    await self._destroy_connection(connection)
                    connection_id = str(id(connection))
                    if connection_id in self.connection_metrics:
                        del self.connection_metrics[connection_id]
        except Exception as e:
            logger.error(f"Stale connection cleanup failed: {e}")

    def _update_pool_stats(self) -> None:
        self.pool_stats['current_active'] = len(self.active_connections)
        self.pool_stats['current_idle'] = len(self.idle_connections)

    def _update_wait_time_stats(self, wait_time_ms: float) -> None:
        current_avg = self.pool_stats['average_wait_time_ms']
        requests = self.pool_stats['connection_requests']
        if requests > 0:
            new_avg = ((current_avg * (requests - 1)) + wait_time_ms) / requests
            self.pool_stats['average_wait_time_ms'] = new_avg

    def get_pool_stats(self) -> Dict[str, Any]:
        """Get pool usage statistics"""
        with self.lock:
            return {
                **self.pool_stats,
                'min_connections': self.min_connections,
                'max_connections': self.max_connections,
                'connection_timeout': self.connection_timeout,
                'idle_timeout': self.idle_timeout,
                'connection_efficiency': (self.pool_stats['total_created'] / max(1, self.pool_stats['connection_requests'])),
                'connection_metrics_count': len(self.connection_metrics)
            }


class PerformanceOptimizer:
    """Performance Optimization Manager"""

    def __init__(self):
        # Components
        self.cache = IntelligentCache()
        self.connection_pool = ConnectionPool()
        self.system_monitor = SystemMonitor()

        # Configuration
        self.optimization_config = {
            'enable_auto_optimization': True,
            'memory_threshold': 0.85,
            'cpu_threshold': 0.80,
            'optimization_interval': 60,
        }

        # State
        self.is_running = False
        self.optimization_task: Optional[asyncio.Task] = None

        # Statistics
        self.performance_stats = {
            'optimization_cycles': 0,
            'cache_optimizations': 0,
            'connection_optimizations': 0,
            'memory_optimizations': 0,
            'last_optimization_time': 0.0
        }

    async def initialize(self, connection_factory: Optional[Callable] = None) -> bool:
        """Initialize optimizer"""
        try:
            await self.cache.start()
            if connection_factory:
                await self.connection_pool.initialize(connection_factory)
            await self.system_monitor.start()

            if self.optimization_config['enable_auto_optimization']:
                self.is_running = True
                self.optimization_task = asyncio.create_task(self._optimization_loop())

            logger.info("✅ Performance optimizer initialized")
            return True
        except Exception as e:
            logger.error(f"❌ Performance optimizer failed to initialize: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown optimizer"""
        try:
            self.is_running = False
            if self.optimization_task:
                self.optimization_task.cancel()

            await self.system_monitor.stop()
            await self.connection_pool.shutdown()
            await self.cache.stop()
            logger.info("Performance optimizer shutdown completed")
        except Exception as e:
            logger.error(f"Failed to shutdown optimizer: {e}")

    async def _optimization_loop(self) -> None:
        """Main optimization cycle"""
        while self.is_running:
            try:
                self.performance_stats['optimization_cycles'] += 1
                system_metrics = self.system_monitor.get_system_metrics()

                # Memory optimization
                if system_metrics['memory_usage'] > self.optimization_config['memory_threshold']:
                    await self._optimize_memory()

                # Cache optimization
                cache_stats = self.cache.get_cache_stats()
                if cache_stats['hit_rate'] < 0.7:
                    await self._optimize_cache()

                # Connection optimization
                pool_stats = self.connection_pool.get_pool_stats()
                if pool_stats['average_wait_time_ms'] > 100:
                    await self._optimize_connections()

                self.performance_stats['last_optimization_time'] = time.time()
                await asyncio.sleep(self.optimization_config['optimization_interval'])
            except Exception as e:
                logger.error(f"Optimization loop exception: {e}")
                await asyncio.sleep(10)

    async def _optimize_memory(self) -> None:
        """Execute memory optimization"""
        try:
            logger.info("Executing memory optimization...")
            gc.collect()
            await self.cache._evict_expired()

            system_metrics = self.system_monitor.get_system_metrics()
            if system_metrics['memory_usage'] > 0.9:
                current_size = self.cache.max_size
                new_size = int(current_size * 0.8)
                self.cache.max_size = max(100, new_size)
                logger.info(f"Adjusting cache size: {current_size} -> {new_size}")

            self.performance_stats['memory_optimizations'] += 1
        except Exception as e:
            logger.error(f"Memory optimization failed: {e}")

    async def _optimize_cache(self) -> None:
        """Execute cache optimization"""
        try:
            logger.info("Executing cache optimization...")
            cache_stats = self.cache.get_cache_stats()

            if cache_stats['hit_rate'] < 0.5:
                self.cache.strategy = CacheStrategy.LFU
                logger.info("Switched cache strategy to LFU")
            elif cache_stats['hit_rate'] < 0.7:
                self.cache.strategy = CacheStrategy.ADAPTIVE
                logger.info("Switched cache strategy to ADAPTIVE")

            if self.cache.strategy == CacheStrategy.LFU:
                await self.cache._evict_lfu()

            self.performance_stats['cache_optimizations'] += 1
        except Exception as e:
            logger.error(f"Cache optimization failed: {e}")

    async def _optimize_connections(self) -> None:
        """Execute connection optimization"""
        try:
            logger.info("Executing connection optimization...")
            await self.connection_pool._cleanup_idle_connections()

            pool_stats = self.connection_pool.get_pool_stats()
            if pool_stats['average_wait_time_ms'] > 200:
                current_min = self.connection_pool.min_connections
                new_min = min(current_min + 2, self.connection_pool.max_connections)
                self.connection_pool.min_connections = new_min
                logger.info(f"Adjusting minimum connections: {current_min} -> {new_min}")

            self.performance_stats['connection_optimizations'] += 1
        except Exception as e:
            logger.error(f"Connection optimization failed: {e}")

    def get_comprehensive_stats(self) -> Dict[str, Any]:
        """Get combined performance metrics"""
        return {
            'cache_stats': self.cache.get_cache_stats(),
            'pool_stats': self.connection_pool.get_pool_stats(),
            'system_metrics': self.system_monitor.get_system_metrics(),
            'performance_stats': self.performance_stats,
            'optimization_config': self.optimization_config,
            'is_running': self.is_running
        }


class SystemMonitor:
    """System Resource Monitor"""

    def __init__(self):
        self.metrics_history: deque = deque(maxlen=1000)
        self.is_running = False
        self.monitoring_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("System monitor started")

    async def stop(self) -> None:
        self.is_running = False
        if self.monitoring_task:
            self.monitoring_task.cancel()
        logger.info("System monitor stopped")

    async def _monitoring_loop(self) -> None:
        while self.is_running:
            try:
                metrics = self._collect_system_metrics()
                self.metrics_history.append(metrics)
                await asyncio.sleep(10)
            except Exception as e:
                logger.error(f"System monitoring exception: {e}")
                await asyncio.sleep(5)

    def _collect_system_metrics(self) -> Dict[str, Any]:
        """Gather system-level metrics"""
        try:
            return {
                'timestamp': time.time(),
                'cpu_usage': psutil.cpu_percent(interval=1),
                'memory_usage': psutil.virtual_memory().percent / 100.0,
                'memory_available_gb': psutil.virtual_memory().available / (1024**3),
                'disk_usage': psutil.disk_usage('/').percent / 100.0,
                'network_io': psutil.net_io_counters()._asdict(),
                'process_count': len(psutil.pids()),
                'load_average': psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            }
        except Exception as e:
            logger.error(f"Failed to collect system metrics: {e}")
            return {
                'timestamp': time.time(),
                'cpu_usage': 0.0,
                'memory_usage': 0.0,
                'memory_available_gb': 0.0,
                'disk_usage': 0.0,
                'network_io': {},
                'process_count': 0,
                'load_average': None
            }

    def get_system_metrics(self) -> Dict[str, Any]:
        """Get latest system metrics"""
        if self.metrics_history:
            return self.metrics_history[-1]
        return self._collect_system_metrics()

    def get_metrics_history(self, minutes: int = 10) -> List[Dict[str, Any]]:
        """Get historical metrics"""
        cutoff_time = time.time() - (minutes * 60)
        return [
            metrics for metrics in self.metrics_history
            if metrics['timestamp'] > cutoff_time
        ]


# Factory helper
def create_performance_optimizer() -> PerformanceOptimizer:
    """Create PerformanceOptimizer instance"""
    return PerformanceOptimizer()


async def test_performance_optimizer():
    """Manual optimizer test"""
    optimizer = create_performance_optimizer()
    try:
        await optimizer.initialize()
        cache = optimizer.cache
        for i in range(100):
            await cache.put(f"key_{i}", f"value_{i}")
        for i in range(50):
            value = cache.get(f"key_{i}")
            print(f"Cache get key_{i}: {value}")
        stats = optimizer.get_comprehensive_stats()
        print(f"Optimizer Stats: {json.dumps(stats, indent=2, default=str)}")
        await asyncio.sleep(30)
    finally:
        await optimizer.shutdown()


if __name__ == "__main__":
    asyncio.run(test_performance_optimizer())
