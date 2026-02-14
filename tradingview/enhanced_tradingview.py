#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Enhanced Data Source Unified Entry
Integrates all enhanced functions to provide a complete professional-grade data source service.
"""

import asyncio
import time
import json
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
import logging

# Import all enhanced modules
from .enhanced_client import EnhancedTradingViewClient, ConnectionState
from .data_quality_monitor import DataQualityEngine, QualityLevel
from .connection_health import ConnectionHealthMonitor, HealthStatus
from .performance_optimizer import PerformanceOptimizer
from .fault_recovery import FaultRecoveryManager, BackupDataSource
from .trading_integration import TradingCoreIntegrationManager, TradingViewDataConverter, MarketDataPoint
from .realtime_adapter import AdvancedRealtimeAdapter, SubscriptionType
from .system_monitor import SystemMonitor, SystemStatus
from .integration_test import IntegrationTestSuite

from tradingview.utils import get_logger

logger = get_logger(__name__)


class ServiceStatus(Enum):
    """Service status"""
    INITIALIZING = auto()
    RUNNING = auto()
    DEGRADED = auto()
    STOPPED = auto()
    ERROR = auto()


@dataclass
class EnhancedTradingViewConfig:
    """Enhanced TradingView Configuration"""
    # Connection config
    auto_reconnect: bool = True
    health_check_interval: int = 30
    connection_timeout: float = 30.0

    # Performance config
    enable_caching: bool = True
    cache_size: int = 10000
    enable_connection_pool: bool = True
    min_connections: int = 5
    max_connections: int = 50

    # Data quality config
    quality_threshold: float = 0.8
    enable_quality_monitoring: bool = True

    # Fault recovery config
    enable_fault_recovery: bool = True
    max_retry_attempts: int = 3
    circuit_breaker_enabled: bool = True

    # Monitoring config
    enable_system_monitoring: bool = True
    metrics_collection_interval: int = 60

    # Test config
    enable_integration_test: bool = False
    test_symbols: List[str] = None

    def __post_init__(self):
        if self.test_symbols is None:
            self.test_symbols = ['BTC/USDT', 'ETH/USDT', 'XAU/USD']


class EnhancedTradingViewService:
    """Enhanced TradingView Data Source Service"""

    def __init__(self, config: Optional[EnhancedTradingViewConfig] = None):
        self.config = config or EnhancedTradingViewConfig()
        self.status = ServiceStatus.INITIALIZING
        self.start_time = time.time()

        # Core components
        self.enhanced_client: Optional[EnhancedTradingViewClient] = None
        self.data_quality_engine: Optional[DataQualityEngine] = None
        self.connection_monitor: Optional[ConnectionHealthMonitor] = None
        self.performance_optimizer: Optional[PerformanceOptimizer] = None
        self.fault_recovery_manager: Optional[FaultRecoveryManager] = None
        self.integration_manager: Optional[TradingCoreIntegrationManager] = None
        self.realtime_adapter: Optional[AdvancedRealtimeAdapter] = None
        self.system_monitor: Optional[SystemMonitor] = None

        # Service state
        self.initialization_errors: List[str] = []
        self.service_metrics = {
            'total_requests': 0,
            'successful_requests': 0,
            'failed_requests': 0,
            'uptime_seconds': 0.0,
            'last_health_check': 0.0
        }

        # Callbacks
        self.data_callbacks: List[Callable[[MarketDataPoint], None]] = []
        self.status_callbacks: List[Callable[[ServiceStatus], None]] = []
        self.error_callbacks: List[Callable[[Exception], None]] = []

    async def initialize(self) -> bool:
        """
        Initialize enhanced TradingView service.

        Returns:
            bool: Initialization success status
        """
        try:
            logger.info("🚀 Starting enhanced TradingView data source service initialization...")
            self.status = ServiceStatus.INITIALIZING

            # 1. Initialize enhanced client
            await self._initialize_enhanced_client()

            # 2. Initialize data quality engine
            if self.config.enable_quality_monitoring:
                await self._initialize_data_quality_engine()

            # 3. Initialize connection health monitor
            await self._initialize_connection_monitor()

            # 4. Initialize performance optimizer
            await self._initialize_performance_optimizer()

            # 5. Initialize fault recovery manager
            if self.config.enable_fault_recovery:
                await self._initialize_fault_recovery_manager()

            # 6. Initialize integration manager
            await self._initialize_integration_manager()

            # 7. Initialize real-time adapter
            await self._initialize_realtime_adapter()

            # 8. Initialize system monitor
            if self.config.enable_system_monitoring:
                await self._initialize_system_monitor()

            # 9. Run integration tests (if enabled)
            if self.config.enable_integration_test:
                await self._run_integration_test()

            # 10. Validate component statuses
            if not await self._validate_components():
                raise RuntimeError("Component validation failed")

            self.status = ServiceStatus.RUNNING
            self._notify_status_change(ServiceStatus.RUNNING)

            logger.info("✅ Enhanced TradingView data source service initialized successfully")
            logger.info(f"🎯 Enabled features: Quality={self.config.enable_quality_monitoring}, "
                       f"Recovery={self.config.enable_fault_recovery}, "
                       f"Monitoring={self.config.enable_system_monitoring}")

            return True

        except Exception as e:
            error_msg = f"Enhanced TradingView service failed to initialize: {e}"
            logger.error(f"❌ {error_msg}")
            self.initialization_errors.append(error_msg)
            self.status = ServiceStatus.ERROR
            self._notify_error(e)
            return False

    async def _initialize_enhanced_client(self) -> None:
        """Initialize enhanced client"""
        try:
            logger.info("Initializing enhanced TradingView client...")
            self.enhanced_client = EnhancedTradingViewClient(
                auto_reconnect=self.config.auto_reconnect,
                health_check_interval=self.config.health_check_interval
            )

            self.enhanced_client.on_connection_state_change(self._on_connection_state_change)
            logger.info("✅ Enhanced TradingView client initialized")

        except Exception as e:
            error_msg = f"Enhanced client initialization failed: {e}"
            logger.error(error_msg)
            self.initialization_errors.append(error_msg)
            raise

    async def _initialize_data_quality_engine(self) -> None:
        """Initialize data quality engine"""
        try:
            logger.info("Initializing data quality engine...")
            self.data_quality_engine = DataQualityEngine()
            logger.info("✅ Data quality engine initialized")

        except Exception as e:
            error_msg = f"Data quality engine initialization failed: {e}"
            logger.error(error_msg)
            self.initialization_errors.append(error_msg)
            raise

    async def _initialize_connection_monitor(self) -> None:
        """Initialize connection health monitor"""
        try:
            logger.info("Initializing connection health monitor...")
            self.connection_monitor = ConnectionHealthMonitor(
                check_interval=self.config.health_check_interval
            )
            await self.connection_monitor.start_monitoring()
            logger.info("✅ Connection health monitor initialized")

        except Exception as e:
            error_msg = f"Connection health monitor initialization failed: {e}"
            logger.error(error_msg)
            self.initialization_errors.append(error_msg)
            raise

    async def _initialize_performance_optimizer(self) -> None:
        """Initialize performance optimizer"""
        try:
            logger.info("Initializing performance optimizer...")
            self.performance_optimizer = PerformanceOptimizer()

            # Create connection factory if needed
            connection_factory = None
            if self.config.enable_connection_pool:
                async def create_mock_connection():
                    return f"mock_connection_{time.time()}"
                connection_factory = create_mock_connection

            await self.performance_optimizer.initialize(connection_factory)
            logger.info("✅ Performance optimizer initialized")

        except Exception as e:
            error_msg = f"Performance optimizer initialization failed: {e}"
            logger.error(error_msg)
            self.initialization_errors.append(error_msg)
            raise

    async def _initialize_fault_recovery_manager(self) -> None:
        """Initialize fault recovery manager"""
        try:
            logger.info("Initializing fault recovery manager...")
            self.fault_recovery_manager = FaultRecoveryManager()
            await self.fault_recovery_manager.start()

            if self.enhanced_client:
                async def client_health_check():
                    stats = self.enhanced_client.get_connection_stats()
                    return {
                        'response_time_ms': stats.get('average_latency', 0),
                        'success_rate': 0.95,
                        'data_quality_score': 0.9
                    }
                self.fault_recovery_manager.register_component('enhanced_client', client_health_check)

            logger.info("✅ Fault recovery manager initialized")

        except Exception as e:
            error_msg = f"Fault recovery manager initialization failed: {e}"
            logger.error(error_msg)
            self.initialization_errors.append(error_msg)
            raise

    async def _initialize_integration_manager(self) -> None:
        """Initialize integration manager"""
        try:
            logger.info("Initializing trading_core integration manager...")
            self.integration_manager = TradingCoreIntegrationManager()
            await self.integration_manager.initialize_integration()
            logger.info("✅ Integration manager initialized")

        except Exception as e:
            error_msg = f"Integration manager initialization failed: {e}"
            logger.error(error_msg)
            self.initialization_errors.append(error_msg)
            raise

    async def _initialize_realtime_adapter(self) -> None:
        """Initialize real-time adapter"""
        try:
            logger.info("Initializing real-time data adapter...")
            self.realtime_adapter = AdvancedRealtimeAdapter()
            await self.realtime_adapter.initialize()
            logger.info("✅ Real-time data adapter initialized")

        except Exception as e:
            error_msg = f"Real-time adapter initialization failed: {e}"
            logger.error(error_msg)
            self.initialization_errors.append(error_msg)
            raise

    async def _initialize_system_monitor(self) -> None:
        """Initialize system monitor"""
        try:
            logger.info("Initializing system monitor...")
            self.system_monitor = SystemMonitor()

            components = {}
            if self.enhanced_client: components['enhanced_client'] = self.enhanced_client
            if self.data_quality_engine: components['data_quality_engine'] = self.data_quality_engine
            if self.connection_monitor: components['connection_monitor'] = self.connection_monitor
            if self.performance_optimizer: components['performance_optimizer'] = self.performance_optimizer
            if self.fault_recovery_manager: components['fault_recovery_manager'] = self.fault_recovery_manager
            if self.integration_manager: components['integration_manager'] = self.integration_manager
            if self.realtime_adapter: components['realtime_adapter'] = self.realtime_adapter

            await self.system_monitor.initialize(components)
            self.system_monitor.add_alert_callback(self._on_system_alert)

            logger.info("✅ System monitor initialized")

        except Exception as e:
            error_msg = f"System monitor initialization failed: {e}"
            logger.error(error_msg)
            self.initialization_errors.append(error_msg)
            raise

    async def _run_integration_test(self) -> None:
        """Run integration tests"""
        try:
            logger.info("Running integration tests...")
            test_suite = IntegrationTestSuite()
            test_report = await test_suite.run_all_tests()

            summary = test_report.get('summary', {})
            success_rate = summary.get('success_rate', 0)

            if success_rate >= 0.8:
                logger.info(f"✅ Integration tests passed, rate: {success_rate:.1%}")
            else:
                logger.warning(f"⚠️ Integration tests partially failed, rate: {success_rate:.1%}")

        except Exception as e:
            logger.error(f"Integration test failed: {e}")

    async def _validate_components(self) -> bool:
        """Validate component statuses"""
        try:
            validation_results = {}

            if self.enhanced_client:
                validation_results['enhanced_client'] = True
            else:
                validation_results['enhanced_client'] = False
                logger.error("Enhanced client not initialized")

            if self.integration_manager:
                status = self.integration_manager.get_integration_status()
                validation_results['integration_manager'] = status.get('status') != 'ERROR'
            else:
                validation_results['integration_manager'] = False
                logger.error("Integration manager not initialized")

            if self.config.enable_quality_monitoring:
                validation_results['data_quality_engine'] = self.data_quality_engine is not None

            if self.config.enable_fault_recovery:
                validation_results['fault_recovery_manager'] = self.fault_recovery_manager is not None

            if self.config.enable_system_monitoring:
                validation_results['system_monitor'] = self.system_monitor is not None

            total_checks = len(validation_results)
            passed_checks = sum(1 for result in validation_results.values() if result)
            validation_rate = passed_checks / total_checks if total_checks > 0 else 0

            logger.info(f"Component validation result: {passed_checks}/{total_checks} passed ({validation_rate:.1%})")
            return validation_rate >= 0.8

        except Exception as e:
            logger.error(f"Component validation failed: {e}")
            return False

    async def shutdown(self) -> None:
        """Shutdown service"""
        try:
            logger.info("Shutting down enhanced TradingView data source service...")
            self.status = ServiceStatus.STOPPED

            if self.system_monitor: await self.system_monitor.shutdown()
            if self.realtime_adapter: await self.realtime_adapter.shutdown()
            if self.fault_recovery_manager: await self.fault_recovery_manager.stop()
            if self.performance_optimizer: await self.performance_optimizer.shutdown()
            if self.connection_monitor: await self.connection_monitor.stop_monitoring()
            if self.enhanced_client: await self.enhanced_client.disconnect()

            self._notify_status_change(ServiceStatus.STOPPED)
            logger.info("✅ Enhanced TradingView service shut down")

        except Exception as e:
            logger.error(f"Shutdown failed: {e}")
            self._notify_error(e)

    # === Data interface ===

    async def get_market_data(self, symbol: str, timeframe: str = "15m", count: int = 100) -> List[MarketDataPoint]:
        """Fetch market data"""
        try:
            self.service_metrics['total_requests'] += 1
            if not self.enhanced_client or self.status != ServiceStatus.RUNNING:
                raise RuntimeError("Service not ready")

            tv_symbol = self._convert_symbol_format(symbol)
            klines = await self.enhanced_client.get_klines(tv_symbol, timeframe, count)

            if not klines:
                self.service_metrics['failed_requests'] += 1
                return []

            converter = TradingViewDataConverter()
            market_data_list = []

            for kline in klines:
                market_data = converter.convert_kline_to_market_data(kline, symbol, timeframe)
                if market_data:
                    if self.data_quality_engine:
                        quality_metrics = await self.data_quality_engine.evaluate_data_quality(symbol, [kline])
                        market_data.quality_score = quality_metrics.overall_quality_score
                    market_data_list.append(market_data)

            self.service_metrics['successful_requests'] += 1
            for market_data in market_data_list:
                for callback in self.data_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback): await callback(market_data)
                        else: callback(market_data)
                    except Exception as e:
                        logger.error(f"Data callback failed: {e}")

            return market_data_list

        except Exception as e:
            self.service_metrics['failed_requests'] += 1
            logger.error(f"Failed to get market data for {symbol}: {e}")
            self._notify_error(e)
            return []

    async def subscribe_realtime_data(self, symbol: str, timeframe: str = "15m",
                                    callback: Callable[[MarketDataPoint], None] = None) -> bool:
        """Subscribe to real-time data"""
        try:
            if not self.realtime_adapter or self.status != ServiceStatus.RUNNING:
                raise RuntimeError("Real-time adapter not ready")

            subscription_type = self._convert_timeframe_to_subscription_type(timeframe)

            async def internal_callback(symbol: str, data: Dict[str, Any]):
                try:
                    converter = TradingViewDataConverter()
                    market_data = converter.convert_kline_to_market_data(data, symbol, timeframe)
                    if market_data:
                        if self.data_quality_engine:
                            quality_metrics = await self.data_quality_engine.evaluate_data_quality(symbol, [data])
                            market_data.quality_score = quality_metrics.overall_quality_score
                        market_data.is_realtime = True
                        if callback:
                            if asyncio.iscoroutinefunction(callback): await callback(market_data)
                            else: callback(market_data)
                        for registered_callback in self.data_callbacks:
                            try:
                                if asyncio.iscoroutinefunction(registered_callback): await registered_callback(market_data)
                                else: registered_callback(market_data)
                            except Exception as e:
                                logger.error(f"Registered data callback failed: {e}")
                except Exception as e:
                    logger.error(f"Real-time processing failed: {e}")

            success = await self.realtime_adapter.subscribe_symbol_data(symbol, subscription_type, internal_callback)
            if success: logger.info(f"✅ Subscribed to real-time: {symbol} {timeframe}")
            else: logger.error(f"❌ Failed to subscribe to real-time: {symbol} {timeframe}")
            return success

        except Exception as e:
            logger.error(f"Real-time subscription failed for {symbol}: {e}")
            self._notify_error(e)
            return False

    async def unsubscribe_realtime_data(self, symbol: str, timeframe: str = "15m") -> bool:
        """Unsubscribe from real-time data"""
        try:
            if not self.realtime_adapter: return False
            subscription_type = self._convert_timeframe_to_subscription_type(timeframe)
            success = await self.realtime_adapter.unsubscribe_symbol_data(symbol, subscription_type)
            if success: logger.info(f"✅ Unsubscription successful: {symbol} {timeframe}")
            return success
        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")
            return False

    # === Monitoring and status ===

    def get_service_status(self) -> Dict[str, Any]:
        """Retrieve full service status"""
        try:
            uptime = time.time() - self.start_time
            self.service_metrics['uptime_seconds'] = uptime
            status_info = {
                'status': self.status.name,
                'uptime_seconds': uptime,
                'uptime_formatted': self._format_uptime(uptime),
                'start_time': self.start_time,
                'metrics': self.service_metrics.copy(),
                'initialization_errors': self.initialization_errors.copy()
            }
            if self.system_monitor: status_info['system_dashboard'] = self.system_monitor.get_system_dashboard()
            if self.connection_monitor: status_info['connection_health'] = self.connection_monitor.get_health_report()
            if self.performance_optimizer: status_info['performance_stats'] = self.performance_optimizer.get_comprehensive_stats()
            return status_info
        except Exception as e:
            logger.error(f"Failed to get service status: {e}")
            return {'error': str(e)}

    def get_data_quality_report(self) -> Dict[str, Any]:
        """Retrieve data quality report"""
        if not self.data_quality_engine: return {'error': 'Quality engine disabled'}
        return {
            'quality_summary': self.data_quality_engine.get_quality_summary(),
            'anomaly_report': self.data_quality_engine.get_anomaly_report()
        }

    def get_fault_recovery_report(self) -> Dict[str, Any]:
        """Retrieve recovery report"""
        if not self.fault_recovery_manager: return {'error': 'Recovery manager disabled'}
        return self.fault_recovery_manager.get_system_health_report()

    # === Callback management ===

    def add_data_callback(self, callback: Callable[[MarketDataPoint], None]) -> None:
        self.data_callbacks.append(callback)
    def add_status_callback(self, callback: Callable[[ServiceStatus], None]) -> None:
        self.status_callbacks.append(callback)
    def add_error_callback(self, callback: Callable[[Exception], None]) -> None:
        self.error_callbacks.append(callback)

    # === Internal utilities ===

    def _convert_symbol_format(self, symbol: str) -> str:
        if "/" in symbol:
            base, quote = symbol.split("/")
            return f"BINANCE:{base}{quote}"
        return symbol

    def _convert_timeframe_to_subscription_type(self, timeframe: str) -> SubscriptionType:
        mapping = {
            "1m": SubscriptionType.KLINE_1M, "5m": SubscriptionType.KLINE_5M,
            "15m": SubscriptionType.KLINE_15M, "1h": SubscriptionType.KLINE_1H,
            "1d": SubscriptionType.KLINE_1D
        }
        return mapping.get(timeframe, SubscriptionType.KLINE_15M)

    def _format_uptime(self, uptime_seconds: float) -> str:
        try:
            hours, remainder = divmod(int(uptime_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0: return f"{hours}h {minutes}m"
            elif minutes > 0: return f"{minutes}h {seconds}s"
            else: return f"{seconds}s"
        except: return "Unknown"

    def _on_connection_state_change(self, state: ConnectionState) -> None:
        logger.info(f"Connection state changed: {state.value}")
        if state == ConnectionState.CONNECTED:
            if self.status == ServiceStatus.DEGRADED:
                self.status = ServiceStatus.RUNNING
                self._notify_status_change(ServiceStatus.RUNNING)
        elif state in [ConnectionState.DISCONNECTED, ConnectionState.FAILED]:
            if self.status == ServiceStatus.RUNNING:
                self.status = ServiceStatus.DEGRADED
                self._notify_status_change(ServiceStatus.DEGRADED)

    async def _on_system_alert(self, alert) -> None:
        logger.warning(f"System alert: {alert.level.name} - {alert.title}: {alert.message}")
        if alert.level.name == 'CRITICAL' and self.status == ServiceStatus.RUNNING:
            self.status = ServiceStatus.DEGRADED
            self._notify_status_change(ServiceStatus.DEGRADED)

    def _notify_status_change(self, new_status: ServiceStatus) -> None:
        for callback in self.status_callbacks:
            try: callback(new_status)
            except Exception as e: logger.error(f"Status callback failed: {e}")

    def _notify_error(self, error: Exception) -> None:
        for callback in self.error_callbacks:
            try: callback(error)
            except Exception as e: logger.error(f"Error callback failed: {e}")


# Factory methods

def create_enhanced_tradingview_service(config: Optional[EnhancedTradingViewConfig] = None) -> EnhancedTradingViewService:
    """Create service instance"""
    return EnhancedTradingViewService(config)


async def create_and_start_service(config: Optional[EnhancedTradingViewConfig] = None) -> EnhancedTradingViewService:
    """Create and start service instance"""
    service = create_enhanced_tradingview_service(config)
    success = await service.initialize()
    if not success: raise RuntimeError("Service initialization failed")
    return service


# Example usage
async def example_usage():
    try:
        config = EnhancedTradingViewConfig(
            enable_quality_monitoring=True, enable_fault_recovery=True,
            enable_system_monitoring=True, enable_integration_test=True,
            cache_size=5000
        )
        service = await create_and_start_service(config)

        def on_data_received(market_data: MarketDataPoint):
            print(f"Received data: {market_data.symbol} {market_data.close}")

        service.add_data_callback(on_data_received)

        print("Fetching historical data...")
        market_data = await service.get_market_data("BTC/USDT", "15m", 100)
        print(f"Retrieved {len(market_data)} history records")

        print("Subscribing to real-time data...")
        await service.subscribe_realtime_data("BTC/USDT", "15m")

        print("Running for 30 seconds...")
        await asyncio.sleep(30)

        status = service.get_service_status()
        print(f"Service status: {json.dumps(status, indent=2, default=str)}")

    except Exception as e:
        logger.error(f"Example run failed: {e}")
    finally:
        if 'service' in locals(): await service.shutdown()


if __name__ == "__main__":
    asyncio.run(example_usage())
