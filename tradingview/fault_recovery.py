#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Fault Recovery and Monitoring System
Implements fault detection, auto-recovery, fallback source switching, and health monitoring.
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Any, Callable, Union, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum, auto
import threading
from concurrent.futures import ThreadPoolExecutor
import logging
import traceback

from tradingview.utils import get_logger

logger = get_logger(__name__)


class FaultType(Enum):
    """Types of faults"""
    CONNECTION_LOST = auto()        # Connection dropped
    DATA_TIMEOUT = auto()          # Data retrieval timeout
    AUTHENTICATION_FAILED = auto()  # Auth failure
    RATE_LIMIT_EXCEEDED = auto()   # Frequency limit
    DATA_CORRUPTION = auto()       # Malformed data
    SYSTEM_OVERLOAD = auto()       # Resources exhausted
    NETWORK_ERROR = auto()         # Infrastructure failure
    PROTOCOL_ERROR = auto()        # Framing/protocol mismatch
    UNKNOWN_ERROR = auto()         # Uncategorized


class RecoveryStrategy(Enum):
    """Strategies for recovery"""
    IMMEDIATE_RETRY = auto()       # Retry without delay
    EXPONENTIAL_BACKOFF = auto()   # Backoff with delay
    CIRCUIT_BREAKER = auto()       # Halt requests
    FALLBACK_SOURCE = auto()       # Switch data provider
    GRACEFUL_DEGRADATION = auto()  # Disable non-critical features
    MANUAL_INTERVENTION = auto()   # Signal for human help


class HealthStatus(Enum):
    """Component health status"""
    HEALTHY = auto()               # Operating normally
    DEGRADED = auto()             # Functional but issues present
    UNHEALTHY = auto()            # Operating with errors
    CRITICAL = auto()             # Non-functional
    UNKNOWN = auto()              # Status not yet determined


@dataclass
class FaultIncident:
    """Represents a specific fault event"""
    incident_id: str
    fault_type: FaultType
    component: str
    description: str
    occurred_at: float = field(default_factory=time.time)
    resolved_at: Optional[float] = None
    severity: int = 1  # 1-5 scale, 5 is max

    # Fault details
    error_message: str = ""
    stack_trace: str = ""
    affected_symbols: List[str] = field(default_factory=list)

    # Recovery tracking
    recovery_strategy: Optional[RecoveryStrategy] = None
    recovery_attempts: int = 0
    is_resolved: bool = False

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def resolve(self) -> None:
        """Mark the incident as resolved"""
        self.is_resolved = True
        self.resolved_at = time.time()

    def get_duration(self) -> float:
        """Get incident duration in seconds"""
        end_time = self.resolved_at or time.time()
        return end_time - self.occurred_at


@dataclass
class HealthMetrics:
    """Health metrics for a component"""
    component: str
    status: HealthStatus = HealthStatus.UNKNOWN
    last_check_time: float = field(default_factory=time.time)

    # Performance
    response_time_ms: float = 0.0
    success_rate: float = 1.0
    error_count: int = 0
    throughput: float = 0.0

    # Resources
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0
    connection_count: int = 0

    # Business logic
    data_quality_score: float = 1.0
    data_freshness_seconds: float = 0.0

    # Trend tracking
    status_history: deque = field(default_factory=lambda: deque(maxlen=100))

    def update_status(self, new_status: HealthStatus) -> None:
        """Transition to a new status"""
        self.status_history.append({
            'status': self.status,
            'timestamp': time.time()
        })
        self.status = new_status
        self.last_check_time = time.time()


class CircuitBreaker:
    """Implementation of the Circuit Breaker pattern"""

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60,
                 success_threshold: int = 3):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.success_threshold = success_threshold

        # State: CLOSED, OPEN, HALF_OPEN
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0
        self.state = "CLOSED"

        # Stats
        self.total_calls = 0
        self.total_failures = 0
        self.total_successes = 0

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a synchronous function through the breaker"""
        self.total_calls += 1

        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout_seconds:
                self.state = "HALF_OPEN"
                self.success_count = 0
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    async def async_call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute an asynchronous function through the breaker"""
        self.total_calls += 1

        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout_seconds:
                self.state = "HALF_OPEN"
                self.success_count = 0
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self) -> None:
        """Handle execution success"""
        self.total_successes += 1
        self.failure_count = 0

        if self.state == "HALF_OPEN":
            self.success_count += 1
            if self.success_count >= self.success_threshold:
                self.state = "CLOSED"

    def _on_failure(self) -> None:
        """Handle execution failure"""
        self.total_failures += 1
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

    def get_stats(self) -> Dict[str, Any]:
        """Get circuit breaker usage stats"""
        return {
            'state': self.state,
            'failure_count': self.failure_count,
            'success_count': self.success_count,
            'total_calls': self.total_calls,
            'total_failures': self.total_failures,
            'total_successes': self.total_successes,
            'failure_rate': self.total_failures / max(1, self.total_calls),
            'last_failure_time': self.last_failure_time
        }


class FaultDetector:
    """System fault detection layer"""

    def __init__(self):
        self.detection_rules: List[Callable] = []
        self.fault_callbacks: List[Callable] = []
        self.detection_stats = {
            'total_checks': 0,
            'faults_detected': 0,
            'false_positives': 0
        }

    def add_detection_rule(self, rule: Callable[[Dict[str, Any]], Optional[FaultIncident]]) -> None:
        """Add a custom detection rule"""
        self.detection_rules.append(rule)
        logger.info(f"Added fault detection rule: {rule.__name__}")

    def add_fault_callback(self, callback: Callable[[FaultIncident], None]) -> None:
        """Register a callback for when faults are detected"""
        self.fault_callbacks.append(callback)
        logger.info(f"Added fault callback: {callback.__name__}")

    async def check_for_faults(self, metrics: Dict[str, Any]) -> List[FaultIncident]:
        """Evaluate metrics against all detection rules"""
        self.detection_stats['total_checks'] += 1
        detected_faults = []

        try:
            for rule in self.detection_rules:
                try:
                    fault = rule(metrics)
                    if fault:
                        detected_faults.append(fault)
                        self.detection_stats['faults_detected'] += 1

                        for callback in self.fault_callbacks:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(fault)
                                else:
                                    callback(fault)
                            except Exception as e:
                                logger.error(f"Fault callback failed: {e}")

                except Exception as e:
                    logger.error(f"Fault detection rule failed: {e}")

            return detected_faults

        except Exception as e:
            logger.error(f"Fault detection failed: {e}")
            return []

    def get_detection_stats(self) -> Dict[str, Any]:
        """Get stats for the detection layer"""
        return self.detection_stats.copy()


class BackupDataSource:
    """Encapsulation of a fallback data provider"""

    def __init__(self, name: str, priority: int, client_factory: Callable):
        self.name = name
        self.priority = priority
        self.client_factory = client_factory
        self.client: Optional[Any] = None
        self.is_active = False
        self.last_used_time = 0.0

        # Performance trackers
        self.success_count = 0
        self.failure_count = 0
        self.average_latency_ms = 0.0

    async def activate(self) -> bool:
        """Switch to this backup source"""
        try:
            if not self.client:
                self.client = await self.client_factory()

            if self.client:
                self.is_active = True
                self.last_used_time = time.time()
                logger.info(f"✅ Backup source activated: {self.name}")
                return True

            return False

        except Exception as e:
            logger.error(f"❌ Failed to activate backup source {self.name}: {e}")
            return False

    async def deactivate(self) -> None:
        """Disconnect and cleanup this source"""
        try:
            if self.client and hasattr(self.client, 'disconnect'):
                await self.client.disconnect()

            self.is_active = False
            self.client = None
            logger.info(f"Backup source deactivated: {self.name}")

        except Exception as e:
            logger.error(f"Failed to deactivate backup source {self.name}: {e}")

    def record_success(self, latency_ms: float) -> None:
        """Track successful request through this source"""
        self.success_count += 1
        self.last_used_time = time.time()

        total_calls = self.success_count + self.failure_count
        if total_calls > 0:
            self.average_latency_ms = (
                (self.average_latency_ms * (total_calls - 1) + latency_ms) / total_calls
            )

    def record_failure(self) -> None:
        """Track failed request through this source"""
        self.failure_count += 1

    def get_success_rate(self) -> float:
        """Calculate source reliability"""
        total = self.success_count + self.failure_count
        return self.success_count / max(1, total)

    def get_stats(self) -> Dict[str, Any]:
        """Summary of source performance"""
        return {
            'name': self.name,
            'priority': self.priority,
            'is_active': self.is_active,
            'last_used_time': self.last_used_time,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'success_rate': self.get_success_rate(),
            'average_latency_ms': self.average_latency_ms
        }


class FaultRecoveryManager:
    """Central manager for fault detection and automated recovery"""

    def __init__(self):
        # Core components
        self.fault_detector = FaultDetector()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.backup_sources: Dict[str, List[BackupDataSource]] = defaultdict(list)

        # State management
        self.active_incidents: Dict[str, FaultIncident] = {}
        self.resolved_incidents: deque = deque(maxlen=1000)

        # Health tracking
        self.health_metrics: Dict[str, HealthMetrics] = {}
        self.health_check_callbacks: Dict[str, Callable] = {}

        # Config
        self.recovery_config = {
            'max_retry_attempts': 3,
            'backoff_base_seconds': 2,
            'max_backoff_seconds': 300,
            'health_check_interval': 30,
            'circuit_breaker_enabled': True
        }

        # Running tasks
        self.is_running = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.recovery_tasks: Set[asyncio.Task] = set()

        # Aggregate stats
        self.recovery_stats = {
            'total_incidents': 0,
            'resolved_incidents': 0,
            'active_incidents': 0,
            'successful_recoveries': 0,
            'failed_recoveries': 0,
            'backup_source_switches': 0
        }

        self._setup_default_detection_rules()

    def _setup_default_detection_rules(self) -> None:
        """Setup base heuristic detection logic"""

        def connection_timeout_rule(metrics: Dict[str, Any]) -> Optional[FaultIncident]:
            """Detect sluggish components"""
            response_time = metrics.get('response_time_ms', 0)
            if response_time > 5000:
                return FaultIncident(
                    incident_id=f"timeout_{int(time.time())}",
                    fault_type=FaultType.DATA_TIMEOUT,
                    component=metrics.get('component', 'unknown'),
                    description=f"High response time: {response_time}ms",
                    severity=3
                )
            return None

        def success_rate_rule(metrics: Dict[str, Any]) -> Optional[FaultIncident]:
            """Detect elevated error rates"""
            success_rate = metrics.get('success_rate', 1.0)
            if success_rate < 0.8:
                return FaultIncident(
                    incident_id=f"low_success_{int(time.time())}",
                    fault_type=FaultType.SYSTEM_OVERLOAD,
                    component=metrics.get('component', 'unknown'),
                    description=f"Success rate too low: {success_rate:.1%}",
                    severity=4
                )
            return None

        def data_quality_rule(metrics: Dict[str, Any]) -> Optional[FaultIncident]:
            """Detect data integrity issues"""
            quality_score = metrics.get('data_quality_score', 1.0)
            if quality_score < 0.5:
                return FaultIncident(
                    incident_id=f"poor_quality_{int(time.time())}",
                    fault_type=FaultType.DATA_CORRUPTION,
                    component=metrics.get('component', 'unknown'),
                    description=f"Extreme quality drop: {quality_score:.1%}",
                    severity=3
                )
            return None

        self.fault_detector.add_detection_rule(connection_timeout_rule)
        self.fault_detector.add_detection_rule(success_rate_rule)
        self.fault_detector.add_detection_rule(data_quality_rule)

        self.fault_detector.add_fault_callback(self._handle_detected_fault)

    async def start(self) -> None:
        """Initialize the recovery management loop"""
        if self.is_running:
            return

        self.is_running = True
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        logger.info("✅ Fault recovery manager started")

    async def stop(self) -> None:
        """Shutdown the manager and cleanup resources"""
        self.is_running = False

        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass

        for task in list(self.recovery_tasks):
            task.cancel()

        if self.recovery_tasks:
            await asyncio.gather(*self.recovery_tasks, return_exceptions=True)

        for sources in self.backup_sources.values():
            for source in sources:
                await source.deactivate()

        logger.info("Fault recovery manager stopped")

    def register_component(self, component_name: str, health_check_callback: Callable) -> None:
        """Register a component for active health monitoring"""
        self.health_check_callbacks[component_name] = health_check_callback
        self.health_metrics[component_name] = HealthMetrics(component=component_name)
        logger.info(f"Registered component for monitoring: {component_name}")

    def add_backup_source(self, component: str, source: BackupDataSource) -> None:
        """Assign a fallback source to a component"""
        self.backup_sources[component].append(source)
        self.backup_sources[component].sort(key=lambda x: x.priority)
        logger.info(f"Added backup source for {component}: {source.name} (Priority: {source.priority})")

    def get_circuit_breaker(self, component: str) -> CircuitBreaker:
        """Access the breaker instance for a component"""
        if component not in self.circuit_breakers:
            self.circuit_breakers[component] = CircuitBreaker()
        return self.circuit_breakers[component]

    async def _monitoring_loop(self) -> None:
        """Component polling loop"""
        while self.is_running:
            try:
                for component_name, health_callback in self.health_check_callbacks.items():
                    try:
                        if asyncio.iscoroutinefunction(health_callback):
                            metrics = await health_callback()
                        else:
                            metrics = health_callback()

                        if component_name in self.health_metrics:
                            health_metric = self.health_metrics[component_name]
                            self._update_health_metrics(health_metric, metrics)

                        metrics['component'] = component_name
                        await self.fault_detector.check_for_faults(metrics)

                    except Exception as e:
                        logger.error(f"Health check failed for {component_name}: {e}")

                        incident = FaultIncident(
                            incident_id=f"health_check_fail_{component_name}_{int(time.time())}",
                            fault_type=FaultType.UNKNOWN_ERROR,
                            component=component_name,
                            description=f"Polling failed: {str(e)}",
                            error_message=str(e),
                            stack_trace=traceback.format_exc(),
                            severity=2
                        )

                        await self._handle_detected_fault(incident)

                await asyncio.sleep(self.recovery_config['health_check_interval'])

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")
                await asyncio.sleep(5)

    def _update_health_metrics(self, health_metric: HealthMetrics, metrics: Dict[str, Any]) -> None:
        """Merge poll results into local metrics state"""
        try:
            health_metric.response_time_ms = metrics.get('response_time_ms', 0.0)
            health_metric.success_rate = metrics.get('success_rate', 1.0)
            health_metric.error_count = metrics.get('error_count', 0)
            health_metric.throughput = metrics.get('throughput', 0.0)
            health_metric.memory_usage_mb = metrics.get('memory_usage_mb', 0.0)
            health_metric.cpu_usage_percent = metrics.get('cpu_usage_percent', 0.0)
            health_metric.connection_count = metrics.get('connection_count', 0)
            health_metric.data_quality_score = metrics.get('data_quality_score', 1.0)
            health_metric.data_freshness_seconds = metrics.get('data_freshness_seconds', 0.0)

            new_status = self._calculate_health_status(health_metric)
            health_metric.update_status(new_status)

        except Exception as e:
            logger.error(f"Metric update failed: {e}")

    def _calculate_health_status(self, metrics: HealthMetrics) -> HealthStatus:
        """Map metrics to a health status level"""
        try:
            if metrics.success_rate < 0.5:
                return HealthStatus.CRITICAL
            elif metrics.success_rate < 0.8:
                return HealthStatus.UNHEALTHY
            elif metrics.response_time_ms > 5000:
                return HealthStatus.DEGRADED
            elif metrics.data_quality_score < 0.7:
                return HealthStatus.DEGRADED
            else:
                return HealthStatus.HEALTHY

        except Exception as e:
            logger.error(f"Status calculation failed: {e}")
            return HealthStatus.UNKNOWN

    async def _handle_detected_fault(self, incident: FaultIncident) -> None:
        """Trigger recovery process for new incidents"""
        try:
            logger.warning(f"🚨 Fault detected: {incident.fault_type.name} - {incident.description}")

            self.active_incidents[incident.incident_id] = incident
            self.recovery_stats['total_incidents'] += 1
            self.recovery_stats['active_incidents'] = len(self.active_incidents)

            strategy = self._determine_recovery_strategy(incident)
            incident.recovery_strategy = strategy

            recovery_task = asyncio.create_task(
                self._execute_recovery_strategy(incident)
            )
            self.recovery_tasks.add(recovery_task)
            recovery_task.add_done_callback(self.recovery_tasks.discard)

        except Exception as e:
            logger.error(f"Fault handling failed: {e}")

    def _determine_recovery_strategy(self, incident: FaultIncident) -> RecoveryStrategy:
        """Choose optimal recovery path based on fault profile"""
        try:
            if incident.fault_type in [FaultType.CONNECTION_LOST, FaultType.NETWORK_ERROR]:
                return RecoveryStrategy.EXPONENTIAL_BACKOFF
            elif incident.fault_type == FaultType.RATE_LIMIT_EXCEEDED:
                return RecoveryStrategy.CIRCUIT_BREAKER
            elif incident.fault_type in [FaultType.DATA_TIMEOUT, FaultType.DATA_CORRUPTION]:
                return RecoveryStrategy.FALLBACK_SOURCE
            elif incident.severity >= 4:
                return RecoveryStrategy.MANUAL_INTERVENTION
            else:
                return RecoveryStrategy.IMMEDIATE_RETRY

        except Exception as e:
            logger.error(f"Strategy selection failed: {e}")
            return RecoveryStrategy.IMMEDIATE_RETRY

    async def _execute_recovery_strategy(self, incident: FaultIncident) -> None:
        """Dispatch incident to recovery logic"""
        try:
            strategy = incident.recovery_strategy
            component = incident.component

            logger.info(f"Executing recovery: {strategy.name} for {component}")

            if strategy == RecoveryStrategy.IMMEDIATE_RETRY:
                await self._immediate_retry_recovery(incident)
            elif strategy == RecoveryStrategy.EXPONENTIAL_BACKOFF:
                await self._exponential_backoff_recovery(incident)
            elif strategy == RecoveryStrategy.CIRCUIT_BREAKER:
                await self._circuit_breaker_recovery(incident)
            elif strategy == RecoveryStrategy.FALLBACK_SOURCE:
                await self._fallback_source_recovery(incident)
            elif strategy == RecoveryStrategy.GRACEFUL_DEGRADATION:
                await self._graceful_degradation_recovery(incident)
            elif strategy == RecoveryStrategy.MANUAL_INTERVENTION:
                await self._manual_intervention_recovery(incident)

        except Exception as e:
            logger.error(f"Recovery execution failed: {e}")
            incident.recovery_attempts += 1
            self.recovery_stats['failed_recoveries'] += 1

    async def _immediate_retry_recovery(self, incident: FaultIncident) -> None:
        """Retry logic for transient glitches"""
        max_attempts = self.recovery_config['max_retry_attempts']

        for attempt in range(max_attempts):
            try:
                incident.recovery_attempts += 1
                component = incident.component
                if component in self.health_check_callbacks:
                    callback = self.health_check_callbacks[component]

                    if asyncio.iscoroutinefunction(callback):
                        metrics = await callback()
                    else:
                        metrics = callback()

                    if metrics.get('success_rate', 0) > 0.8:
                        incident.resolve()
                        self._mark_incident_resolved(incident)
                        logger.info(f"✅ Immediate retry successful for: {incident.component}")
                        return

                if attempt < max_attempts - 1:
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"Immediate retry attempt {attempt + 1}/{max_attempts} failed: {e}")

        self.recovery_stats['failed_recoveries'] += 1
        logger.error(f"❌ Immediate retry failed for: {incident.component}")

    async def _exponential_backoff_recovery(self, incident: FaultIncident) -> None:
        """Retry logic for networking issues"""
        max_attempts = self.recovery_config['max_retry_attempts']
        base_delay = self.recovery_config['backoff_base_seconds']
        max_delay = self.recovery_config['max_backoff_seconds']

        for attempt in range(max_attempts):
            try:
                incident.recovery_attempts += 1
                delay = min(base_delay * (2 ** attempt), max_delay)
                logger.info(f"Backoff retry attempt {attempt + 1}/{max_attempts}: waiting {delay}s")

                await asyncio.sleep(delay)

                component = incident.component
                if component in self.health_check_callbacks:
                    callback = self.health_check_callbacks[component]

                    if asyncio.iscoroutinefunction(callback):
                        metrics = await callback()
                    else:
                        metrics = callback()

                    if metrics.get('success_rate', 0) > 0.8:
                        incident.resolve()
                        self._mark_incident_resolved(incident)
                        logger.info(f"✅ Backoff retry successful for: {incident.component}")
                        return

            except Exception as e:
                logger.error(f"Backoff retry failed: {e}")

        self.recovery_stats['failed_recoveries'] += 1
        logger.error(f"❌ Backoff retry failed for: {incident.component}")

    async def _fallback_source_recovery(self, incident: FaultIncident) -> None:
        """Logic for switching to backup providers"""
        try:
            component = incident.component
            backup_sources = self.backup_sources.get(component, [])

            if not backup_sources:
                logger.warning(f"No backup sources configured for: {component}")
                self.recovery_stats['failed_recoveries'] += 1
                return

            for source in backup_sources:
                try:
                    logger.info(f"Attempting switch to backup: {source.name}")

                    if await source.activate():
                        incident.resolve()
                        self._mark_incident_resolved(incident)
                        self.recovery_stats['backup_source_switches'] += 1
                        logger.info(f"✅ Fallback switch successful to: {source.name}")
                        return

                except Exception as e:
                    logger.error(f"Failed to activate backup {source.name}: {e}")
                    source.record_failure()

            self.recovery_stats['failed_recoveries'] += 1
            logger.error(f"❌ All fallback sources failed for: {component}")

        except Exception as e:
            logger.error(f"Fallback recovery error: {e}")
            self.recovery_stats['failed_recoveries'] += 1

    async def _circuit_breaker_recovery(self, incident: FaultIncident) -> None:
        """Circuit breaker management"""
        try:
            component = incident.component
            circuit_breaker = self.get_circuit_breaker(component)

            # Force trip
            circuit_breaker.state = "OPEN"
            circuit_breaker.last_failure_time = time.time()

            logger.info(f"Circuit breaker tripped for: {component}")

            # Wait for cooling period
            await asyncio.sleep(circuit_breaker.timeout_seconds)

            circuit_breaker.state = "HALF_OPEN"
            circuit_breaker.success_count = 0

            incident.resolve()
            self._mark_incident_resolved(incident)
            logger.info(f"✅ Circuit breaker entered HALF_OPEN for: {component}")

        except Exception as e:
            logger.error(f"Breaker recovery failed: {e}")
            self.recovery_stats['failed_recoveries'] += 1

    async def _graceful_degradation_recovery(self, incident: FaultIncident) -> None:
        """Logic for scaling back features"""
        try:
            logger.info(f"Enabling graceful degradation for: {incident.component}")
            incident.resolve()
            self._mark_incident_resolved(incident)

        except Exception as e:
            logger.error(f"Degradation logic failed: {e}")
            self.recovery_stats['failed_recoveries'] += 1

    async def _manual_intervention_recovery(self, incident: FaultIncident) -> None:
        """Handling for critical non-recoverable faults"""
        try:
            logger.critical(f"🚨 Manual intervention required: {incident.description}")
            logger.critical(f"Component: {incident.component}, Severity: {incident.severity}")
            logger.critical(f"Incident ID: {incident.incident_id}")
            # Integration with paging systems would go here

        except Exception as e:
            logger.error(f"Manual intervention escalation failed: {e}")

    def _mark_incident_resolved(self, incident: FaultIncident) -> None:
        """Update state to reflected resolution"""
        try:
            if incident.incident_id in self.active_incidents:
                del self.active_incidents[incident.incident_id]
                self.resolved_incidents.append(incident)

                self.recovery_stats['resolved_incidents'] += 1
                self.recovery_stats['active_incidents'] = len(self.active_incidents)
                self.recovery_stats['successful_recoveries'] += 1

                logger.info(f"Incident resolved: {incident.incident_id} (Duration: {incident.get_duration():.1f}s)")

        except Exception as e:
            logger.error(f"State transition to resolved failed: {e}")

    def get_system_health_report(self) -> Dict[str, Any]:
        """Generate high-level health report"""
        try:
            healthy_count = sum(1 for m in self.health_metrics.values()
                                   if m.status == HealthStatus.HEALTHY)
            total_count = len(self.health_metrics)
            health_ratio = healthy_count / max(1, total_count)

            if health_ratio >= 0.9:
                overall_status = HealthStatus.HEALTHY
            elif health_ratio >= 0.7:
                overall_status = HealthStatus.DEGRADED
            elif health_ratio >= 0.5:
                overall_status = HealthStatus.UNHEALTHY
            else:
                overall_status = HealthStatus.CRITICAL

            return {
                'overall_status': overall_status.name,
                'overall_health_ratio': health_ratio,
                'total_components': total_count,
                'healthy_components': healthy_count,
                'active_incidents': len(self.active_incidents),
                'total_incidents_today': self._count_incidents_today(),
                'recovery_stats': self.recovery_stats,
                'component_health': {
                    component: {
                        'status': metrics.status.name,
                        'success_rate': metrics.success_rate,
                        'response_time_ms': metrics.response_time_ms,
                        'data_quality_score': metrics.data_quality_score,
                        'last_check_time': metrics.last_check_time
                    }
                    for component, metrics in self.health_metrics.items()
                },
                'circuit_breaker_stats': {
                    component: breaker.get_stats()
                    for component, breaker in self.circuit_breakers.items()
                },
                'backup_source_stats': {
                    component: [source.get_stats() for source in sources]
                    for component, sources in self.backup_sources.items()
                }
            }

        except Exception as e:
            logger.error(f"Report generation failed: {e}")
            return {}

    def _count_incidents_today(self) -> int:
        """Tally occurrences since midnight local time"""
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
            count = 0

            for incident in self.active_incidents.values():
                if incident.occurred_at >= today_start:
                    count += 1
            for incident in self.resolved_incidents:
                if incident.occurred_at >= today_start:
                    count += 1
            return count

        except Exception as e:
            logger.error(f"Daily count failed: {e}")
            return 0


def create_fault_recovery_manager() -> FaultRecoveryManager:
    """Factory to create a recovery manager"""
    return FaultRecoveryManager()


async def test_fault_recovery():
    """System test for recovery mechanisms"""
    manager = create_fault_recovery_manager()

    try:
        await manager.start()

        async def mock_health_check():
            return {
                'response_time_ms': 100,
                'success_rate': 0.95,
                'data_quality_score': 0.9,
                'error_count': 1
            }

        manager.register_component('test_component', mock_health_check)

        async def mock_backup_client():
            return "mock_backup_client"

        backup_source = BackupDataSource(
            name='backup_test',
            priority=1,
            client_factory=mock_backup_client
        )

        manager.add_backup_source('test_component', backup_source)

        await asyncio.sleep(2)

        fault_incident = FaultIncident(
            incident_id="test_fault_001",
            fault_type=FaultType.CONNECTION_LOST,
            component="test_component",
            description="Simulated connection drop",
            severity=3
        )

        await manager._handle_detected_fault(fault_incident)

        await asyncio.sleep(5)

        health_report = manager.get_system_health_report()
        print(f"System Health Report: {json.dumps(health_report, indent=2, default=str)}")

    finally:
        await manager.stop()


if __name__ == "__main__":
    asyncio.run(test_fault_recovery())
