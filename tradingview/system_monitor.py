#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView System Comprehensive Monitoring Manager
Unified monitoring integrating connection health, data quality, performance optimization, and fault recovery.
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import deque, defaultdict
from enum import Enum, auto
import logging
import threading

from .enhanced_client import EnhancedTradingViewClient
from .data_quality_monitor import DataQualityEngine
from .connection_health import ConnectionHealthMonitor
from .performance_optimizer import PerformanceOptimizer
from .fault_recovery import FaultRecoveryManager
from .trading_integration import TradingCoreIntegrationManager
from .realtime_adapter import AdvancedRealtimeAdapter

from tradingview.utils import get_logger

logger = get_logger(__name__)


class SystemStatus(Enum):
    """System Status"""
    STARTING = auto()      # Starting up
    HEALTHY = auto()       # Healthy
    DEGRADED = auto()      # Degraded
    WARNING = auto()       # Warning
    CRITICAL = auto()      # Critical
    OFFLINE = auto()       # Offline


class AlertLevel(Enum):
    """Alert Level"""
    INFO = auto()
    WARNING = auto()
    ERROR = auto()
    CRITICAL = auto()


@dataclass
class SystemAlert:
    """System Alert"""
    alert_id: str
    level: AlertLevel
    component: str
    title: str
    message: str
    timestamp: float = field(default_factory=time.time)
    acknowledged: bool = False
    resolved: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentStatus:
    """Component Status"""
    name: str
    status: SystemStatus = SystemStatus.STARTING
    last_update: float = field(default_factory=time.time)
    health_score: float = 1.0
    error_count: int = 0
    uptime_seconds: float = 0.0
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemMetrics:
    """System Comprehensive Metrics"""
    timestamp: float = field(default_factory=time.time)

    # Overall Status
    overall_status: SystemStatus = SystemStatus.STARTING
    overall_health_score: float = 1.0
    uptime_seconds: float = 0.0

    # Component Status
    component_count: int = 0
    healthy_components: int = 0
    degraded_components: int = 0
    critical_components: int = 0

    # Performance Metrics
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    average_response_time_ms: float = 0.0
    requests_per_second: float = 0.0

    # Data Metrics
    data_quality_score: float = 1.0
    data_throughput: int = 0
    cache_hit_rate: float = 0.0

    # Connection Metrics
    active_connections: int = 0
    connection_pool_utilization: float = 0.0

    # Fault Metrics
    active_incidents: int = 0
    resolved_incidents_today: int = 0

    # Resource Metrics
    memory_usage_mb: float = 0.0
    cpu_usage_percent: float = 0.0


class SystemMonitor:
    """System Comprehensive Monitoring Manager"""

    def __init__(self):
        # Core components
        self.enhanced_client: Optional[EnhancedTradingViewClient] = None
        self.data_quality_engine: Optional[DataQualityEngine] = None
        self.connection_monitor: Optional[ConnectionHealthMonitor] = None
        self.performance_optimizer: Optional[PerformanceOptimizer] = None
        self.fault_recovery_manager: Optional[FaultRecoveryManager] = None
        self.integration_manager: Optional[TradingCoreIntegrationManager] = None
        self.realtime_adapter: Optional[AdvancedRealtimeAdapter] = None

        # Monitor state
        self.system_start_time = time.time()
        self.is_running = False
        self.monitoring_tasks: List[asyncio.Task] = []

        # Component tracking
        self.component_status: Dict[str, ComponentStatus] = {}

        # Alert management
        self.active_alerts: Dict[str, SystemAlert] = {}
        self.alert_history: deque = deque(maxlen=1000)
        self.alert_callbacks: List[Callable[[SystemAlert], None]] = []

        # Metrics history
        self.metrics_history: deque = deque(maxlen=1440)  # 24 hours, one per minute

        # Monitor configuration
        self.monitoring_config = {
            'health_check_interval': 30,      # 30s
            'metrics_collection_interval': 60, # 60s
            'alert_check_interval': 10,        # 10s
            'component_timeout': 300,          # 5m

            # Thresholds
            'health_score_warning': 0.8,
            'health_score_critical': 0.6,
            'response_time_warning': 1000,     # 1s
            'response_time_critical': 3000,    # 3s
            'error_rate_warning': 0.05,        # 5%
            'error_rate_critical': 0.15,       # 15%
            'data_quality_warning': 0.8,
            'data_quality_critical': 0.6,
        }

        # Stats
        self.monitoring_stats = {
            'total_health_checks': 0,
            'total_alerts_generated': 0,
            'total_metrics_collected': 0,
            'monitoring_uptime': 0.0
        }

    async def initialize(self, components: Dict[str, Any]) -> bool:
        """
        Initialize system monitoring.

        Args:
            components: Dictionary of components to monitor

        Returns:
            bool: Success status
        """
        try:
            logger.info("🚀 Starting system monitoring initialization...")

            # Init components
            self.enhanced_client = components.get('enhanced_client')
            self.data_quality_engine = components.get('data_quality_engine')
            self.connection_monitor = components.get('connection_monitor')
            self.performance_optimizer = components.get('performance_optimizer')
            self.fault_recovery_manager = components.get('fault_recovery_manager')
            self.integration_manager = components.get('integration_manager')
            self.realtime_adapter = components.get('realtime_adapter')

            # Register status trackers
            for component_name in components.keys():
                self.component_status[component_name] = ComponentStatus(name=component_name)

            # Start monitoring tasks
            self.is_running = True

            # Health loop
            health_task = asyncio.create_task(self._health_check_loop())
            self.monitoring_tasks.append(health_task)

            # Metrics loop
            metrics_task = asyncio.create_task(self._metrics_collection_loop())
            self.monitoring_tasks.append(metrics_task)

            # Alert loop
            alert_task = asyncio.create_task(self._alert_check_loop())
            self.monitoring_tasks.append(alert_task)

            # Status update loop
            status_task = asyncio.create_task(self._component_status_loop())
            self.monitoring_tasks.append(status_task)

            logger.info("✅ System monitoring initialized successfully")
            return True

        except Exception as e:
            logger.error(f"❌ System monitoring initialization failed: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown system monitoring"""
        try:
            logger.info("Shutting down system monitoring...")

            self.is_running = False

            for task in self.monitoring_tasks:
                task.cancel()

            if self.monitoring_tasks:
                await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)

            self.monitoring_tasks.clear()

            logger.info("System monitoring shutdown complete")

        except Exception as e:
            logger.error(f"Failed to shutdown system monitoring: {e}")

    async def _health_check_loop(self) -> None:
        """Health check main loop"""
        while self.is_running:
            try:
                await self._perform_health_checks()
                self.monitoring_stats['total_health_checks'] += 1

                await asyncio.sleep(self.monitoring_config['health_check_interval'])

            except Exception as e:
                logger.error(f"Health check loop error: {e}")
                await asyncio.sleep(5)

    async def _perform_health_checks(self) -> None:
        """Execute health checks across all components"""
        try:
            current_time = time.time()

            if self.enhanced_client:
                await self._check_enhanced_client_health()

            if self.data_quality_engine:
                await self._check_data_quality_health()

            if self.connection_monitor:
                await self._check_connection_monitor_health()

            if self.performance_optimizer:
                await self._check_performance_optimizer_health()

            if self.fault_recovery_manager:
                await self._check_fault_recovery_health()

            if self.integration_manager:
                await self._check_integration_manager_health()

            if self.realtime_adapter:
                await self._check_realtime_adapter_health()

            # Update component uptimes
            for component in self.component_status.values():
                component.uptime_seconds = current_time - self.system_start_time
                component.last_update = current_time

        except Exception as e:
            logger.error(f"Execution of health checks failed: {e}")

    async def _check_enhanced_client_health(self) -> None:
        """Assess Enhanced Client health"""
        try:
            component_name = 'enhanced_client'
            status = self.component_status[component_name]

            connection_stats = self.enhanced_client.get_connection_stats()

            health_score = 1.0
            if connection_stats['state'] != 'connected':
                health_score *= 0.3

            quality_score = connection_stats.get('quality_score', 1.0)
            health_score *= quality_score

            status.health_score = health_score
            status.metrics = connection_stats

            if health_score >= 0.8:
                status.status = SystemStatus.HEALTHY
            elif health_score >= 0.6:
                status.status = SystemStatus.DEGRADED
            else:
                status.status = SystemStatus.CRITICAL

        except Exception as e:
            logger.error(f"Failed to check enhanced client health: {e}")
            if 'enhanced_client' in self.component_status:
                self.component_status['enhanced_client'].status = SystemStatus.CRITICAL

    async def _check_data_quality_health(self) -> None:
        """Assess Data Quality Engine health"""
        try:
            component_name = 'data_quality_engine'
            if component_name not in self.component_status:
                return

            status = self.component_status[component_name]
            quality_summary = self.data_quality_engine.get_quality_summary()

            health_score = quality_summary.get('average_quality_score', 1.0)

            status.health_score = health_score
            status.metrics = quality_summary

            if health_score >= 0.9:
                status.status = SystemStatus.HEALTHY
            elif health_score >= 0.7:
                status.status = SystemStatus.DEGRADED
            else:
                status.status = SystemStatus.CRITICAL

        except Exception as e:
            logger.error(f"Failed to check data quality engine health: {e}")

    async def _check_connection_monitor_health(self) -> None:
        """Assess Connection Monitor health"""
        try:
            component_name = 'connection_monitor'
            if component_name not in self.component_status:
                return

            status = self.component_status[component_name]
            health_report = self.connection_monitor.get_health_report()

            current_health = health_report.get('current_health', {})
            health_score = current_health.get('score', 1.0)

            status.health_score = health_score
            status.metrics = health_report

            if health_score >= 0.9:
                status.status = SystemStatus.HEALTHY
            elif health_score >= 0.7:
                status.status = SystemStatus.DEGRADED
            else:
                status.status = SystemStatus.CRITICAL

        except Exception as e:
            logger.error(f"Failed to check connection monitor health: {e}")

    async def _check_performance_optimizer_health(self) -> None:
        """Assess Performance Optimizer health"""
        try:
            component_name = 'performance_optimizer'
            if component_name not in self.component_status:
                return

            status = self.component_status[component_name]
            perf_stats = self.performance_optimizer.get_comprehensive_stats()

            cache_stats = perf_stats.get('cache_stats', {})
            hit_rate = cache_stats.get('hit_rate', 1.0)

            pool_stats = perf_stats.get('pool_stats', {})
            avg_wait_time = pool_stats.get('average_wait_time_ms', 0)

            health_score = hit_rate * (1.0 - min(0.5, avg_wait_time / 1000))

            status.health_score = health_score
            status.metrics = perf_stats

            if health_score >= 0.8:
                status.status = SystemStatus.HEALTHY
            elif health_score >= 0.6:
                status.status = SystemStatus.DEGRADED
            else:
                status.status = SystemStatus.CRITICAL

        except Exception as e:
            logger.error(f"Failed to check performance optimizer health: {e}")

    async def _check_fault_recovery_health(self) -> None:
        """Assess Fault Recovery Manager health"""
        try:
            component_name = 'fault_recovery_manager'
            if component_name not in self.component_status:
                return

            status = self.component_status[component_name]
            health_report = self.fault_recovery_manager.get_system_health_report()

            health_ratio = health_report.get('overall_health_ratio', 1.0)
            active_incidents = health_report.get('active_incidents', 0)

            health_score = health_ratio * (1.0 - min(0.3, active_incidents * 0.1))

            status.health_score = health_score
            status.metrics = health_report

            if health_score >= 0.9:
                status.status = SystemStatus.HEALTHY
            elif health_score >= 0.7:
                status.status = SystemStatus.DEGRADED
            else:
                status.status = SystemStatus.CRITICAL

        except Exception as e:
            logger.error(f"Failed to check fault recovery manager health: {e}")

    async def _check_integration_manager_health(self) -> None:
        """Assess Integration Manager health"""
        try:
            component_name = 'integration_manager'
            if component_name not in self.component_status:
                return

            status = self.component_status[component_name]
            integration_status = self.integration_manager.get_integration_status()

            converter_stats = integration_status.get('converter_stats', {})
            success_rate = converter_stats.get('success_rate', 1.0)

            health_score = success_rate

            status.health_score = health_score
            status.metrics = integration_status

            if health_score >= 0.9:
                status.status = SystemStatus.HEALTHY
            elif health_score >= 0.7:
                status.status = SystemStatus.DEGRADED
            else:
                status.status = SystemStatus.CRITICAL

        except Exception as e:
            logger.error(f"Failed to check integration manager health: {e}")

    async def _check_realtime_adapter_health(self) -> None:
        """Assess Real-time Adapter health"""
        try:
            component_name = 'realtime_adapter'
            if component_name not in self.component_status:
                return

            status = self.component_status[component_name]
            adapter_stats = self.realtime_adapter.get_comprehensive_stats()

            subscription_status = adapter_stats.get('subscription_status', {})
            active_subs = subscription_status.get('active_subscriptions', 0)
            total_subs = subscription_status.get('total_subscriptions', 1)

            health_score = active_subs / max(1, total_subs)

            status.health_score = health_score
            status.metrics = adapter_stats

            if health_score >= 0.9:
                status.status = SystemStatus.HEALTHY
            elif health_score >= 0.7:
                status.status = SystemStatus.DEGRADED
            else:
                status.status = SystemStatus.CRITICAL

        except Exception as e:
            logger.error(f"Failed to check real-time adapter health: {e}")

    async def _metrics_collection_loop(self) -> None:
        """Metrics aggregation loop"""
        while self.is_running:
            try:
                await self._collect_system_metrics()
                self.monitoring_stats['total_metrics_collected'] += 1

                await asyncio.sleep(self.monitoring_config['metrics_collection_interval'])

            except Exception as e:
                logger.error(f"Metrics collection loop error: {e}")
                await asyncio.sleep(10)

    async def _collect_system_metrics(self) -> None:
        """Aggregate system-wide metrics"""
        try:
            current_time = time.time()
            metrics = SystemMetrics(timestamp=current_time)

            metrics.uptime_seconds = current_time - self.system_start_time
            metrics.component_count = len(self.component_status)
            for component in self.component_status.values():
                if component.status == SystemStatus.HEALTHY:
                    metrics.healthy_components += 1
                elif component.status == SystemStatus.DEGRADED:
                    metrics.degraded_components += 1
                elif component.status == SystemStatus.CRITICAL:
                    metrics.critical_components += 1

            if metrics.component_count > 0:
                metrics.overall_health_score = sum(
                    comp.health_score for comp in self.component_status.values()
                ) / metrics.component_count

            if metrics.overall_health_score >= 0.9:
                metrics.overall_status = SystemStatus.HEALTHY
            elif metrics.overall_health_score >= 0.7:
                metrics.overall_status = SystemStatus.DEGRADED
            elif metrics.overall_health_score >= 0.5:
                metrics.overall_status = SystemStatus.WARNING
            else:
                metrics.overall_status = SystemStatus.CRITICAL

            await self._collect_performance_metrics(metrics)
            await self._collect_data_metrics(metrics)
            await self._collect_connection_metrics(metrics)
            await self._collect_fault_metrics(metrics)

            self.metrics_history.append(metrics)
            self.monitoring_stats['monitoring_uptime'] = metrics.uptime_seconds

        except Exception as e:
            logger.error(f"Failed to aggregate system metrics: {e}")

    async def _collect_performance_metrics(self, metrics: SystemMetrics) -> None:
        """Collect performance related metrics"""
        try:
            if self.performance_optimizer:
                perf_stats = self.performance_optimizer.get_comprehensive_stats()

                cache_stats = perf_stats.get('cache_stats', {})
                metrics.cache_hit_rate = cache_stats.get('hit_rate', 0.0)

                pool_stats = perf_stats.get('pool_stats', {})
                metrics.active_connections = pool_stats.get('current_active', 0)
                metrics.connection_pool_utilization = pool_stats.get('current_active', 0) / max(1, pool_stats.get('max_connections', 1))

                system_metrics = perf_stats.get('system_metrics', {})
                metrics.memory_usage_mb = system_metrics.get('memory_available_gb', 0) * 1024
                metrics.cpu_usage_percent = system_metrics.get('cpu_usage', 0)

        except Exception as e:
            logger.error(f"Failed to collect performance metrics: {e}")

    async def _collect_data_metrics(self, metrics: SystemMetrics) -> None:
        """Collect data related metrics"""
        try:
            if self.data_quality_engine:
                quality_summary = self.data_quality_engine.get_quality_summary()
                metrics.data_quality_score = quality_summary.get('average_quality_score', 1.0)

            if self.realtime_adapter:
                adapter_stats = self.realtime_adapter.get_comprehensive_stats()
                realtime_stats = adapter_stats.get('event_stats', {})
                metrics.data_throughput = realtime_stats.get('events_dispatched', 0)

        except Exception as e:
            logger.error(f"Failed to collect data metrics: {e}")

    async def _collect_connection_metrics(self, metrics: SystemMetrics) -> None:
        """Collect connection related metrics"""
        try:
            if self.enhanced_client:
                connection_stats = self.enhanced_client.get_connection_stats()
                stats = connection_stats.get('stats', {})
                metrics.total_requests = stats.get('successful_connections', 0) + stats.get('failed_connections', 0)
                metrics.successful_requests = stats.get('successful_connections', 0)
                metrics.failed_requests = stats.get('failed_connections', 0)
                metrics.average_response_time_ms = connection_stats.get('average_latency', 0.0)

        except Exception as e:
            logger.error(f"Failed to collect connection metrics: {e}")

    async def _collect_fault_metrics(self, metrics: SystemMetrics) -> None:
        """Collect fault related metrics"""
        try:
            if self.fault_recovery_manager:
                health_report = self.fault_recovery_manager.get_system_health_report()
                metrics.active_incidents = health_report.get('active_incidents', 0)
                metrics.resolved_incidents_today = health_report.get('total_incidents_today', 0)

        except Exception as e:
            logger.error(f"Failed to collect fault metrics: {e}")

    async def _alert_check_loop(self) -> None:
        """Alert evaluation loop"""
        while self.is_running:
            try:
                await self._check_for_alerts()
                await asyncio.sleep(self.monitoring_config['alert_check_interval'])

            except Exception as e:
                logger.error(f"Alert evaluation loop error: {e}")
                await asyncio.sleep(5)

    async def _check_for_alerts(self) -> None:
        """Evaluate current metrics against alert thresholds"""
        try:
            current_time = time.time()

            for component_name, component in self.component_status.items():
                if component.health_score < self.monitoring_config['health_score_critical']:
                    await self._create_alert(
                        AlertLevel.CRITICAL,
                        component_name,
                        "Low Component Health Score",
                        f"Component {component_name} health: {component.health_score:.2f}",
                        {'health_score': component.health_score}
                    )
                elif component.health_score < self.monitoring_config['health_score_warning']:
                    await self._create_alert(
                        AlertLevel.WARNING,
                        component_name,
                        "Component Health Score Warning",
                        f"Component {component_name} health: {component.health_score:.2f}",
                        {'health_score': component.health_score}
                    )

            if self.metrics_history:
                latest_metrics = self.metrics_history[-1]

                if latest_metrics.average_response_time_ms > self.monitoring_config['response_time_critical']:
                    await self._create_alert(
                        AlertLevel.CRITICAL,
                        "system",
                        "High Response Time",
                        f"Average response time: {latest_metrics.average_response_time_ms:.1f}ms",
                        {'response_time_ms': latest_metrics.average_response_time_ms}
                    )
                elif latest_metrics.average_response_time_ms > self.monitoring_config['response_time_warning']:
                    await self._create_alert(
                        AlertLevel.WARNING,
                        "system",
                        "Response Time Warning",
                        f"Average response time: {latest_metrics.average_response_time_ms:.1f}ms",
                        {'response_time_ms': latest_metrics.average_response_time_ms}
                    )

                if latest_metrics.data_quality_score < self.monitoring_config['data_quality_critical']:
                    await self._create_alert(
                        AlertLevel.CRITICAL,
                        "data_quality",
                        "Severe Data Quality Drop",
                        f"Quality score: {latest_metrics.data_quality_score:.2f}",
                        {'data_quality_score': latest_metrics.data_quality_score}
                    )
                elif latest_metrics.data_quality_score < self.monitoring_config['data_quality_warning']:
                    await self._create_alert(
                        AlertLevel.WARNING,
                        "data_quality",
                        "Data Quality Warning",
                        f"Quality score: {latest_metrics.data_quality_score:.2f}",
                        {'data_quality_score': latest_metrics.data_quality_score}
                    )

                if latest_metrics.total_requests > 0:
                    error_rate = latest_metrics.failed_requests / latest_metrics.total_requests

                    if error_rate > self.monitoring_config['error_rate_critical']:
                        await self._create_alert(
                            AlertLevel.CRITICAL,
                            "system",
                            "High Error Rate",
                            f"Error rate: {error_rate:.1%}",
                            {'error_rate': error_rate}
                        )
                    elif error_rate > self.monitoring_config['error_rate_warning']:
                        await self._create_alert(
                            AlertLevel.WARNING,
                            "system",
                            "Error Rate Warning",
                            f"Error rate: {error_rate:.1%}",
                            {'error_rate': error_rate}
                        )

        except Exception as e:
            logger.error(f"Alert evaluation failed: {e}")

    async def _create_alert(self, level: AlertLevel, component: str, title: str,
                          message: str, metadata: Dict[str, Any]) -> None:
        """Generate a new system alert"""
        try:
            alert_id = f"{component}_{level.name}_{int(time.time())}"

            # Deduplication
            existing_alerts = [
                alert for alert in self.active_alerts.values()
                if (alert.component == component and
                    alert.level == level and
                    alert.title == title and
                    not alert.resolved)
            ]

            if existing_alerts:
                existing_alerts[0].timestamp = time.time()
                return

            alert = SystemAlert(
                alert_id=alert_id,
                level=level,
                component=component,
                title=title,
                message=message,
                metadata=metadata
            )

            self.active_alerts[alert_id] = alert
            self.alert_history.append(alert)
            self.monitoring_stats['total_alerts_generated'] += 1

            log_level = {
                AlertLevel.INFO: logging.INFO,
                AlertLevel.WARNING: logging.WARNING,
                AlertLevel.ERROR: logging.ERROR,
                AlertLevel.CRITICAL: logging.CRITICAL
            }.get(level, logging.INFO)

            logger.log(log_level, f"🚨 {level.name} Alert: {component} - {title}: {message}")

            for callback in self.alert_callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(alert)
                    else:
                        callback(alert)
                except Exception as e:
                    logger.error(f"Alert callback failed: {e}")

        except Exception as e:
            logger.error(f"Failed to generate alert: {e}")

    async def _component_status_loop(self) -> None:
        """Component timeout monitoring loop"""
        while self.is_running:
            try:
                await self._update_component_status()
                await asyncio.sleep(30)

            except Exception as e:
                logger.error(f"Status update loop error: {e}")
                await asyncio.sleep(5)

    async def _update_component_status(self) -> None:
        """Mark components as offline if they fail to report"""
        try:
            current_time = time.time()
            timeout_threshold = self.monitoring_config['component_timeout']

            for component in self.component_status.values():
                if current_time - component.last_update > timeout_threshold:
                    component.status = SystemStatus.OFFLINE
                    component.health_score = 0.0
                    component.error_count += 1

        except Exception as e:
            logger.error(f"Status update failed: {e}")

    def add_alert_callback(self, callback: Callable[[SystemAlert], None]) -> None:
        """Register a subscriber for alerts"""
        self.alert_callbacks.append(callback)
        logger.info(f"Registered alert callback: {callback.__name__}")

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Acknowledge an active alert"""
        try:
            if alert_id in self.active_alerts:
                self.active_alerts[alert_id].acknowledged = True
                logger.info(f"Alert acknowledged: {alert_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to acknowledge alert: {e}")
            return False

    def resolve_alert(self, alert_id: str) -> bool:
        """Manually resolve an active alert"""
        try:
            if alert_id in self.active_alerts:
                alert = self.active_alerts[alert_id]
                alert.resolved = True
                del self.active_alerts[alert_id]
                logger.info(f"Alert resolved: {alert_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
            return False

    def get_system_dashboard(self) -> Dict[str, Any]:
        """Retrieve aggregated data for the monitoring dashboard"""
        try:
            current_time = time.time()
            latest_metrics = self.metrics_history[-1] if self.metrics_history else SystemMetrics()

            alerts_by_level = defaultdict(int)
            for alert in self.active_alerts.values():
                alerts_by_level[alert.level.name] += 1

            components_by_status = defaultdict(int)
            for component in self.component_status.values():
                components_by_status[component.status.name] += 1

            trends = self._calculate_trends()

            return {
                # Overview
                'system_overview': {
                    'status': latest_metrics.overall_status.name,
                    'health_score': latest_metrics.overall_health_score,
                    'uptime_seconds': latest_metrics.uptime_seconds,
                    'uptime_formatted': self._format_uptime(latest_metrics.uptime_seconds)
                },

                # Components
                'component_summary': {
                    'total_components': latest_metrics.component_count,
                    'healthy': latest_metrics.healthy_components,
                    'degraded': latest_metrics.degraded_components,
                    'critical': latest_metrics.critical_components,
                    'by_status': dict(components_by_status)
                },

                # Performance
                'performance_metrics': {
                    'total_requests': latest_metrics.total_requests,
                    'success_rate': (latest_metrics.successful_requests / max(1, latest_metrics.total_requests)),
                    'average_response_time_ms': latest_metrics.average_response_time_ms,
                    'requests_per_second': latest_metrics.requests_per_second,
                    'cache_hit_rate': latest_metrics.cache_hit_rate
                },

                # Data
                'data_metrics': {
                    'data_quality_score': latest_metrics.data_quality_score,
                    'data_throughput': latest_metrics.data_throughput,
                    'active_connections': latest_metrics.active_connections,
                    'connection_pool_utilization': latest_metrics.connection_pool_utilization
                },

                # Faults
                'fault_metrics': {
                    'active_incidents': latest_metrics.active_incidents,
                    'resolved_incidents_today': latest_metrics.resolved_incidents_today,
                    'active_alerts': len(self.active_alerts),
                    'alerts_by_level': dict(alerts_by_level)
                },

                # Resources
                'resource_metrics': {
                    'memory_usage_mb': latest_metrics.memory_usage_mb,
                    'cpu_usage_percent': latest_metrics.cpu_usage_percent
                },

                # Analysis
                'trends': trends,

                # Recent history
                'recent_alerts': [
                    {
                        'alert_id': alert.alert_id,
                        'level': alert.level.name,
                        'component': alert.component,
                        'title': alert.title,
                        'message': alert.message,
                        'timestamp': alert.timestamp,
                        'acknowledged': alert.acknowledged
                    }
                    for alert in sorted(
                        self.active_alerts.values(),
                        key=lambda x: x.timestamp,
                        reverse=True
                    )[:10]
                ],

                'monitoring_stats': self.monitoring_stats,

                'component_details': {
                    name: {
                        'status': component.status.name,
                        'health_score': component.health_score,
                        'uptime_seconds': component.uptime_seconds,
                        'error_count': component.error_count,
                        'last_update': component.last_update
                    }
                    for name, component in self.component_status.items()
                }
            }

        except Exception as e:
            logger.error(f"Failed to generate dashboard data: {e}")
            return {}

    def _calculate_trends(self) -> Dict[str, float]:
        """Calculate percentage changes vs 1 hour ago"""
        try:
            if len(self.metrics_history) < 2:
                return {}

            current = self.metrics_history[-1]
            one_hour_ago = current.timestamp - 3600
            historical = None

            for metrics in reversed(self.metrics_history):
                if metrics.timestamp <= one_hour_ago:
                    historical = metrics
                    break

            if not historical:
                return {}

            trends = {}

            if historical.overall_health_score > 0:
                trends['health_score_trend'] = (
                    (current.overall_health_score - historical.overall_health_score) /
                    historical.overall_health_score
                )

            if historical.average_response_time_ms > 0:
                trends['response_time_trend'] = (
                    (current.average_response_time_ms - historical.average_response_time_ms) /
                    historical.average_response_time_ms
                )

            if historical.data_quality_score > 0:
                trends['data_quality_trend'] = (
                    (current.data_quality_score - historical.data_quality_score) /
                    historical.data_quality_score
                )

            return trends

        except Exception as e:
            logger.error(f"Trend calculation failed: {e}")
            return {}

    def _format_uptime(self, uptime_seconds: float) -> str:
        """Human-readable uptime string"""
        try:
            uptime_timedelta = timedelta(seconds=int(uptime_seconds))
            days = uptime_timedelta.days
            hours, remainder = divmod(uptime_timedelta.seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            if days > 0:
                return f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes}m {seconds}s"

        except Exception:
            return "Unknown"


def create_system_monitor() -> SystemMonitor:
    """Factory for monitor manager"""
    return SystemMonitor()


async def test_system_monitor():
    """Manual system test"""
    monitor = create_system_monitor()

    try:
        mock_components = {
            'enhanced_client': None,
            'data_quality_engine': None,
            'connection_monitor': None
        }

        await monitor.initialize(mock_components)
        await asyncio.sleep(10)
        dashboard = monitor.get_system_dashboard()
        print(f"System Dashboard: {json.dumps(dashboard, indent=2, default=str)}")

    finally:
        await monitor.shutdown()


if __name__ == "__main__":
    asyncio.run(test_system_monitor())
