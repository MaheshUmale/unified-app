#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Data Quality Monitoring System
Implements multi-dimensional data quality assessment, anomaly detection, and quality reporting.
"""

import asyncio
import time
import statistics
import math
from typing import Dict, List, Optional, Tuple, Any, Set
from collections import deque, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto

from tradingview.utils import get_logger

logger = get_logger(__name__)


class QualityLevel(Enum):
    """Quality levels"""
    EXCELLENT = auto()  # 95-100%
    GOOD = auto()       # 85-94%
    FAIR = auto()       # 70-84%
    POOR = auto()       # 50-69%
    CRITICAL = auto()   # 0-49%


class AnomalyType(Enum):
    """Anomaly types"""
    PRICE_SPIKE = auto()        # Price spikes
    VOLUME_ANOMALY = auto()     # Volume anomalies
    TIME_GAP = auto()           # Gap in time sequence
    MISSING_DATA = auto()       # Missing data points
    DUPLICATE_DATA = auto()     # Duplicate records
    INVALID_OHLC = auto()       # Logical OHLC errors
    EXTREME_VALUE = auto()      # Values outside normal range
    PATTERN_BREAK = auto()      # Sudden change in data pattern


@dataclass
class QualityMetrics:
    """Quality metrics data structure"""
    symbol: str
    timeframe: str
    timestamp: float = field(default_factory=time.time)

    # Completeness metrics
    completeness_score: float = 1.0
    missing_data_ratio: float = 0.0
    duplicate_data_ratio: float = 0.0

    # Accuracy metrics
    accuracy_score: float = 1.0
    invalid_ohlc_ratio: float = 0.0
    extreme_value_ratio: float = 0.0

    # Consistency metrics
    consistency_score: float = 1.0
    time_consistency_ratio: float = 1.0
    value_consistency_ratio: float = 1.0

    # Timeliness metrics
    timeliness_score: float = 1.0
    data_delay: float = 0.0
    update_frequency: float = 0.0

    # Anomaly tracking
    anomaly_count: int = 0
    anomaly_types: Dict[str, int] = field(default_factory=dict)
    anomaly_severity: float = 0.0

    # Overall score
    overall_quality_score: float = 1.0
    quality_level: QualityLevel = QualityLevel.EXCELLENT

    # Record counts
    total_records: int = 0
    valid_records: int = 0
    processed_records: int = 0


@dataclass
class DataAnomaly:
    """Represents a single data anomaly"""
    anomaly_id: str
    anomaly_type: AnomalyType
    symbol: str
    timestamp: float
    severity: float                        # 0.0 to 1.0
    description: str
    details: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False


class DataValidator:
    """Base class for data validators"""

    def __init__(self, name: str):
        self.name = name
        self.validation_count = 0
        self.error_count = 0

    async def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Perform validation"""
        raise NotImplementedError

    def get_error_rate(self) -> float:
        """Get current error rate"""
        if self.validation_count == 0:
            return 0.0
        return self.error_count / self.validation_count


class OHLCValidator(DataValidator):
    """OHLC data logic validator"""

    def __init__(self):
        super().__init__("OHLC Validator")

    async def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate OHLC logic and ranges"""
        self.validation_count += 1
        errors = []

        try:
            # Required fields check
            required_fields = ['open', 'high', 'low', 'close', 'time']
            for field in required_fields:
                if field not in data:
                    errors.append(f"Missing required field: {field}")

            if errors:
                self.error_count += 1
                return False, errors

            # Convert values
            open_price = float(data['open'])
            high_price = float(data['high'])
            low_price = float(data['low'])
            close_price = float(data['close'])

            # Positivity check
            prices = [open_price, high_price, low_price, close_price]
            if any(price <= 0 for price in prices):
                errors.append("Prices must be positive")

            # OHLC consistency check
            if high_price < max(open_price, close_price):
                errors.append(f"High {high_price} is less than max of Open/Close")

            if low_price > min(open_price, close_price):
                errors.append(f"Low {low_price} is greater than min of Open/Close")

            # Extreme movement check
            max_price = max(prices)
            min_price = min(prices)
            if max_price > 0 and (max_price - min_price) / min_price > 0.5:  # 50% movement
                errors.append("Price movement within a single period is too extreme")

            if errors:
                self.error_count += 1
                return False, errors
            else:
                return True, []

        except (ValueError, TypeError) as e:
            self.error_count += 1
            errors.append(f"Data type error: {e}")
            return False, errors
        except Exception as e:
            self.error_count += 1
            errors.append(f"Validation exception: {e}")
            return False, errors


class VolumeValidator(DataValidator):
    """Trading volume validator"""

    def __init__(self):
        super().__init__("Volume Validator")

    async def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate volume data"""
        self.validation_count += 1
        errors = []

        try:
            if 'volume' not in data:
                return True, []  # Volume is optional

            volume = float(data['volume'])

            # Non-negativity check
            if volume < 0:
                errors.append("Volume cannot be negative")

            if errors:
                self.error_count += 1
                return False, errors
            else:
                return True, []

        except (ValueError, TypeError) as e:
            self.error_count += 1
            errors.append(f"Volume data type error: {e}")
            return False, errors


class TimestampValidator(DataValidator):
    """Data timestamp validator"""

    def __init__(self, max_future_seconds: int = 300, max_past_seconds: int = 86400):
        super().__init__("Timestamp Validator")
        self.max_future_seconds = max_future_seconds
        self.max_past_seconds = max_past_seconds

    async def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate timestamp ranges"""
        self.validation_count += 1
        errors = []

        try:
            if 'time' not in data:
                errors.append("Missing timestamp field")
                self.error_count += 1
                return False, errors

            timestamp = data['time']
            current_time = time.time()

            # Format normalization
            if isinstance(timestamp, str):
                timestamp = float(timestamp)
            elif isinstance(timestamp, datetime):
                timestamp = timestamp.timestamp()

            # Range check
            time_diff = timestamp - current_time

            if time_diff > self.max_future_seconds:
                errors.append(f"Timestamp too far in future: {time_diff:.0f}s")

            if time_diff < -self.max_past_seconds:
                errors.append(f"Timestamp too old: {abs(time_diff):.0f}s")

            if errors:
                self.error_count += 1
                return False, errors
            else:
                return True, []

        except (ValueError, TypeError) as e:
            self.error_count += 1
            errors.append(f"Timestamp format error: {e}")
            return False, errors


class ContinuityValidator(DataValidator):
    """Data sequence continuity validator"""

    def __init__(self, expected_interval: int = 900):  # 15 min = 900s
        super().__init__("Continuity Validator")
        self.expected_interval = expected_interval
        self.last_timestamps = {} # symbol -> timestamp
        self.tolerance = expected_interval * 0.1  # 10% tolerance

    async def validate(self, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate time sequence continuity"""
        # Note: This validator now requires 'symbol' in data for multi-symbol support
        self.validation_count += 1
        errors = []

        try:
            if 'time' not in data:
                return True, []

            symbol = data.get('symbol', 'DEFAULT')
            current_timestamp = float(data['time'])

            if symbol in self.last_timestamps:
                last_timestamp = self.last_timestamps[symbol]
                time_gap = current_timestamp - last_timestamp
                expected_gap = self.expected_interval

                # Interval check
                if abs(time_gap - expected_gap) > self.tolerance:
                    if time_gap > expected_gap:
                        errors.append(f"Data gap too large: {time_gap:.0f}s (Expected: {expected_gap:.0f}s)")
                    else:
                        errors.append(f"Data gap too small: {time_gap:.0f}s (Expected: {expected_gap:.0f}s)")

            self.last_timestamps[symbol] = current_timestamp

            if errors:
                self.error_count += 1
                return False, errors
            else:
                return True, []

        except (ValueError, TypeError) as e:
            self.error_count += 1
            errors.append(f"Continuity validation error: {e}")
            return False, errors


class AnomalyDetector:
    """Stateful anomaly detector using history windows"""

    def __init__(self, symbol: str, window_size: int = 100):
        self.symbol = symbol
        self.window_size = window_size

        self.price_history: deque = deque(maxlen=window_size)
        self.volume_history: deque = deque(maxlen=window_size)
        self.time_history: deque = deque(maxlen=window_size)

        self.anomaly_count = 0
        self.detected_anomalies: List[DataAnomaly] = []

    async def detect_anomalies(self, data: Dict[str, Any]) -> List[DataAnomaly]:
        """Run all detection algorithms on data point"""
        anomalies = []

        try:
            current_time = time.time()

            # Price detection
            if 'close' in data:
                price_anomalies = await self._detect_price_anomalies(data, current_time)
                anomalies.extend(price_anomalies)

            # Volume detection
            if 'volume' in data:
                volume_anomalies = await self._detect_volume_anomalies(data, current_time)
                anomalies.extend(volume_anomalies)

            # Time detection
            if 'time' in data:
                time_anomalies = await self._detect_time_anomalies(data, current_time)
                anomalies.extend(time_anomalies)

            # Update windows
            self._update_history(data)

            self.detected_anomalies.extend(anomalies)
            self.anomaly_count += len(anomalies)

            return anomalies

        except Exception as e:
            logger.error(f"Anomaly detection failed: {e}")
            return []

    async def _detect_price_anomalies(self, data: Dict[str, Any], current_time: float) -> List[DataAnomaly]:
        """Detect statistical price anomalies"""
        anomalies = []

        try:
            if len(self.price_history) < 10:
                return anomalies

            current_price = float(data['close'])
            prices = list(self.price_history)
            mean_price = statistics.mean(prices)
            std_price = statistics.stdev(prices) if len(prices) > 1 else 0

            if std_price > 0:
                # Z-score detection
                z_score = abs(current_price - mean_price) / std_price

                if z_score > 3:  # 3-sigma rule
                    severity = min(1.0, z_score / 5.0)
                    anomalies.append(DataAnomaly(
                        anomaly_id=f"price_spike_{self.symbol}_{int(current_time)}",
                        anomaly_type=AnomalyType.PRICE_SPIKE,
                        symbol=self.symbol,
                        timestamp=current_time,
                        severity=severity,
                        description=f"Price jump detected, Z-score: {z_score:.2f}",
                        details={
                            'current_price': current_price,
                            'mean_price': mean_price,
                            'std_price': std_price,
                            'z_score': z_score
                        }
                    ))

            # Percentile detection
            if len(prices) >= 20:
                percentile_95 = statistics.quantiles(prices, n=20)[18]
                percentile_5 = statistics.quantiles(prices, n=20)[0]

                if current_price > percentile_95 * 1.2 or current_price < percentile_5 * 0.8:
                    anomalies.append(DataAnomaly(
                        anomaly_id=f"extreme_value_{self.symbol}_{int(current_time)}",
                        anomaly_type=AnomalyType.EXTREME_VALUE,
                        symbol=self.symbol,
                        timestamp=current_time,
                        severity=0.7,
                        description="Price outside normal ranges",
                        details={
                            'current_price': current_price,
                            'percentile_95': percentile_95,
                            'percentile_5': percentile_5
                        }
                    ))

        except Exception as e:
            logger.error(f"Price anomaly detection failed: {e}")

        return anomalies

    async def _detect_volume_anomalies(self, data: Dict[str, Any], current_time: float) -> List[DataAnomaly]:
        """Detect volume spikes"""
        anomalies = []

        try:
            if len(self.volume_history) < 10:
                return anomalies

            current_volume = float(data['volume'])
            volumes = [v for v in self.volume_history if v > 0]
            if not volumes:
                return anomalies

            mean_volume = statistics.mean(volumes)

            if current_volume > mean_volume * 10:
                anomalies.append(DataAnomaly(
                    anomaly_id=f"volume_spike_{self.symbol}_{int(current_time)}",
                    anomaly_type=AnomalyType.VOLUME_ANOMALY,
                    symbol=self.symbol,
                    timestamp=current_time,
                    severity=0.6,
                    description=f"Abnormal volume spike: {current_volume:.0f} (Avg: {mean_volume:.0f})",
                    details={
                        'current_volume': current_volume,
                        'mean_volume': mean_volume,
                        'ratio': current_volume / mean_volume
                    }
                ))

        except Exception as e:
            logger.error(f"Volume anomaly detection failed: {e}")

        return anomalies

    async def _detect_time_anomalies(self, data: Dict[str, Any], current_time: float) -> List[DataAnomaly]:
        """Detect time sequence anomalies"""
        anomalies = []

        try:
            if len(self.time_history) < 2:
                return anomalies

            data_timestamp = float(data['time'])
            last_timestamp = self.time_history[-1]

            time_gap = data_timestamp - last_timestamp
            expected_gap = 900

            if abs(time_gap - expected_gap) > expected_gap * 0.5:
                anomalies.append(DataAnomaly(
                    anomaly_id=f"time_gap_{self.symbol}_{int(current_time)}",
                    anomaly_type=AnomalyType.TIME_GAP,
                    symbol=self.symbol,
                    timestamp=current_time,
                    severity=0.4,
                    description=f"Time gap anomaly: {time_gap:.0f}s (Expected: {expected_gap:.0f}s)",
                    details={
                        'actual_gap': time_gap,
                        'expected_gap': expected_gap,
                        'last_timestamp': last_timestamp,
                        'current_timestamp': data_timestamp
                    }
                ))

        except Exception as e:
            logger.error(f"Time anomaly detection failed: {e}")

        return anomalies

    def _update_history(self, data: Dict[str, Any]) -> None:
        """Add new point to sliding history windows"""
        try:
            if 'close' in data:
                self.price_history.append(float(data['close']))

            if 'volume' in data:
                self.volume_history.append(float(data['volume']))

            if 'time' in data:
                self.time_history.append(float(data['time']))

        except Exception as e:
            logger.error(f"Failed to update history windows: {e}")

    def get_anomaly_stats(self) -> Dict[str, Any]:
        """Calculate anomaly summary statistics"""
        anomaly_type_counts = defaultdict(int)
        total_severity = 0.0

        for anomaly in self.detected_anomalies:
            anomaly_type_counts[anomaly.anomaly_type.name] += 1
            total_severity += anomaly.severity

        avg_severity = total_severity / max(1, len(self.detected_anomalies))

        return {
            'total_anomalies': len(self.detected_anomalies),
            'anomaly_types': dict(anomaly_type_counts),
            'average_severity': avg_severity,
            'anomaly_rate': len(self.detected_anomalies) / max(1, len(self.price_history))
        }


class DataQualityEngine:
    """Engine for assessing overall data quality"""

    def __init__(self):
        # Suite of validators
        self.validators = [
            OHLCValidator(),
            VolumeValidator(),
            TimestampValidator(),
            ContinuityValidator()
        ]

        # Symbol-specific anomaly detectors
        self.anomaly_detectors: Dict[str, AnomalyDetector] = {}

        # Historical quality records
        self.quality_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))

        # Engine stats
        self.total_evaluations = 0
        self.quality_sum = 0.0

    async def evaluate_data_quality(self, symbol: str, data_batch: List[Dict[str, Any]]) -> QualityMetrics:
        """Run full quality suite on a batch of data"""
        try:
            timeframe = "15m"
            current_time = time.time()

            metrics = QualityMetrics(
                symbol=symbol,
                timeframe=timeframe,
                timestamp=current_time
            )

            if not data_batch:
                metrics.overall_quality_score = 0.0
                metrics.quality_level = QualityLevel.CRITICAL
                return metrics

            metrics.total_records = len(data_batch)

            # Run validations
            validation_results = await self._validate_data_batch(data_batch, symbol)

            # Detect anomalies
            anomalies = await self._detect_batch_anomalies(symbol, data_batch)

            # Final scoring
            await self._calculate_quality_metrics(metrics, data_batch, validation_results, anomalies)

            self.quality_history[symbol].append(metrics)
            self.total_evaluations += 1
            self.quality_sum += metrics.overall_quality_score

            return metrics

        except Exception as e:
            logger.error(f"Quality assessment failed: {e}")
            return QualityMetrics(symbol=symbol, timeframe="15m", overall_quality_score=0.0)

    async def _validate_data_batch(self, data_batch: List[Dict[str, Any]], symbol: str = None) -> Dict[str, List]:
        """Validate a batch using all active validators"""
        validation_results = {
            'valid_records': [],
            'invalid_records': [],
            'validation_errors': []
        }

        for data in data_batch:
            # Ensure symbol is present for continuity check
            if symbol and 'symbol' not in data:
                data = data.copy()
                data['symbol'] = symbol

            is_valid = True
            record_errors = []

            for validator in self.validators:
                try:
                    valid, errors = await validator.validate(data)
                    if not valid:
                        is_valid = False
                        record_errors.extend(errors)
                except Exception as e:
                    is_valid = False
                    record_errors.append(f"{validator.name} exception: {e}")

            if is_valid:
                validation_results['valid_records'].append(data)
            else:
                validation_results['invalid_records'].append(data)
                validation_results['validation_errors'].extend(record_errors)

        return validation_results

    async def _detect_batch_anomalies(self, symbol: str, data_batch: List[Dict[str, Any]]) -> List[DataAnomaly]:
        """Detect anomalies across a batch of records"""
        if symbol not in self.anomaly_detectors:
            self.anomaly_detectors[symbol] = AnomalyDetector(symbol)

        detector = self.anomaly_detectors[symbol]
        all_anomalies = []

        for data in data_batch:
            try:
                anomalies = await detector.detect_anomalies(data)
                all_anomalies.extend(anomalies)
            except Exception as e:
                logger.error(f"Batch anomaly detection failed for {symbol}: {e}")

        return all_anomalies

    async def _calculate_quality_metrics(self,
                                       metrics: QualityMetrics,
                                       data_batch: List[Dict[str, Any]],
                                       validation_results: Dict[str, List],
                                       anomalies: List[DataAnomaly]) -> None:
        """Weight results into quality metrics"""
        try:
            total_records = len(data_batch)
            valid_records = len(validation_results['valid_records'])

            # Completeness
            metrics.completeness_score = valid_records / max(1, total_records)
            metrics.missing_data_ratio = (total_records - valid_records) / max(1, total_records)
            metrics.valid_records = valid_records
            metrics.processed_records = total_records

            # Accuracy
            invalid_ohlc_count = sum(1 for err in validation_results['validation_errors']
                                   if 'OHLC' in err or 'Prices' in err)
            metrics.invalid_ohlc_ratio = invalid_ohlc_count / max(1, total_records)
            metrics.accuracy_score = 1.0 - metrics.invalid_ohlc_ratio

            # Consistency
            time_errors = sum(1 for err in validation_results['validation_errors']
                            if 'Time' in err or 'gap' in err)
            metrics.time_consistency_ratio = 1.0 - (time_errors / max(1, total_records))
            metrics.consistency_score = metrics.time_consistency_ratio

            # Timeliness
            if data_batch:
                latest_data = max(data_batch, key=lambda x: x.get('time', 0))
                if 'time' in latest_data:
                    data_time = float(latest_data['time'])
                    current_time = time.time()
                    metrics.data_delay = current_time - data_time
                    metrics.timeliness_score = max(0.0, 1.0 - (metrics.data_delay / 3600))  # Full score if < 1h

            # Anomaly severity
            metrics.anomaly_count = len(anomalies)
            anomaly_types_count = defaultdict(int)
            total_severity = 0.0

            for anomaly in anomalies:
                anomaly_types_count[anomaly.anomaly_type.name] += 1
                total_severity += anomaly.severity

            metrics.anomaly_types = dict(anomaly_types_count)
            metrics.anomaly_severity = total_severity / max(1, len(anomalies))

            # Weighted overall score
            quality_factors = [
                metrics.completeness_score * 0.25,
                metrics.accuracy_score * 0.30,
                metrics.consistency_score * 0.20,
                metrics.timeliness_score * 0.15,
                (1.0 - min(1.0, metrics.anomaly_severity)) * 0.10
            ]

            metrics.overall_quality_score = sum(quality_factors)

            # Map score to level
            if metrics.overall_quality_score >= 0.95:
                metrics.quality_level = QualityLevel.EXCELLENT
            elif metrics.overall_quality_score >= 0.85:
                metrics.quality_level = QualityLevel.GOOD
            elif metrics.overall_quality_score >= 0.70:
                metrics.quality_level = QualityLevel.FAIR
            elif metrics.overall_quality_score >= 0.50:
                metrics.quality_level = QualityLevel.POOR
            else:
                metrics.quality_level = QualityLevel.CRITICAL

        except Exception as e:
            logger.error(f"Failed to weight quality metrics: {e}")
            metrics.overall_quality_score = 0.0
            metrics.quality_level = QualityLevel.CRITICAL

    def get_quality_summary(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Summarize current quality across symbols"""
        try:
            if symbol and symbol in self.quality_history:
                history = list(self.quality_history[symbol])
            else:
                history = []
                for symbol_history in self.quality_history.values():
                    history.extend(list(symbol_history))

            if not history:
                return {
                    'total_evaluations': 0,
                    'average_quality_score': 0.0,
                    'quality_trend': 0.0,
                    'quality_distribution': {}
                }

            quality_scores = [m.overall_quality_score for m in history]
            avg_quality = statistics.mean(quality_scores)

            # Calculate trend
            quality_trend = 0.0
            if len(quality_scores) >= 20:
                recent_avg = statistics.mean(quality_scores[-10:])
                previous_avg = statistics.mean(quality_scores[-20:-10])
                quality_trend = recent_avg - previous_avg

            quality_distribution = defaultdict(int)
            for metrics in history:
                quality_distribution[metrics.quality_level.name] += 1

            return {
                'total_evaluations': len(history),
                'average_quality_score': avg_quality,
                'quality_trend': quality_trend,
                'quality_distribution': dict(quality_distribution),
                'recent_quality_score': quality_scores[-1] if quality_scores else 0.0,
                'validator_stats': {
                    validator.name: {
                        'validation_count': validator.validation_count,
                        'error_count': validator.error_count,
                        'error_rate': validator.get_error_rate()
                    }
                    for validator in self.validators
                }
            }

        except Exception as e:
            logger.error(f"Failed to get quality summary: {e}")
            return {}

    def get_anomaly_report(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Generate full report on detected anomalies"""
        try:
            if symbol and symbol in self.anomaly_detectors:
                detectors = [self.anomaly_detectors[symbol]]
            else:
                detectors = list(self.anomaly_detectors.values())

            if not detectors:
                return {'total_anomalies': 0}

            total_anomalies = 0
            anomaly_type_counts = defaultdict(int)
            total_severity = 0.0

            for detector in detectors:
                stats = detector.get_anomaly_stats()
                total_anomalies += stats['total_anomalies']
                total_severity += stats['average_severity'] * stats['total_anomalies']

                for anomaly_type, count in stats['anomaly_types'].items():
                    anomaly_type_counts[anomaly_type] += count

            avg_severity = total_severity / max(1, total_anomalies)

            return {
                'total_anomalies': total_anomalies,
                'anomaly_types': dict(anomaly_type_counts),
                'average_severity': avg_severity,
                'symbols_with_anomalies': len([d for d in detectors if d.anomaly_count > 0])
            }

        except Exception as e:
            logger.error(f"Failed to generate anomaly report: {e}")
            return {}


async def evaluate_kline_quality(symbol: str, klines: List[Dict[str, Any]]) -> QualityMetrics:
    """Helper function to quickly evaluate K-line quality"""
    engine = DataQualityEngine()
    return await engine.evaluate_data_quality(symbol, klines)
