#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Connection Health Monitoring System
Implements connection quality assessment, anomaly detection, and auto-recovery.
"""

import asyncio
import time
import statistics
from typing import Dict, List, Optional, Callable, Any, Tuple
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto

from tradingview.utils import get_logger

logger = get_logger(__name__)


class HealthStatus(Enum):
    """Health status enum"""
    EXCELLENT = auto()    # 90-100%
    GOOD = auto()         # 70-89%
    FAIR = auto()         # 50-69%
    POOR = auto()         # 30-49%
    CRITICAL = auto()     # 0-29%


class AlertLevel(Enum):
    """Alert levels"""
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass
class HealthMetrics:
    """Health metrics structure"""
    timestamp: float = field(default_factory=time.time)

    # Connection metrics
    is_connected: bool = False
    connection_uptime: float = 0.0
    total_reconnects: int = 0

    # Latency metrics
    current_latency: float = 0.0
    average_latency: float = 0.0
    max_latency: float = 0.0
    latency_variance: float = 0.0

    # Error metrics
    error_count: int = 0
    error_rate: float = 0.0
    last_error_time: Optional[float] = None

    # Message metrics
    messages_received: int = 0
    messages_processed: int = 0
    message_loss_rate: float = 0.0
    processing_rate: float = 0.0

    # Data quality metrics
    data_quality_score: float = 1.0
    data_freshness: float = 0.0
    data_completeness: float = 1.0

    # Overall score
    overall_health_score: float = 1.0
    health_status: HealthStatus = HealthStatus.EXCELLENT


@dataclass
class HealthAlert:
    """Health alert structure"""
    alert_id: str
    level: AlertLevel
    title: str
    message: str
    timestamp: float = field(default_factory=time.time)
    metric_name: str = ""
    current_value: Any = None
    threshold: Any = None
    resolved: bool = False


class HealthThresholds:
    """Health threshold configuration"""

    def __init__(self):
        # Latency thresholds (ms)
        self.latency_warning = 1000
        self.latency_error = 3000
        self.latency_critical = 5000

        # Error rate thresholds
        self.error_rate_warning = 0.05   # 5%
        self.error_rate_error = 0.15     # 15%
        self.error_rate_critical = 0.30  # 30%

        # Message loss rate thresholds
        self.message_loss_warning = 0.01  # 1%
        self.message_loss_error = 0.05    # 5%
        self.message_loss_critical = 0.10 # 10%

        # Data quality thresholds
        self.data_quality_warning = 0.90
        self.data_quality_error = 0.80
        self.data_quality_critical = 0.70

        # Data freshness thresholds (seconds)
        self.data_freshness_warning = 60
        self.data_freshness_error = 300
        self.data_freshness_critical = 600

        # Overall health score thresholds
        self.health_score_warning = 0.70
        self.health_score_error = 0.50
        self.health_score_critical = 0.30


class MetricsCollector:
    """Collector for system metrics"""

    def __init__(self, window_size: int = 1000):
        self.window_size = window_size

        # Latency data
        self.latency_history: deque = deque(maxlen=window_size)
        self.ping_times: Dict[str, float] = {}

        # Error data
        self.error_history: deque = deque(maxlen=window_size)
        self.error_types: defaultdict = defaultdict(int)

        # Message data
        self.message_stats = {
            'received': 0,
            'processed': 0,
            'failed': 0,
            'last_received_time': 0,
            'processing_times': deque(maxlen=window_size)
        }

        # Connection data
        self.connection_stats = {
            'connect_time': 0,
            'disconnect_count': 0,
            'reconnect_count': 0,
            'total_uptime': 0
        }

        # Data quality
        self.data_quality_history: deque = deque(maxlen=100)

    def record_ping(self, ping_id: str) -> None:
        """Record a ping transmission"""
        self.ping_times[ping_id] = time.time()

    def record_pong(self, ping_id: str) -> None:
        """Record a pong reception"""
        if ping_id in self.ping_times:
            latency = (time.time() - self.ping_times[ping_id]) * 1000
            self.latency_history.append(latency)
            del self.ping_times[ping_id]

    def record_error(self, error_type: str, error_msg: str) -> None:
        """Record a system error"""
        self.error_history.append({
            'type': error_type,
            'message': error_msg,
            'timestamp': time.time()
        })
        self.error_types[error_type] += 1

    def record_message_received(self) -> None:
        """Record message reception"""
        self.message_stats['received'] += 1
        self.message_stats['last_received_time'] = time.time()

    def record_message_processed(self, processing_time: float) -> None:
        """Record message processing completion"""
        self.message_stats['processed'] += 1
        self.message_stats['processing_times'].append(processing_time)

    def record_message_failed(self) -> None:
        """Record message processing failure"""
        self.message_stats['failed'] += 1

    def record_connection_event(self, event_type: str) -> None:
        """Record connection state events"""
        if event_type == 'connect':
            self.connection_stats['connect_time'] = time.time()
        elif event_type == 'disconnect':
            self.connection_stats['disconnect_count'] += 1
        elif event_type == 'reconnect':
            self.connection_stats['reconnect_count'] += 1

    def record_data_quality(self, quality_score: float) -> None:
        """Record observed data quality score"""
        self.data_quality_history.append({
            'score': quality_score,
            'timestamp': time.time()
        })

    def get_current_metrics(self) -> HealthMetrics:
        """Calculate and return current health metrics"""
        current_time = time.time()

        # Latency
        current_latency = self.latency_history[-1] if self.latency_history else 0
        avg_latency = statistics.mean(self.latency_history) if self.latency_history else 0
        max_latency = max(self.latency_history) if self.latency_history else 0
        latency_variance = statistics.variance(self.latency_history) if len(self.latency_history) > 1 else 0

        # Error metrics (last 5 minutes)
        recent_errors = [
            err for err in self.error_history
            if current_time - err['timestamp'] < 300
        ]
        error_count = len(recent_errors)
        total_operations = self.message_stats['received'] + self.message_stats['processed']
        error_rate = error_count / max(1, total_operations)

        # Message metrics
        messages_received = self.message_stats['received']
        messages_processed = self.message_stats['processed']
        messages_failed = self.message_stats['failed']
        message_loss_rate = messages_failed / max(1, messages_received)

        avg_processing_time = 0
        if self.message_stats['processing_times']:
            avg_processing_time = statistics.mean(self.message_stats['processing_times'])
        processing_rate = messages_processed / max(1, avg_processing_time) if avg_processing_time > 0 else 0

        # Connection uptime
        connection_uptime = 0
        if self.connection_stats['connect_time'] > 0:
            connection_uptime = current_time - self.connection_stats['connect_time']

        # Data quality metrics
        data_quality_score = 1.0
        data_freshness = 0
        data_completeness = 1.0

        if self.data_quality_history:
            recent_quality = [
                q['score'] for q in self.data_quality_history
                if current_time - q['timestamp'] < 300
            ]
            if recent_quality:
                data_quality_score = statistics.mean(recent_quality)

        if self.message_stats['last_received_time'] > 0:
            data_freshness = current_time - self.message_stats['last_received_time']

        # Overall scoring logic
        health_factors = [
            1.0 - min(1.0, avg_latency / 5000),  # Latency factor
            1.0 - min(1.0, error_rate),          # Error factor
            1.0 - min(1.0, message_loss_rate),   # Loss factor
            data_quality_score,                  # Quality factor
            min(1.0, connection_uptime / 3600)   # Stability factor
        ]

        overall_health_score = sum(health_factors) / len(health_factors)

        # Map score to status
        if overall_health_score >= 0.9:
            health_status = HealthStatus.EXCELLENT
        elif overall_health_score >= 0.7:
            health_status = HealthStatus.GOOD
        elif overall_health_score >= 0.5:
            health_status = HealthStatus.FAIR
        elif overall_health_score >= 0.3:
            health_status = HealthStatus.POOR
        else:
            health_status = HealthStatus.CRITICAL

        return HealthMetrics(
            timestamp=current_time,
            is_connected=self.connection_stats['connect_time'] > 0,
            connection_uptime=connection_uptime,
            total_reconnects=self.connection_stats['reconnect_count'],
            current_latency=current_latency,
            average_latency=avg_latency,
            max_latency=max_latency,
            latency_variance=latency_variance,
            error_count=error_count,
            error_rate=error_rate,
            last_error_time=recent_errors[-1]['timestamp'] if recent_errors else None,
            messages_received=messages_received,
            messages_processed=messages_processed,
            message_loss_rate=message_loss_rate,
            processing_rate=processing_rate,
            data_quality_score=data_quality_score,
            data_freshness=data_freshness,
            data_completeness=data_completeness,
            overall_health_score=overall_health_score,
            health_status=health_status
        )


class AlertManager:
    """Manager for system alerts"""

    def __init__(self, max_alerts: int = 1000):
        self.max_alerts = max_alerts
        self.alerts: deque = deque(maxlen=max_alerts)
        self.active_alerts: Dict[str, HealthAlert] = {}
        self.alert_callbacks: List[Callable] = []
        self.alert_count = 0

    def add_alert_callback(self, callback: Callable[[HealthAlert], None]) -> None:
        """Register a callback for new alerts"""
        self.alert_callbacks.append(callback)

    def create_alert(self,
                    level: AlertLevel,
                    title: str,
                    message: str,
                    metric_name: str = "",
                    current_value: Any = None,
                    threshold: Any = None) -> HealthAlert:
        """Create and publish a new alert"""
        alert_id = f"alert_{self.alert_count}_{int(time.time())}"
        self.alert_count += 1

        alert = HealthAlert(
            alert_id=alert_id,
            level=level,
            title=title,
            message=message,
            metric_name=metric_name,
            current_value=current_value,
            threshold=threshold
        )

        self.alerts.append(alert)
        self.active_alerts[alert_id] = alert

        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

        logger.warning(f"Health alert raised [{level.name}]: {title}")
        return alert

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved"""
        if alert_id in self.active_alerts:
            alert = self.active_alerts[alert_id]
            alert.resolved = True
            del self.active_alerts[alert_id]

            logger.info(f"Alert resolved: {alert.title}")
            return True
        return False

    def get_active_alerts(self, level: Optional[AlertLevel] = None) -> List[HealthAlert]:
        """Retrieve current active alerts"""
        alerts = list(self.active_alerts.values())
        if level:
            alerts = [alert for alert in alerts if alert.level == level]
        return sorted(alerts, key=lambda x: x.timestamp, reverse=True)

    def get_alert_summary(self) -> Dict[str, int]:
        """Summarize active alerts by level"""
        summary = {level.name: 0 for level in AlertLevel}
        for alert in self.active_alerts.values():
            summary[alert.level.name] += 1
        return summary


class ConnectionHealthMonitor:
    """Monitor for connection health and automatic recovery"""

    def __init__(self,
                 check_interval: float = 30.0,
                 enable_auto_recovery: bool = True):

        self.check_interval = check_interval
        self.enable_auto_recovery = enable_auto_recovery

        # Core components
        self.metrics_collector = MetricsCollector()
        self.alert_manager = AlertManager()
        self.thresholds = HealthThresholds()

        # Monitor state
        self.is_monitoring = False
        self.monitor_task: Optional[asyncio.Task] = None

        # Health history
        self.health_history: deque = deque(maxlen=1000)

        # Callbacks
        self.health_callbacks: List[Callable] = []
        self.recovery_callbacks: List[Callable] = []

        # Auto-recovery state
        self.auto_recovery_attempts = 0
        self.max_recovery_attempts = 3
        self.recovery_cooldown = 300  # 5 minutes
        self.last_recovery_time = 0

    async def start_monitoring(self) -> None:
        """Start the health monitoring loop"""
        if self.is_monitoring:
            return

        self.is_monitoring = True
        self.monitor_task = asyncio.create_task(self._monitoring_loop())
        logger.info("Connection health monitoring started")

    async def stop_monitoring(self) -> None:
        """Stop the health monitoring loop"""
        self.is_monitoring = False

        if self.monitor_task:
            self.monitor_task.cancel()
            try:
                await self.monitor_task
            except asyncio.CancelledError:
                pass

        logger.info("Connection health monitoring stopped")

    def add_health_callback(self, callback: Callable[[HealthMetrics], None]) -> None:
        """Register a health status update callback"""
        self.health_callbacks.append(callback)

    def add_recovery_callback(self, callback: Callable[[], None]) -> None:
        """Register a recovery action callback"""
        self.recovery_callbacks.append(callback)

    async def _monitoring_loop(self) -> None:
        """Monitoring loop logic"""
        while self.is_monitoring:
            try:
                # Collect
                current_metrics = self.metrics_collector.get_current_metrics()
                self.health_history.append(current_metrics)

                # Check and Alert
                await self._check_health_and_alert(current_metrics)

                # Notify
                for callback in self.health_callbacks:
                    try:
                        await callback(current_metrics)
                    except Exception as e:
                        logger.error(f"Health status callback failed: {e}")

                # Recover
                if self.enable_auto_recovery:
                    await self._check_auto_recovery(current_metrics)

                await asyncio.sleep(self.check_interval)

            except Exception as e:
                logger.error(f"Health monitoring loop error: {e}")
                await asyncio.sleep(5)

    async def _check_health_and_alert(self, metrics: HealthMetrics) -> None:
        """Check metrics against thresholds and raise alerts"""
        try:
            # Latency checks
            if metrics.average_latency > self.thresholds.latency_critical:
                self.alert_manager.create_alert(
                    AlertLevel.CRITICAL,
                    "Extreme Connection Latency",
                    f"Average latency {metrics.average_latency:.1f}ms exceeds critical threshold",
                    "average_latency",
                    metrics.average_latency,
                    self.thresholds.latency_critical
                )
            elif metrics.average_latency > self.thresholds.latency_error:
                self.alert_manager.create_alert(
                    AlertLevel.ERROR,
                    "High Connection Latency",
                    f"Average latency {metrics.average_latency:.1f}ms exceeds error threshold",
                    "average_latency",
                    metrics.average_latency,
                    self.thresholds.latency_error
                )
            elif metrics.average_latency > self.thresholds.latency_warning:
                self.alert_manager.create_alert(
                    AlertLevel.WARNING,
                    "Connection Latency Warning",
                    f"Average latency {metrics.average_latency:.1f}ms exceeds warning threshold",
                    "average_latency",
                    metrics.average_latency,
                    self.thresholds.latency_warning
                )

            # Error rate checks
            if metrics.error_rate > self.thresholds.error_rate_critical:
                self.alert_manager.create_alert(
                    AlertLevel.CRITICAL,
                    "Extreme Error Rate",
                    f"Error rate {metrics.error_rate:.1%} exceeds critical threshold",
                    "error_rate",
                    metrics.error_rate,
                    self.thresholds.error_rate_critical
                )

            # Data quality checks
            if metrics.data_quality_score < self.thresholds.data_quality_critical:
                self.alert_manager.create_alert(
                    AlertLevel.CRITICAL,
                    "Severe Data Quality Degradation",
                    f"Quality score {metrics.data_quality_score:.2f} below critical threshold",
                    "data_quality_score",
                    metrics.data_quality_score,
                    self.thresholds.data_quality_critical
                )

            # Freshness checks
            if metrics.data_freshness > self.thresholds.data_freshness_critical:
                self.alert_manager.create_alert(
                    AlertLevel.CRITICAL,
                    "Data Update Stagnation",
                    f"Data has not updated for {metrics.data_freshness:.0f} seconds",
                    "data_freshness",
                    metrics.data_freshness,
                    self.thresholds.data_freshness_critical
                )

        except Exception as e:
            logger.error(f"Health assessment failed: {e}")

    async def _check_auto_recovery(self, metrics: HealthMetrics) -> None:
        """Trigger auto-recovery if conditions met"""
        try:
            current_time = time.time()

            # Check if recovery needed
            needs_recovery = (
                metrics.health_status in [HealthStatus.POOR, HealthStatus.CRITICAL] or
                not metrics.is_connected or
                metrics.error_rate > self.thresholds.error_rate_error
            )

            if not needs_recovery:
                self.auto_recovery_attempts = 0
                return

            # Check cooldown
            if current_time - self.last_recovery_time < self.recovery_cooldown:
                return

            # Check limits
            if self.auto_recovery_attempts >= self.max_recovery_attempts:
                logger.warning("Max auto-recovery attempts reached")
                return

            # Execute
            logger.info(f"Executing auto-recovery (Attempt #{self.auto_recovery_attempts + 1})")

            for callback in self.recovery_callbacks:
                try:
                    await callback()
                except Exception as e:
                    logger.error(f"Recovery callback failed: {e}")

            self.auto_recovery_attempts += 1
            self.last_recovery_time = current_time

        except Exception as e:
            logger.error(f"Auto-recovery check failed: {e}")

    def get_health_report(self) -> Dict[str, Any]:
        """Generate a complete health report"""
        if not self.health_history:
            return {}

        latest_metrics = self.health_history[-1]

        # Calculate trend
        if len(self.health_history) >= 2:
            previous_metrics = self.health_history[-2]
            health_trend = latest_metrics.overall_health_score - previous_metrics.overall_health_score
        else:
            health_trend = 0.0

        return {
            'current_health': {
                'status': latest_metrics.health_status.name,
                'score': latest_metrics.overall_health_score,
                'trend': health_trend
            },
            'connection': {
                'is_connected': latest_metrics.is_connected,
                'uptime': latest_metrics.connection_uptime,
                'reconnects': latest_metrics.total_reconnects
            },
            'performance': {
                'current_latency': latest_metrics.current_latency,
                'average_latency': latest_metrics.average_latency,
                'max_latency': latest_metrics.max_latency,
                'processing_rate': latest_metrics.processing_rate
            },
            'quality': {
                'data_quality_score': latest_metrics.data_quality_score,
                'data_freshness': latest_metrics.data_freshness,
                'message_loss_rate': latest_metrics.message_loss_rate
            },
            'alerts': {
                'active_count': len(self.alert_manager.active_alerts),
                'summary': self.alert_manager.get_alert_summary(),
                'recent_alerts': [
                    {
                        'level': alert.level.name,
                        'title': alert.title,
                        'timestamp': alert.timestamp
                    }
                    for alert in self.alert_manager.get_active_alerts()[:5]
                ]
            },
            'auto_recovery': {
                'enabled': self.enable_auto_recovery,
                'attempts': self.auto_recovery_attempts,
                'last_recovery': self.last_recovery_time
            }
        }
