#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Data Source Module Full Integration Test Suite
Verifies integration and performance performance of all enhanced features
"""

import asyncio
import time
import json
import random
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum, auto
import logging
import traceback

# Import all enhanced modules
from .enhanced_client import EnhancedTradingViewClient, ConnectionState
from .data_quality_monitor import DataQualityEngine, QualityLevel
from .connection_health import ConnectionHealthMonitor, HealthStatus
from .performance_optimizer import PerformanceOptimizer, IntelligentCache, ConnectionPool
from .fault_recovery import FaultRecoveryManager, FaultType, RecoveryStrategy, BackupDataSource
from .trading_integration import TradingCoreIntegrationManager, TradingViewDataConverter
from .realtime_adapter import AdvancedRealtimeAdapter, SubscriptionType
from .system_monitor import SystemMonitor, SystemStatus, AlertLevel

from tradingview.utils import get_logger

logger = get_logger(__name__)

# Configure logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


class TestStatus(Enum):
    """Test Status"""
    PENDING = auto()
    RUNNING = auto()
    PASSED = auto()
    FAILED = auto()
    SKIPPED = auto()


class TestCategory(Enum):
    """Test Category"""
    UNIT = auto()           # Unit Test
    INTEGRATION = auto()    # Integration Test
    PERFORMANCE = auto()    # Performance Test
    STRESS = auto()         # Stress Test
    FAULT = auto()          # Fault Test


@dataclass
class TestResult:
    """Test Result"""
    test_name: str
    category: TestCategory
    status: TestStatus
    duration_ms: float
    error_message: str = ""
    details: Dict[str, Any] = None
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.details is None:
            self.details = {}


class IntegrationTestSuite:
    """Integration Test Suite"""

    def __init__(self):
        # Test Components
        self.enhanced_client: Optional[EnhancedTradingViewClient] = None
        self.data_quality_engine: Optional[DataQualityEngine] = None
        self.connection_monitor: Optional[ConnectionHealthMonitor] = None
        self.performance_optimizer: Optional[PerformanceOptimizer] = None
        self.fault_recovery_manager: Optional[FaultRecoveryManager] = None
        self.integration_manager: Optional[TradingCoreIntegrationManager] = None
        self.realtime_adapter: Optional[AdvancedRealtimeAdapter] = None
        self.system_monitor: Optional[SystemMonitor] = None

        # Test Results
        self.test_results: List[TestResult] = []
        self.test_stats = {
            'total_tests': 0,
            'passed_tests': 0,
            'failed_tests': 0,
            'skipped_tests': 0,
            'total_duration_ms': 0.0
        }

        # Test Configuration
        self.test_config = {
            'timeout_seconds': 30,
            'max_retry_attempts': 3,
            'test_symbols': ['BTC/USDT', 'ETH/USDT', 'XAU/USD'],
            'stress_test_duration': 60,
            'performance_threshold_ms': 1000,
            'quality_threshold': 0.8,
            'health_threshold': 0.8
        }

    async def run_all_tests(self) -> Dict[str, Any]:
        """Run all tests"""
        try:
            logger.info("🚀 Starting full integration test suite...")
            start_time = time.time()

            # 1. Setup test environment
            await self._setup_test_environment()

            # 2. Run unit tests
            await self._run_unit_tests()

            # 3. Run integration tests
            await self._run_integration_tests()

            # 4. Run performance tests
            await self._run_performance_tests()

            # 5. Run fault tests
            await self._run_fault_tests()

            # 6. Run stress tests
            await self._run_stress_tests()

            # 7. Cleanup test environment
            await self._cleanup_test_environment()

            # 8. Generate test report
            total_duration = (time.time() - start_time) * 1000
            self.test_stats['total_duration_ms'] = total_duration

            test_report = self._generate_test_report()

            logger.info(f"✅ Integration tests completed, total time: {total_duration:.1f}ms")
            return test_report

        except Exception as e:
            logger.error(f"❌ Integration tests failed: {e}")
            logger.error(traceback.format_exc())
            return {'error': str(e), 'traceback': traceback.format_exc()}

    async def _setup_test_environment(self) -> None:
        """Setup test environment"""
        try:
            logger.info("Setting up test environment...")

            # Initialize enhanced client
            self.enhanced_client = EnhancedTradingViewClient()

            # Initialize data quality engine
            self.data_quality_engine = DataQualityEngine()

            # Initialize connection health monitor
            self.connection_monitor = ConnectionHealthMonitor()
            await self.connection_monitor.start_monitoring()

            # Initialize performance optimizer
            self.performance_optimizer = PerformanceOptimizer()
            await self.performance_optimizer.initialize()

            # Initialize fault recovery manager
            self.fault_recovery_manager = FaultRecoveryManager()
            await self.fault_recovery_manager.start()

            # Initialize integration manager
            self.integration_manager = TradingCoreIntegrationManager()
            await self.integration_manager.initialize_integration()

            # Initialize realtime adapter
            self.realtime_adapter = AdvancedRealtimeAdapter()
            await self.realtime_adapter.initialize()

            # Initialize system monitor
            self.system_monitor = SystemMonitor()
            components = {
                'enhanced_client': self.enhanced_client,
                'data_quality_engine': self.data_quality_engine,
                'connection_monitor': self.connection_monitor,
                'performance_optimizer': self.performance_optimizer,
                'fault_recovery_manager': self.fault_recovery_manager,
                'integration_manager': self.integration_manager,
                'realtime_adapter': self.realtime_adapter
            }
            await self.system_monitor.initialize(components)

            logger.info("✅ Test environment setup complete")

        except Exception as e:
            logger.error(f"❌ Test environment setup failed: {e}")
            raise

    async def _cleanup_test_environment(self) -> None:
        """Cleanup test environment"""
        try:
            logger.info("Cleaning up test environment...")

            # Shutdown all components
            if self.system_monitor:
                await self.system_monitor.shutdown()

            if self.realtime_adapter:
                await self.realtime_adapter.shutdown()

            if self.integration_manager:
                # integration_manager has no shutdown method, skip
                pass

            if self.fault_recovery_manager:
                await self.fault_recovery_manager.stop()

            if self.performance_optimizer:
                await self.performance_optimizer.shutdown()

            if self.connection_monitor:
                await self.connection_monitor.stop_monitoring()

            if self.enhanced_client:
                await self.enhanced_client.disconnect()

            logger.info("✅ Test environment cleanup complete")

        except Exception as e:
            logger.error(f"⚠️ Test environment cleanup failed: {e}")

    async def _run_unit_tests(self) -> None:
        """Run unit tests"""
        logger.info("🧪 Running unit tests...")

        # Test data converter
        await self._test_data_converter()

        # Test cache system
        await self._test_intelligent_cache()

        # Test connection pool
        await self._test_connection_pool()

        # Test circuit breaker
        await self._test_circuit_breaker()

        # Test data quality evaluation
        await self._test_data_quality_evaluation()

    async def _test_data_converter(self) -> None:
        """Test data converter"""
        test_name = "Data Converter Test"
        start_time = time.perf_counter()

        try:
            converter = TradingViewDataConverter()

            # Test normal data conversion
            tv_data = {
                'time': time.time(),
                'open': 50000.0,
                'high': 51000.0,
                'low': 49500.0,
                'close': 50500.0,
                'volume': 1000.0
            }

            market_data = converter.convert_kline_to_market_data(tv_data, "BTC/USDT")
            assert market_data is not None, "Normal data conversion failed"
            assert market_data.symbol == "BTC/USDT", "Symbol conversion error"
            assert market_data.close == 50500.0, "Price conversion error"

            # Test abnormal data processing
            invalid_data = {'invalid': 'data'}
            result = converter.convert_kline_to_market_data(invalid_data, "BTC/USDT")
            assert result is None, "Abnormal data should return None"

            # Test conversion stats
            stats = converter.get_conversion_stats()
            assert 'success_rate' in stats, "Missing conversion stats"

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.UNIT, TestStatus.PASSED, duration_ms)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.UNIT, TestStatus.FAILED, duration_ms, str(e))

    async def _test_intelligent_cache(self) -> None:
        """Test intelligent cache"""
        test_name = "Intelligent Cache Test"
        start_time = time.perf_counter()

        try:
            cache = IntelligentCache(max_size=100)
            await cache.start()

            try:
                # Test basic cache operations
                test_key = "test_key"
                test_value = {"data": "test_value"}

                # Test set and get
                result = await cache.put(test_key, test_value)
                assert result is True, "Cache set failed"

                cached_value = cache.get(test_key)
                assert cached_value is not None, "Cache get failed"
                assert cached_value["data"] == "test_value", "Cache value mismatch"

                # Test cache stats
                stats = cache.get_cache_stats()
                assert stats['hits'] > 0, "Cache hit statistics error"
                assert stats['entry_count'] > 0, "Cache entry statistics error"

                # Test cache clear
                cache.clear()
                assert cache.get(test_key) is None, "Cache clear failed"

                duration_ms = (time.perf_counter() - start_time) * 1000
                self._record_test_result(test_name, TestCategory.UNIT, TestStatus.PASSED, duration_ms)

            finally:
                await cache.stop()

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.UNIT, TestStatus.FAILED, duration_ms, str(e))

    async def _test_connection_pool(self) -> None:
        """Test connection pool"""
        test_name = "Connection Pool Test"
        start_time = time.perf_counter()

        try:
            # Mock connection factory
            async def mock_connection_factory():
                await asyncio.sleep(0.01)  # Simulate connection creation time
                return f"mock_connection_{time.time()}"

            pool = ConnectionPool(min_connections=2, max_connections=10)
            await pool.initialize(mock_connection_factory)

            try:
                # Test get connection
                connection = await pool.get_connection()
                assert connection is not None, "Failed to get connection"

                # Test return connection
                result = await pool.return_connection(connection)
                assert result is True, "Failed to return connection"

                # Test connection pool stats
                stats = pool.get_pool_stats()
                assert 'current_active' in stats, "Missing connection pool stats"
                assert 'total_created' in stats, "Missing connection creation stats"

                duration_ms = (time.perf_counter() - start_time) * 1000
                self._record_test_result(test_name, TestCategory.UNIT, TestStatus.PASSED, duration_ms)

            finally:
                await pool.shutdown()

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.UNIT, TestStatus.FAILED, duration_ms, str(e))

    async def _test_circuit_breaker(self) -> None:
        """Test circuit breaker"""
        test_name = "Circuit Breaker Test"
        start_time = time.perf_counter()

        try:
            from .fault_recovery import CircuitBreaker

            circuit_breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=1)

            # Test normal call
            def success_func():
                return "success"

            result = circuit_breaker.call(success_func)
            assert result == "success", "Normal call failed"

            # Test failure call
            def failure_func():
                raise Exception("test failure")

            # Trigger circuit breaker open
            for _ in range(4):
                try:
                    circuit_breaker.call(failure_func)
                except:
                    pass

            # Circuit breaker should be OPEN
            assert circuit_breaker.state == "OPEN", "Circuit breaker not open"

            # Test circuit breaker stats
            stats = circuit_breaker.get_stats()
            assert stats['total_failures'] >= 3, "Failure statistics error"
            assert stats['state'] == "OPEN", "Circuit breaker state error"

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.UNIT, TestStatus.PASSED, duration_ms)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.UNIT, TestStatus.FAILED, duration_ms, str(e))

    async def _test_data_quality_evaluation(self) -> None:
        """Test data quality evaluation"""
        test_name = "Data Quality Evaluation Test"
        start_time = time.perf_counter()

        try:
            engine = self.data_quality_engine

            # Test high quality data
            good_data = [{
                'time': time.time(),
                'open': 50000.0,
                'high': 51000.0,
                'low': 49500.0,
                'close': 50500.0,
                'volume': 1000.0
            }]

            metrics = await engine.evaluate_data_quality("UNIT_TEST_SYMBOL", good_data)
            assert metrics.overall_quality_score > 0.8, f"High quality data score too low: {metrics.overall_quality_score}"
            assert metrics.quality_level in [QualityLevel.EXCELLENT, QualityLevel.GOOD], "Quality level error"

            # Test low quality data
            bad_data = [{
                'time': time.time(),
                'open': -1.0,  # Negative price
                'high': 0.0,   # Zero price
                'low': 100.0,  # Logical error in price relationship
                'close': 50.0
            }]

            metrics = await engine.evaluate_data_quality("UNIT_TEST_SYMBOL_BAD", bad_data)
            assert metrics.overall_quality_score < 0.5, f"Low quality data score too high: {metrics.overall_quality_score}"

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.UNIT, TestStatus.PASSED, duration_ms)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.UNIT, TestStatus.FAILED, duration_ms, str(e))

    async def _run_integration_tests(self) -> None:
        """Run integration tests"""
        logger.info("🔗 Running integration tests...")

        # Test end-to-end data flow
        await self._test_end_to_end_data_flow()

        # Test component communication
        await self._test_component_communication()

        # Test system monitoring integration
        await self._test_system_monitoring_integration()

        # Test configuration management integration
        await self._test_configuration_integration()

    async def _test_end_to_end_data_flow(self) -> None:
        """Test end-to-end data flow"""
        test_name = "End-to-End Data Flow Test"
        start_time = time.perf_counter()

        try:
            # Simulate full data flow: TradingView -> Data Quality -> Conversion -> Realtime Adapter

            # 1. Mock TradingView data
            tv_data = {
                'time': time.time(),
                'open': 50000.0,
                'high': 51000.0,
                'low': 49500.0,
                'close': 50500.0,
                'volume': 1000.0
            }

            # 2. Data quality evaluation
            quality_metrics = await self.data_quality_engine.evaluate_data_quality("BTC/USDT", [tv_data])
            assert quality_metrics.overall_quality_score > 0.7, f"Data quality assessment failed: {quality_metrics.overall_quality_score}"

            # 3. Data format conversion
            converter = TradingViewDataConverter()
            market_data = converter.convert_kline_to_market_data(tv_data, "BTC/USDT")
            assert market_data is not None, "Data conversion failed"

            # 4. Realtime adapter processing
            success = await self.realtime_adapter.process_realtime_data(
                "BTC/USDT", tv_data, SubscriptionType.KLINE_15M
            )
            assert success is True, "Realtime adapter processing failed"

            # 5. Verify data integrity
            assert market_data.symbol == "BTC/USDT", "Symbol mismatch"
            assert market_data.close == 50500.0, "Price mismatch"
            assert market_data.quality_score > 0.7, "Quality score too low"

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.INTEGRATION, TestStatus.PASSED, duration_ms)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.INTEGRATION, TestStatus.FAILED, duration_ms, str(e))

    async def _test_component_communication(self) -> None:
        """Test component communication"""
        test_name = "Component Communication Test"
        start_time = time.perf_counter()

        try:
            # Test communication between fault recovery manager and other components

            # 1. Register component health check
            async def mock_health_check():
                return {
                    'response_time_ms': 100,
                    'success_rate': 0.95,
                    'data_quality_score': 0.9
                }

            self.fault_recovery_manager.register_component('test_component', mock_health_check)

            # 2. Wait for health check to execute
            await asyncio.sleep(2)

            # 3. Verify health report
            health_report = self.fault_recovery_manager.get_system_health_report()
            assert 'component_health' in health_report, "Missing component health info"

            # 4. Test system monitoring data collection
            dashboard = self.system_monitor.get_system_dashboard()
            assert 'system_overview' in dashboard, "Missing system overview"
            assert 'component_summary' in dashboard, "Missing component summary"

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.INTEGRATION, TestStatus.PASSED, duration_ms)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.INTEGRATION, TestStatus.FAILED, duration_ms, str(e))

    async def _test_system_monitoring_integration(self) -> None:
        """Test system monitoring integration"""
        test_name = "System Monitoring Integration Test"
        start_time = time.perf_counter()

        try:
            # Wait for monitor to collect data
            await asyncio.sleep(3)

            # Get dashboard data
            dashboard = self.system_monitor.get_system_dashboard()

            # Verify basic structure
            required_sections = [
                'system_overview', 'component_summary', 'performance_metrics',
                'data_metrics', 'fault_metrics', 'monitoring_stats'
            ]

            for section in required_sections:
                assert section in dashboard, f"Missing dashboard section: {section}"

            # Verify system overview
            system_overview = dashboard['system_overview']
            assert 'status' in system_overview, "Missing system status"
            assert 'health_score' in system_overview, "Missing health score"
            assert 'uptime_seconds' in system_overview, "Missing uptime"

            # Verify component summary
            component_summary = dashboard['component_summary']
            assert component_summary['total_components'] > 0, "Component count is 0"

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.INTEGRATION, TestStatus.PASSED, duration_ms)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.INTEGRATION, TestStatus.FAILED, duration_ms, str(e))

    async def _test_configuration_integration(self) -> None:
        """Test configuration management integration"""
        test_name = "Configuration Management Integration Test"
        start_time = time.perf_counter()

        try:
            # Test if each component's configuration is loaded correctly

            # 1. Verify performance optimizer configuration
            if self.performance_optimizer:
                perf_stats = self.performance_optimizer.get_comprehensive_stats()
                assert 'cache_stats' in perf_stats, "Missing cache stats"
                assert 'pool_stats' in perf_stats, "Missing connection pool stats"

            # 2. Verify fault recovery manager configuration
            if self.fault_recovery_manager:
                health_report = self.fault_recovery_manager.get_system_health_report()
                assert 'recovery_stats' in health_report, "Missing recovery stats"

            # 3. Verify realtime adapter configuration
            if self.realtime_adapter:
                adapter_stats = self.realtime_adapter.get_comprehensive_stats()
                assert 'subscription_status' in adapter_stats, "Missing subscription status"

            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.INTEGRATION, TestStatus.PASSED, duration_ms)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.INTEGRATION, TestStatus.FAILED, duration_ms, str(e))

    async def _run_performance_tests(self) -> None:
        """Run performance tests"""
        logger.info("⚡ Running performance tests...")

        # Test data processing performance
        await self._test_data_processing_performance()

        # Test cache performance
        await self._test_cache_performance()

        # Test concurrent processing performance
        await self._test_concurrent_performance()

        # Test memory usage
        await self._test_memory_usage()

    async def _test_data_processing_performance(self) -> None:
        """Test data processing performance"""
        test_name = "Data Processing Performance Test"
        start_time = time.perf_counter()

        try:
            converter = TradingViewDataConverter()
            data_count = 1000

            # Generate test data
            test_data = []
            for i in range(data_count):
                test_data.append({
                    'time': time.time() + i,
                    'open': 50000.0 + random.uniform(-100, 100),
                    'high': 51000.0 + random.uniform(-100, 100),
                    'low': 49500.0 + random.uniform(-100, 100),
                    'close': 50500.0 + random.uniform(-100, 100),
                    'volume': 1000.0 + random.uniform(-100, 100)
                })

            # Test conversion performance
            conversion_start = time.perf_counter()
            successful_conversions = 0

            for data in test_data:
                result = converter.convert_kline_to_market_data(data, "BTC/USDT")
                if result:
                    successful_conversions += 1

            conversion_time = (time.perf_counter() - conversion_start) * 1000
            avg_conversion_time = conversion_time / data_count

            # Verify performance metrics
            assert avg_conversion_time < 1.0, f"Average conversion time too long: {avg_conversion_time:.2f}ms"
            assert successful_conversions / data_count > 0.95, f"Conversion success rate too low: {successful_conversions/data_count:.1%}"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'data_count': data_count,
                'total_conversion_time_ms': conversion_time,
                'avg_conversion_time_ms': avg_conversion_time,
                'success_rate': successful_conversions / data_count
            }

            self._record_test_result(test_name, TestCategory.PERFORMANCE, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.PERFORMANCE, TestStatus.FAILED, duration_ms, str(e))

    async def _test_cache_performance(self) -> None:
        """Test cache performance"""
        test_name = "Cache Performance Test"
        start_time = time.perf_counter()

        try:
            cache = IntelligentCache(max_size=1000)
            await cache.start()

            try:
                # Test large write operations
                write_count = 1000
                write_start = time.time()

                for i in range(write_count):
                    await cache.put(f"key_{i}", f"value_{i}")

                write_time = (time.time() - write_start) * 1000
                avg_write_time = write_time / write_count

                # Test large read operations
                read_start = time.time()
                hits = 0

                for i in range(write_count):
                    value = cache.get(f"key_{i}")
                    if value:
                        hits += 1

                read_time = (time.time() - read_start) * 1000
                avg_read_time = read_time / write_count
                hit_rate = hits / write_count

                # Verify performance metrics
                assert avg_write_time < 0.1, f"Average write time too long: {avg_write_time:.3f}ms"
                assert avg_read_time < 0.05, f"Average read time too long: {avg_read_time:.3f}ms"
                assert hit_rate > 0.99, f"Cache hit rate too low: {hit_rate:.1%}"

                duration_ms = (time.perf_counter() - start_time) * 1000
                details = {
                    'write_count': write_count,
                    'avg_write_time_ms': avg_write_time,
                    'avg_read_time_ms': avg_read_time,
                    'hit_rate': hit_rate
                }

                self._record_test_result(test_name, TestCategory.PERFORMANCE, TestStatus.PASSED, duration_ms, details=details)

            finally:
                await cache.stop()

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.PERFORMANCE, TestStatus.FAILED, duration_ms, str(e))

    async def _test_concurrent_performance(self) -> None:
        """Test concurrent processing performance"""
        test_name = "Concurrent Processing Performance Test"
        start_time = time.perf_counter()

        try:
            # Create multiple concurrent tasks
            concurrent_tasks = 100
            tasks = []

            async def data_processing_task(task_id: int):
                """Single data processing task"""
                converter = TradingViewDataConverter()

                for i in range(10):  # Each task processes 10 data points
                    data = {
                        'time': time.time() + i,
                        'open': 50000.0 + random.uniform(-100, 100),
                        'high': 51000.0 + random.uniform(-100, 100),
                        'low': 49500.0 + random.uniform(-100, 100),
                        'close': 50500.0 + random.uniform(-100, 100),
                        'volume': 1000.0
                    }

                    result = converter.convert_kline_to_market_data(data, f"SYMBOL_{task_id}")
                    if not result:
                        raise Exception(f"Task {task_id} conversion failed")

                return task_id

            # Start all concurrent tasks
            concurrent_start = time.time()

            for i in range(concurrent_tasks):
                task = asyncio.create_task(data_processing_task(i))
                tasks.append(task)

            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            concurrent_time = (time.time() - concurrent_start) * 1000

            # Aggregate results
            successful_tasks = sum(1 for r in results if not isinstance(r, Exception))
            failed_tasks = len(results) - successful_tasks

            # Verify concurrent performance
            assert concurrent_time < 5000, f"Concurrent processing time too long: {concurrent_time:.1f}ms"
            assert successful_tasks / concurrent_tasks > 0.95, f"Concurrent success rate too low: {successful_tasks/concurrent_tasks:.1%}"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'concurrent_tasks': concurrent_tasks,
                'concurrent_time_ms': concurrent_time,
                'successful_tasks': successful_tasks,
                'failed_tasks': failed_tasks,
                'success_rate': successful_tasks / concurrent_tasks
            }

            self._record_test_result(test_name, TestCategory.PERFORMANCE, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.PERFORMANCE, TestStatus.FAILED, duration_ms, str(e))

    async def _test_memory_usage(self) -> None:
        """Test memory usage"""
        test_name = "Memory Usage Test"
        start_time = time.perf_counter()

        try:
            import psutil
            import gc

            # Record initial memory usage
            process = psutil.Process()
            initial_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Create large amount of data for processing
            converter = TradingViewDataConverter()
            data_count = 10000
            processed_data = []

            for i in range(data_count):
                data = {
                    'time': time.time() + i,
                    'open': 50000.0 + random.uniform(-100, 100),
                    'high': 51000.0 + random.uniform(-100, 100),
                    'low': 49500.0 + random.uniform(-100, 100),
                    'close': 50500.0 + random.uniform(-100, 100),
                    'volume': 1000.0
                }

                result = converter.convert_kline_to_market_data(data, "BTC/USDT")
                if result:
                    processed_data.append(result)

            # Record peak memory usage
            peak_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Cleanup data
            processed_data.clear()
            gc.collect()

            # Record final memory usage
            final_memory = process.memory_info().rss / 1024 / 1024  # MB

            # Calculate memory metrics
            memory_increase = peak_memory - initial_memory
            memory_per_item = memory_increase / data_count * 1024  # KB per item
            memory_cleanup_ratio = (peak_memory - final_memory) / memory_increase if memory_increase > 0 else 0

            # Verify memory usage reasonableness
            assert memory_per_item < 2.0, f"Memory usage per item too high: {memory_per_item:.2f}KB"
            assert memory_cleanup_ratio > 0.2, f"Memory cleanup effect poor: {memory_cleanup_ratio:.1%}"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'data_count': data_count,
                'initial_memory_mb': initial_memory,
                'peak_memory_mb': peak_memory,
                'final_memory_mb': final_memory,
                'memory_increase_mb': memory_increase,
                'memory_per_item_kb': memory_per_item,
                'memory_cleanup_ratio': memory_cleanup_ratio
            }

            self._record_test_result(test_name, TestCategory.PERFORMANCE, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.PERFORMANCE, TestStatus.FAILED, duration_ms, str(e))

    async def _run_fault_tests(self) -> None:
        """Run fault tests"""
        logger.info("🛡️ Running fault tests...")

        # Test fault detection
        await self._test_fault_detection()

        # Test fault recovery
        await self._test_fault_recovery()

        # Test circuit breaker fault handling
        await self._test_circuit_breaker_fault_handling()

        # Test backup source switching
        await self._test_backup_source_switching()

    async def _test_fault_detection(self) -> None:
        """Test fault detection"""
        test_name = "Fault Detection Test"
        start_time = time.perf_counter()

        try:
            # Simulate fault conditions
            fault_metrics = {
                'component': 'test_component',
                'response_time_ms': 6000,  # Exceeds 5s threshold
                'success_rate': 0.3,       # Below 80% threshold
                'data_quality_score': 0.4  # Below 50% threshold
            }

            # Trigger fault detection
            detected_faults = await self.fault_recovery_manager.fault_detector.check_for_faults(fault_metrics)

            # Verify fault detection results
            assert len(detected_faults) > 0, "No faults detected"

            # Verify fault types
            fault_types = [fault.fault_type for fault in detected_faults]
            expected_types = [FaultType.DATA_TIMEOUT, FaultType.SYSTEM_OVERLOAD, FaultType.DATA_CORRUPTION]

            for expected_type in expected_types:
                assert expected_type in fault_types, f"Expected fault type not detected: {expected_type}"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'detected_faults_count': len(detected_faults),
                'fault_types': [f.fault_type.name for f in detected_faults]
            }

            self._record_test_result(test_name, TestCategory.FAULT, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.FAULT, TestStatus.FAILED, duration_ms, str(e))

    async def _test_fault_recovery(self) -> None:
        """Test fault recovery"""
        test_name = "Fault Recovery Test"
        start_time = time.perf_counter()

        try:
            from .fault_recovery import FaultIncident

            # Create mock fault
            incident = FaultIncident(
                incident_id="test_recovery_001",
                fault_type=FaultType.CONNECTION_LOST,
                component="test_component",
                description="Simulated connection loss fault",
                severity=3
            )

            # Record initial active incidents count
            initial_active_incidents = len(self.fault_recovery_manager.active_incidents)

            # Trigger fault handling
            await self.fault_recovery_manager._handle_detected_fault(incident)

            # Wait for recovery attempt
            await asyncio.sleep(2)

            # Verify fault has been recorded
            assert len(self.fault_recovery_manager.active_incidents) > initial_active_incidents, "Fault not recorded"

            # Verify recovery strategy has been set
            assert incident.recovery_strategy is not None, "Recovery strategy not set"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'incident_id': incident.incident_id,
                'recovery_strategy': incident.recovery_strategy.name if incident.recovery_strategy else None,
                'recovery_attempts': incident.recovery_attempts
            }

            self._record_test_result(test_name, TestCategory.FAULT, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.FAULT, TestStatus.FAILED, duration_ms, str(e))

    async def _test_circuit_breaker_fault_handling(self) -> None:
        """Test circuit breaker fault handling"""
        test_name = "Circuit Breaker Fault Handling Test"
        start_time = time.perf_counter()

        try:
            circuit_breaker = self.fault_recovery_manager.get_circuit_breaker("test_component")

            # Simulate consecutive failures
            def failing_function():
                raise Exception("Simulated failure")

            failure_count = 0
            for i in range(10):
                try:
                    circuit_breaker.call(failing_function)
                except:
                    failure_count += 1

            # Verify circuit breaker state
            stats = circuit_breaker.get_stats()
            assert stats['state'] == 'OPEN', f"Circuit breaker state error: {stats['state']}"
            assert stats['total_failures'] >= 5, f"Failure count error: {stats['total_failures']}"

            # Test circuit breaker blocking subsequent calls
            try:
                circuit_breaker.call(lambda: "success")
                assert False, "Circuit breaker failed to block call"
            except Exception as e:
                assert "Circuit breaker is OPEN" in str(e), "Circuit breaker error message incorrect"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'circuit_breaker_state': stats['state'],
                'total_failures': stats['total_failures'],
                'failure_rate': stats['failure_rate']
            }

            self._record_test_result(test_name, TestCategory.FAULT, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.FAULT, TestStatus.FAILED, duration_ms, str(e))

    async def _test_backup_source_switching(self) -> None:
        """Test backup source switching"""
        test_name = "Backup Source Switching Test"
        start_time = time.perf_counter()

        try:
            # Create mock backup data source
            async def mock_backup_client():
                return "mock_backup_client"

            backup_source = BackupDataSource(
                name="mock_backup",
                priority=1,
                client_factory=mock_backup_client
            )

            # Add backup data source
            self.fault_recovery_manager.add_backup_source("test_component", backup_source)

            # Simulate fault requiring switch to backup source
            from .fault_recovery import FaultIncident

            incident = FaultIncident(
                incident_id="backup_test_001",
                fault_type=FaultType.DATA_TIMEOUT,
                component="test_component",
                description="Requires switch to backup data source",
                severity=2
            )

            # Execute backup source recovery
            await self.fault_recovery_manager._fallback_source_recovery(incident)

            # Verify backup source state
            backup_stats = backup_source.get_stats()
            assert backup_source.is_active or incident.is_resolved, "Backup source switching failed"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'backup_source_name': backup_source.name,
                'is_active': backup_source.is_active,
                'incident_resolved': incident.is_resolved
            }

            self._record_test_result(test_name, TestCategory.FAULT, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.FAULT, TestStatus.FAILED, duration_ms, str(e))

    async def _run_stress_tests(self) -> None:
        """Run stress tests"""
        logger.info("💪 Running stress tests...")

        # Test high frequency data processing
        await self._test_high_frequency_data_processing()

        # Test long running stability
        await self._test_long_running_stability()

        # Test resource exhaustion scenario
        await self._test_resource_exhaustion()

    async def _test_high_frequency_data_processing(self) -> None:
        """Test high frequency data processing"""
        test_name = "High Frequency Data Processing Stress Test"
        start_time = time.perf_counter()

        try:
            # Configure high frequency test parameters
            data_rate = 100  # 100 data points per second
            test_duration = 30  # Test for 30 seconds
            total_expected = data_rate * test_duration

            processed_count = 0
            error_count = 0

            async def data_generator():
                """Data generator"""
                nonlocal processed_count, error_count

                end_time = time.time() + test_duration
                while time.time() < end_time:
                    try:
                        # Generate simulated data
                        data = {
                            'time': time.time(),
                            'open': 50000.0 + random.uniform(-100, 100),
                            'high': 51000.0 + random.uniform(-100, 100),
                            'low': 49500.0 + random.uniform(-100, 100),
                            'close': 50500.0 + random.uniform(-100, 100),
                            'volume': 1000.0
                        }

                        # Process data
                        success = await self.realtime_adapter.process_realtime_data(
                            "BTC/USDT", data, SubscriptionType.KLINE_15M
                        )

                        if success:
                            processed_count += 1
                        else:
                            error_count += 1

                        # Control data frequency
                        await asyncio.sleep(1.0 / data_rate)

                    except Exception as e:
                        error_count += 1
                        logger.error(f"Data processing error: {e}")

            # Start data generator
            await data_generator()

            # Verify processing results
            success_rate = processed_count / (processed_count + error_count) if (processed_count + error_count) > 0 else 0
            processing_rate = processed_count / test_duration

            assert success_rate > 0.90, f"High frequency processing success rate too low: {success_rate:.1%}"
            assert processing_rate >= data_rate * 0.7, f"Insufficient processing rate: {processing_rate:.1f}/s (Expected: {data_rate}/s)"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'test_duration_s': test_duration,
                'target_data_rate': data_rate,
                'processed_count': processed_count,
                'error_count': error_count,
                'success_rate': success_rate,
                'actual_processing_rate': processing_rate
            }

            self._record_test_result(test_name, TestCategory.STRESS, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.STRESS, TestStatus.FAILED, duration_ms, str(e))

    async def _test_long_running_stability(self) -> None:
        """Test long running stability"""
        test_name = "Long-term Stability Stress Test"
        start_time = time.perf_counter()

        try:
            # Configure long running test parameters
            test_duration = 60  # Test for 60 seconds
            check_interval = 5   # Check every 5 seconds

            initial_stats = {
                'system_health': 0,
                'memory_usage': 0,
                'active_connections': 0
            }

            # Record initial state
            if self.system_monitor:
                dashboard = self.system_monitor.get_system_dashboard()
                initial_stats['system_health'] = dashboard.get('system_overview', {}).get('health_score', 0)

            stability_checks = []
            end_time = time.time() + test_duration

            # Regular stability checks
            while time.time() < end_time:
                try:
                    check_time = time.time()

                    # Check system state
                    if self.system_monitor:
                        dashboard = self.system_monitor.get_system_dashboard()
                        system_overview = dashboard.get('system_overview', {})

                        check_result = {
                            'timestamp': check_time,
                            'health_score': system_overview.get('health_score', 0),
                            'status': system_overview.get('status', 'UNKNOWN'),
                            'uptime': system_overview.get('uptime_seconds', 0)
                        }

                        stability_checks.append(check_result)

                    await asyncio.sleep(check_interval)

                except Exception as e:
                    logger.error(f"Stability check error: {e}")

            # Analyze stability data
            if stability_checks:
                health_scores = [check['health_score'] for check in stability_checks]
                avg_health = sum(health_scores) / len(health_scores)
                min_health = min(health_scores)
                health_variance = sum((h - avg_health) ** 2 for h in health_scores) / len(health_scores)

                # Verify stability metrics
                assert avg_health > 0.2, f"Average health score too low: {avg_health:.2f}"
                assert min_health >= 0.0, f"Minimum health score too low: {min_health:.2f}"
                assert health_variance < 0.2, f"Health score variance too high: {health_variance:.3f}"

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'test_duration_s': test_duration,
                'stability_checks': len(stability_checks),
                'avg_health_score': avg_health if stability_checks else 0,
                'min_health_score': min_health if stability_checks else 0,
                'health_variance': health_variance if stability_checks else 0
            }

            self._record_test_result(test_name, TestCategory.STRESS, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.STRESS, TestStatus.FAILED, duration_ms, str(e))

    async def _test_resource_exhaustion(self) -> None:
        """Test resource exhaustion scenario"""
        test_name = "Resource Exhaustion Scenario Test"
        start_time = time.perf_counter()

        try:
            # Test cache capacity limit
            cache = IntelligentCache(max_size=100)  # Small capacity cache
            await cache.start()

            try:
                # Write data exceeding capacity
                write_count = 200
                for i in range(write_count):
                    await cache.put(f"key_{i}", f"large_value_{i}" * 100)  # Large values

                # Verify cache size limit
                stats = cache.get_cache_stats()
                assert stats['current_size'] <= 100, f"Cache size exceeds limit: {stats['current_size']}"
                assert stats['evictions'] > 0, "No cache evictions occurred"

                # Test cache performance under resource pressure
                hit_count = 0
                test_reads = 50

                for i in range(test_reads):
                    value = cache.get(f"key_{i + write_count - test_reads}")  # Read most recent data
                    if value:
                        hit_count += 1

                hit_rate = hit_count / test_reads
                assert hit_rate > 0.8, f"Cache hit rate too low under resource pressure: {hit_rate:.1%}"

            finally:
                await cache.stop()

            duration_ms = (time.perf_counter() - start_time) * 1000
            details = {
                'cache_max_size': 100,
                'data_written': write_count,
                'evictions': stats.get('evictions', 0),
                'final_cache_size': stats.get('current_size', 0),
                'hit_rate_under_pressure': hit_rate
            }

            self._record_test_result(test_name, TestCategory.STRESS, TestStatus.PASSED, duration_ms, details=details)

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            self._record_test_result(test_name, TestCategory.STRESS, TestStatus.FAILED, duration_ms, str(e))

    def _record_test_result(self, test_name: str, category: TestCategory, status: TestStatus,
                          duration_ms: float, error_message: str = "", details: Dict[str, Any] = None) -> None:
        """Record test result"""
        result = TestResult(
            test_name=test_name,
            category=category,
            status=status,
            duration_ms=duration_ms,
            error_message=error_message,
            details=details or {}
        )

        self.test_results.append(result)

        # Update statistics
        self.test_stats['total_tests'] += 1
        if status == TestStatus.PASSED:
            self.test_stats['passed_tests'] += 1
        elif status == TestStatus.FAILED:
            self.test_stats['failed_tests'] += 1
        elif status == TestStatus.SKIPPED:
            self.test_stats['skipped_tests'] += 1

        # Log entry
        status_emoji = {
            TestStatus.PASSED: "✅",
            TestStatus.FAILED: "❌",
            TestStatus.SKIPPED: "⏭️"
        }

        emoji = status_emoji.get(status, "❓")
        logger.info(f"{emoji} {test_name} ({category.name}): {status.name} ({duration_ms:.1f}ms)")

        if error_message:
            logger.error(f"   Error: {error_message}")

    def _generate_test_report(self) -> Dict[str, Any]:
        """Generate test report"""
        try:
            # Breakdown by category
            category_stats = {}
            for category in TestCategory:
                category_results = [r for r in self.test_results if r.category == category]
                category_stats[category.name] = {
                    'total': len(category_results),
                    'passed': len([r for r in category_results if r.status == TestStatus.PASSED]),
                    'failed': len([r for r in category_results if r.status == TestStatus.FAILED]),
                    'skipped': len([r for r in category_results if r.status == TestStatus.SKIPPED]),
                    'avg_duration_ms': sum(r.duration_ms for r in category_results) / len(category_results) if category_results else 0
                }

            # Failed tests details
            failed_tests = [r for r in self.test_results if r.status == TestStatus.FAILED]

            # Performance statistics
            performance_tests = [r for r in self.test_results if r.category == TestCategory.PERFORMANCE]
            performance_summary = {}

            if performance_tests:
                performance_summary = {
                    'avg_duration_ms': sum(r.duration_ms for r in performance_tests) / len(performance_tests),
                    'max_duration_ms': max(r.duration_ms for r in performance_tests),
                    'min_duration_ms': min(r.duration_ms for r in performance_tests)
                }

            # Calculate overall success rate
            success_rate = self.test_stats['passed_tests'] / max(1, self.test_stats['total_tests'])

            return {
                'summary': {
                    'total_tests': self.test_stats['total_tests'],
                    'passed_tests': self.test_stats['passed_tests'],
                    'failed_tests': self.test_stats['failed_tests'],
                    'skipped_tests': self.test_stats['skipped_tests'],
                    'success_rate': success_rate,
                    'total_duration_ms': self.test_stats['total_duration_ms']
                },
                'category_breakdown': category_stats,
                'performance_summary': performance_summary,
                'failed_tests': [
                    {
                        'name': test.test_name,
                        'category': test.category.name,
                        'error': test.error_message,
                        'duration_ms': test.duration_ms
                    }
                    for test in failed_tests
                ],
                'detailed_results': [
                    {
                        'name': test.test_name,
                        'category': test.category.name,
                        'status': test.status.name,
                        'duration_ms': test.duration_ms,
                        'timestamp': test.timestamp,
                        'details': test.details
                    }
                    for test in self.test_results
                ],
                'test_environment': {
                    'components_tested': [
                        'enhanced_client', 'data_quality_engine', 'connection_monitor',
                        'performance_optimizer', 'fault_recovery_manager',
                        'integration_manager', 'realtime_adapter', 'system_monitor'
                    ],
                    'test_symbols': self.test_config['test_symbols'],
                    'performance_threshold_ms': self.test_config['performance_threshold_ms'],
                    'quality_threshold': self.test_config['quality_threshold']
                }
            }

        except Exception as e:
            logger.error(f"Failed to generate test report: {e}")
            return {'error': f'Failed to generate test report: {e}'}


# Helper functions
def create_integration_test_suite() -> IntegrationTestSuite:
    """Create integration test suite"""
    return IntegrationTestSuite()


async def run_complete_integration_test():
    """Run full integration test"""
    logger.info("🚀 Starting TradingView Data Source Module Full Integration Test")

    # Create test suite
    test_suite = create_integration_test_suite()

    try:
        # Run all tests
        test_report = await test_suite.run_all_tests()

        # Output test report
        print("\n" + "="*80)
        print("📊 TradingView Data Source Module Integration Test Report")
        print("="*80)

        summary = test_report.get('summary', {})
        print(f"Total Tests: {summary.get('total_tests', 0)}")
        print(f"Passed: {summary.get('passed_tests', 0)}")
        print(f"Failed: {summary.get('failed_tests', 0)}")
        print(f"Skipped: {summary.get('skipped_tests', 0)}")
        print(f"Success Rate: {summary.get('success_rate', 0):.1%}")
        print(f"Total Duration: {summary.get('total_duration_ms', 0):.1f}ms")

        # Breakdown by category
        print("\n📋 Category Breakdown:")
        category_breakdown = test_report.get('category_breakdown', {})
        for category, stats in category_breakdown.items():
            print(f"  {category}: {stats['passed']}/{stats['total']} Passed "
                  f"(Average Duration: {stats['avg_duration_ms']:.1f}ms)")

        # Failed tests
        failed_tests = test_report.get('failed_tests', [])
        if failed_tests:
            print("\n❌ Failed Tests:")
            for test in failed_tests:
                print(f"  - {test['name']} ({test['category']}): {test['error']}")

        # Performance summary
        performance_summary = test_report.get('performance_summary', {})
        if performance_summary:
            print(f"\n⚡ Performance Summary:")
            print(f"  Average Duration: {performance_summary.get('avg_duration_ms', 0):.1f}ms")
            print(f"  Max Duration: {performance_summary.get('max_duration_ms', 0):.1f}ms")
            print(f"  Min Duration: {performance_summary.get('min_duration_ms', 0):.1f}ms")

        print("="*80)

        # Determine overall test result
        if summary.get('success_rate', 0) >= 0.9:
            print("🎉 Integration test overall passed! TradingView data source module enhanced features are working well.")
            return True
        else:
            print("⚠️ Integration test found issues, further debugging and optimization required.")
            return False

    except Exception as e:
        logger.error(f"Integration test execution failed: {e}")
        print(f"❌ Integration test execution failed: {e}")
        return False


if __name__ == "__main__":
    # Run full integration test
    asyncio.run(run_complete_integration_test())
